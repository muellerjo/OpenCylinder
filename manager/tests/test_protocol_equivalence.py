"""The manager must produce exactly the bytes / commands of the reference scripts."""

import json
import sys

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from conftest import HOSPITAL
from ocmanager.protocol import an10922, bundle as B, card as C, encoder as E
from ocmanager.protocol.commissioning import HKDF_INFO, LockIdentity, SiteSecrets, commissioning_bundle

sys.path.insert(0, str(HOSPITAL))
ref_access = pytest.importorskip("check_access")
ref_bundle = pytest.importorskip("bundle")
ref_kdf = pytest.importorskip("an10922")
ref_card = pytest.importorskip("write_test_card")

SITE = json.loads((HOSPITAL / "site.json").read_text())


def test_an10922_known_answer():
    assert ref_kdf.self_test()
    mk = bytes.fromhex("00112233445566778899AABBCCDDEEFF")
    m = bytes.fromhex("04782E21801D80" "3042F5" "4E585020416275")
    assert an10922.diversify(mk, m).hex().upper() == "A8DD63A3B89D54B37CA802473FDA9175"


@pytest.mark.parametrize("user", SITE["users"], ids=lambda u: str(u["credential_id"]))
def test_card_bytes_match_reference(user):
    f0_ref, f1_ref = ref_access.encode_card(SITE, user)
    entries = C.merge_entries([C.Entry(C.TYPE_DOOR if k == 1 else C.TYPE_ZONE, t, p)
                               for k, t, p in ref_access.access_entries(SITE, user)])
    f0, f1 = C.encode_card(user["credential_id"], entries, ref_access.unix(user.get("valid_until")),
                           ref_access.unix(SITE["site"]["issued_at"]))
    assert (f0, f1) == (f0_ref, f1_ref)


def test_profiles_and_bundle_header_match_reference():
    ours = [{"id": p["id"], "days": p["days"], "intervals": p.get("intervals", [{"from": p["from"], "to": p["to"]}])}
            for p in SITE["time_profiles"]]
    assert B.profiles_value(ours) == ref_bundle.profiles_value(SITE["time_profiles"])
    aid = bytes.fromhex("4F4331")[::-1]
    assert B.build_bundle(aid, 7, 100, 200, b"xyz", b"\x01" * 8) == ref_bundle.build_bundle(aid, 7, 100, 200, b"xyz", b"\x01" * 8)


def test_user_card_plan_matches_reference():
    uid = bytes.fromhex("04AABBCCDDEE80")
    user = next(u for u in SITE["users"] if u["credential_id"] == 2001)
    f0, f1 = ref_access.encode_card(SITE, user)
    n = len(ref_access.access_entries(SITE, user))
    m = uid + bytes.fromhex("4F4331")[::-1]
    k0 = ref_kdf.diversify(bytes.fromhex(ref_card.K0_ISSUER_MASTER), m).hex().upper()
    k1 = ref_kdf.diversify(bytes.fromhex(ref_card.K1_READ_MASTER), m).hex().upper()
    ref = ref_card.build_steps("4F4331", f0, f1[:4 * n], k0, k1, m.hex().upper())
    ours = E.user_card_plan("4F4331", uid, f0, f1[:4 * n], bytes.fromhex(ref_card.K0_ISSUER_MASTER),
                            bytes.fromhex(ref_card.K1_READ_MASTER), bytes.fromhex(ref_card.K2_UID))
    # the reference ends with two AN10922 self-checks that need the MASTER read key on the
    # command line — the manager deliberately leaves them out
    assert [s.cmd for s in ours] == [s["cmd"] for s in ref[:len(ours)]]
    assert all("--kdf" in s["cmd"] or "auth" in s["cmd"] for s in ref[len(ours):])


def test_commissioning_record_decrypts_for_the_lock_only():
    lock_key = ec.generate_private_key(ec.SECP256R1())
    pub33 = lock_key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.CompressedPoint)
    ident = LockIdentity(bytes.fromhex("0000AC276EFB0250"), pub33)
    signer = B.generate_signing_key()
    sec = SiteSecrets(b"\x31\x43\x4F", b"\x41\x43\x4F", b"R" * 16, b"U" * 16, b"A" * 16)
    blob = commissioning_bundle(ident, sec, signer, 4, [3, 4], b"", 99, 1000, 2000)
    header, body, sig = blob[:27], blob[27:-64], blob[-64:]
    assert B.parse_header(blob)["target_device"] == ident.device_id
    # verify the signature like the lock
    from cryptography.hazmat.primitives.asymmetric.utils import encode_dss_signature
    signer.public_key().verify(encode_dss_signature(int.from_bytes(sig[:32], "big"), int.from_bytes(sig[32:], "big")),
                               blob[:-64], ec.ECDSA(hashes.SHA256()))
    assert body[0] == B.T_COMMISSIONING
    rec = body[3:3 + int.from_bytes(body[1:3], "little")]
    eph = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), rec[:65])
    key = HKDF(hashes.SHA256(), 16, salt=ident.device_id, info=HKDF_INFO).derive(lock_key.exchange(ec.ECDH(), eph))
    plain = AESGCM(key).decrypt(rec[65:77], rec[77:], header)
    assert plain.startswith(b"\x31\x43\x4F\x41\x43\x4FRRRRRRRRRRRRRRRRUUUUUUUUUUUUUUUUAAAAAAAAAAAAAAAA")
    assert plain.endswith(bytes([4, 0, 2, 3, 0, 4, 0]))
    other = ec.generate_private_key(ec.SECP256R1())
    bad = HKDF(hashes.SHA256(), 16, salt=ident.device_id, info=HKDF_INFO).derive(other.exchange(ec.ECDH(), eph))
    with pytest.raises(Exception):
        AESGCM(bad).decrypt(rec[65:77], rec[77:], header)
