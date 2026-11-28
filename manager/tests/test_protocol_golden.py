"""Known-answer tests for the shared wire formats (ocmanager.protocol).

tests/golden/hospital.json was recorded from the original, independent
example scripts before they were switched to this package — so these tests
still compare against an independent implementation. The last tests run the
example scripts themselves (they now use this package) against the same values.
"""

import json
import subprocess
import sys
from datetime import datetime

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from conftest import HOSPITAL
from ocmanager.protocol import an10922, bundle as B, card as C, encoder as E
from ocmanager.protocol.commissioning import HKDF_INFO, LockIdentity, SiteSecrets, commissioning_bundle
from ocmanager.modules.sites.devkeys import HOSPITAL_DEFAULTS as DEV

GOLD = json.loads((HOSPITAL.parents[1] / "manager" / "tests" / "golden" / "hospital.json").read_text())
SITE = json.loads((HOSPITAL / "site.json").read_text())
FAR = 0xFFFFFFFF


def unix(iso):
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()) if iso else 0


def entries(user):
    raw = [e for r in user["roles"] for e in SITE["roles"][r]["entries"]] + user.get("extra", [])
    return C.merge_entries([C.Entry(C.TYPE_DOOR, e["door"], e.get("profile", 0)) if "door" in e
                            else C.Entry(C.TYPE_ZONE, e["zone"], e.get("profile", 0)) for e in raw])


def test_an10922_known_answer():
    mk = bytes.fromhex("00112233445566778899AABBCCDDEEFF")
    m = bytes.fromhex("04782E21801D80" "3042F5" "4E585020416275")
    assert an10922.diversify(mk, m).hex().upper() == "A8DD63A3B89D54B37CA802473FDA9175"


@pytest.mark.parametrize("user", SITE["users"], ids=lambda u: str(u["credential_id"]))
def test_card_bytes(user):
    f0, f1 = C.encode_card(user["credential_id"], entries(user), unix(user.get("valid_until")),
                           unix(SITE["site"]["issued_at"]))
    assert {"file0": f0.hex().upper(), "file1": f1.hex().upper()} == GOLD["cards"][str(user["credential_id"])]


def test_profiles_and_bundle_header():
    assert B.profiles_value(SITE["time_profiles"]).hex().upper() == GOLD["profiles_value"]
    assert B.build_bundle(b"\x31\x43\x4f", 5, 6, 7, b"\x01\x02", b"\x09" * 8).hex().upper() == GOLD["build_bundle_5_6_7"]


def test_admin_records():
    zones6 = next(d["zones"] for d in SITE["doors"] if d["id"] == 6)
    ours = {
        "full": (B.ACT_TIME | B.ACT_BLACKLIST | B.ACT_PROFILES,
                 B.tlv(B.T_BLACKLIST_REPLACE, B.blacklist_value((c, FAR) for c in SITE["blacklist"]))
                 + B.tlv(B.T_TIME_PROFILES, B.profiles_value(SITE["time_profiles"]))
                 + B.tlv(B.T_TZ_RULE, SITE["site"]["posix_tz"].encode())),
        "blacklist_add_2001_7": (B.ACT_TIME | B.ACT_BLACKLIST,
                                 B.tlv(B.T_BLACKLIST_ADD, B.blacklist_value([(2001, FAR), (7, FAR)]))),
        "blacklist_remove_2003": (B.ACT_TIME | B.ACT_BLACKLIST,
                                  B.tlv(B.T_BLACKLIST_REMOVE, (2003).to_bytes(4, "little"))),
        "reassign_door_6": (B.ACT_TIME | B.ACT_REASSIGN, B.tlv(B.T_LOCK_ASSIGNMENT, B.assignment_value(6, zones6))),
        "decommission": (B.ACT_TIME | B.ACT_DECOMMISSION, B.tlv(B.T_DECOMMISSION, b"")),
    }
    for name, (act, rec) in ours.items():
        assert {"actions": act, "records": rec.hex().upper()} == GOLD["admin_records"][name], name


@pytest.mark.parametrize("cred", [2001, 4001])
def test_user_card_commands(cred):
    user = next(u for u in SITE["users"] if u["credential_id"] == cred)
    es = entries(user)
    f0, f1 = C.encode_card(cred, es, unix(user.get("valid_until")), unix(SITE["site"]["issued_at"]))
    uid = bytes.fromhex(GOLD["uid"])
    plan = E.user_card_plan("4F4331", uid, f0, f1[:4 * len(es)], bytes.fromhex(DEV["issuer_master"]),
                            bytes.fromhex(DEV["read_master"]), bytes.fromhex(DEV["uid_key"]))
    kdf = E.kdf_check_steps("4F4331", DEV["read_master"], (uid + bytes.fromhex("31434F")).hex().upper())
    assert [s.cmd for s in plan + kdf] == GOLD[f"user_card_{cred}_commands"]
    # the manager's plan never contains a master key
    assert DEV["read_master"] not in " ".join(s.cmd for s in plan)


def test_commissioning_record_decrypts_for_the_lock_only():
    lock_key = ec.generate_private_key(ec.SECP256R1())
    pub33 = lock_key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.CompressedPoint)
    ident = LockIdentity(bytes.fromhex("0000AC276EFB0250"), pub33)
    signer = B.generate_signing_key()
    sec = SiteSecrets(b"\x31\x43\x4F", b"\x41\x43\x4F", b"R" * 16, b"U" * 16, b"A" * 16)
    blob = commissioning_bundle(ident, sec, signer, 4, [3, 4], b"", 99, 1000, 2000)
    header, body, sig = blob[:27], blob[27:-64], blob[-64:]
    assert B.parse_header(blob)["target_device"] == ident.device_id
    signer.public_key().verify(encode_dss_signature(int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big")),
                               blob[:-64], ec.ECDSA(hashes.SHA256()))
    assert body[0] == B.T_COMMISSIONING
    rec = body[3:3 + int.from_bytes(body[1:3], "little")]
    eph = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), rec[:65])
    key = HKDF(hashes.SHA256(), 16, salt=ident.device_id, info=HKDF_INFO).derive(lock_key.exchange(ec.ECDH(), eph))
    plain = AESGCM(key).decrypt(rec[65:77], rec[77:], header)
    assert plain.startswith(b"\x31\x43\x4F\x41\x43\x4F" + b"R" * 16 + b"U" * 16 + b"A" * 16)
    assert plain.endswith(bytes([4, 0, 2, 3, 0, 4, 0]))
    other = ec.generate_private_key(ec.SECP256R1())
    bad = HKDF(hashes.SHA256(), 16, salt=ident.device_id, info=HKDF_INFO).derive(other.exchange(ec.ECDH(), eph))
    with pytest.raises(Exception):
        AESGCM(bad).decrypt(rec[65:77], rec[77:], header)


# ---- the example scripts (now thin wrappers) still give the recorded answers

def run_example(*args):
    return subprocess.run([sys.executable, *args], cwd=HOSPITAL, capture_output=True, text=True,
                          check=True).stdout


@pytest.mark.parametrize("at,key", [("2026-11-24 03:00", "check_access_0300"), ("2026-11-24 10:00", "check_access_1000")])
def test_example_check_access(at, key):
    assert run_example("check_access.py", "--at", at) == GOLD[key]


def test_example_write_test_card_dry_run():
    out = run_example("write_test_card.py", "--dry-run", "--uid", GOLD["uid"])
    assert [l for l in out.splitlines() if l.startswith("hf ")] == GOLD["user_card_2001_commands"]
