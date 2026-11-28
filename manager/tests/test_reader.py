"""Card inspector against a simulated Proxmark3 that only answers with the right keys."""

import re

from conftest import Browser  # noqa: F401
from ocmanager.modules.sites.devkeys import HOSPITAL_DEFAULTS as DEV
from ocmanager.protocol import encoder as E

UID = "04AABBCCDDEE80"


def dump(data: bytes) -> str:
    lines = ["[=] ------------------------------- File 00 data -------------------------------",
             f"[+] Read {len(data)} bytes from file 0x00 offset 0",
             "[=]  Offset  | Data                                            | Ascii",
             "[=] ----------------------------------------------------------------------------"]
    for i in range(0, len(data), 16):
        chunk = data[i:i + 16]
        lines.append(f"[=] {i:3}/0x{i:02X} | {chunk.hex(' ').upper():<47} | {'.' * len(chunk)}")
    return "\n".join(lines)


class FakeCard:
    """apps: {aid: {fid: bytes}}; keys: {aid: expected read key hex or None (free read)}."""

    def __init__(self, apps, keys, uid=UID):
        self.apps, self.keys, self.uid = apps, keys, uid
        self.log = []

    def batch(self, cmds):
        out = []
        for c in cmds:
            self.log.append(c)
            if c == "hf 14a info":
                out.append(f"[+]  UID: {bytes.fromhex(self.uid).hex(' ').upper()} \n[+] MIFARE DESFire EV1 4K")
            elif c == "hf mfdes getaids":
                out.append(f"[+] --- AID list ( {len(self.apps)} found )\n[+] " + " ".join(self.apps))
            else:
                m = re.match(r"hf mfdes read --aid (\w+) (?:-n 1 -t aes -k (\w+) -m encrypt|--no-auth) --fid (\w+)", c)
                aid, key, fid = m.group(1), m.group(2), int(m.group(3), 16)
                if self.keys.get(aid) != key:
                    out.append("[!] Authentication error")
                else:
                    out.append(dump(self.apps[aid][fid]))
        return out


def _job(admin, site, path, **json):
    return admin.api("POST", f"/t/hospital/sites/{site}/cards{path}", json=json or None).json()


def test_reader_page_without_reader(admin, hospital):
    admin.c.app.state.settings.pm3_path = None
    assert "No reader on this machine" in admin.get("/t/hospital/reader").text


def test_inspect_user_card_written_by_the_gui(app, admin, hospital):
    people = admin.api("GET", f"/t/hospital/sites/{hospital}/people", params={"q": "2001"}).json()
    job = _job(admin, hospital, f"/user/{people[0]['id']}")
    f0, f1 = bytes.fromhex(job["payload"]["file0"]), bytes.fromhex(job["payload"]["file1"])
    _, k1 = E.card_keys(bytes.fromhex(UID), "4F4331", bytes.fromhex(DEV["issuer_master"]),
                        bytes.fromhex(DEV["read_master"]))
    app.state.card_reader = FakeCard({"4F4331": {0: f0, 1: f1 + bytes(128 - len(f1))}}, {"4F4331": k1})
    r = admin.api("POST", "/t/hospital/reader/inspect").json()
    a = r["applications"][0]
    assert r["uid"] == UID and a["kind"] == "user" and a["person"] == "Sara Yilmaz"
    assert a["problems"] == [] and a["credential_id"] == 2001
    assert a["opens_now"] == [1, 3, 4, 5, 12]                      # ward 1 nurse
    # HTML page via htmx
    html = admin.c.post("/t/hospital/reader", headers={"HX-Request": "true", "X-CSRF-Token": admin.token}).text
    assert "Sara Yilmaz" in html and "up to date" in html and "Ward 1 - ward door" in html

    # rights change -> card is out of date; blacklist -> flagged
    admin.post(f"/t/hospital/s/{hospital}/people/{people[0]['id']}",
               {"name": "Sara Yilmaz", "roles[]": "nurse-ward-2"})
    a = admin.api("POST", "/t/hospital/reader/inspect").json()["applications"][0]
    assert any("out of date" in p for p in a["problems"])
    cred = people[0]["credentials"][0]["id"]
    admin.api("PUT", f"/t/hospital/sites/{hospital}/credentials/{cred}/status", json={"status": "blacklisted"})
    a = admin.api("POST", "/t/hospital/reader/inspect").json()["applications"][0]
    assert any("BLACKLISTED" in p for p in a["problems"]) and a["opens_now"] == []


def test_inspect_wrong_keys_and_foreign_apps(app, admin, hospital):
    app.state.card_reader = FakeCard({"4F4331": {0: bytes(16), 1: bytes(128)}, "F51001": {}},
                                     {"4F4331": "00" * 16})
    apps = admin.api("POST", "/t/hospital/reader/inspect").json()["applications"]
    assert "other keys" in apps[0]["problems"][0]
    assert apps[1]["kind"] == "foreign"


def test_inspect_admin_and_commissioning_cards(app, admin, hospital):
    job = _job(admin, hospital, "/maintenance", valid_days=2)
    hdr, bundle = bytes.fromhex(job["payload"]["header"]), bytes.fromhex(job["payload"]["bundle"])
    _, ka1 = E.card_keys(bytes.fromhex(UID), "4F4341", bytes.fromhex(DEV["admin_issuer_master"]),
                         bytes.fromhex(DEV["admin_read_master"]))
    card = FakeCard({"4F4341": {0: hdr, 1: bundle + bytes(0x400 - len(bundle))}}, {"4F4341": ka1})
    app.state.card_reader = card
    a = admin.api("POST", "/t/hospital/reader/inspect").json()["applications"][0]
    assert a["kind"] == "admin" and a["problems"] == []
    names = [r["name"] for r in a["bundle"]["records"]]
    assert names == ["blacklist replace", "time profiles", "time-zone rule"]
    assert a["bundle"]["records"][0]["entries"][0]["credential_id"] == 2003
    # a newer bundle makes this one stale; a flipped byte breaks the signature
    _job(admin, hospital, "/maintenance", valid_days=2)
    a = admin.api("POST", "/t/hospital/reader/inspect").json()["applications"][0]
    assert any("older than the newest" in p for p in a["problems"])
    bad = bytearray(bundle)
    bad[40] ^= 1
    card.apps["4F4341"][1] = bytes(bad) + bytes(0x400 - len(bad))
    a = admin.api("POST", "/t/hospital/reader/inspect").json()["applications"][0]
    assert any("signature does NOT match" in p for p in a["problems"])

    # commissioning card for a registered lock
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    pub = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.CompressedPoint).hex().upper()
    lk = admin.api("POST", f"/t/hospital/sites/{hospital}/locks", json={"qr": f"OC1:00000000000000AB:{pub}"}).json()
    cj = _job(admin, hospital, f"/lock/{lk['id']}", kind="commissioning", door=4)
    cb = bytes.fromhex(cj["payload"]["bundle"])
    app.state.card_reader = FakeCard({"4F434B": {0: cb + bytes(0x200 - len(cb))}}, {"4F434B": None})
    a = admin.api("POST", "/t/hospital/reader/inspect").json()["applications"][0]
    assert a["kind"] == "commissioning" and a["problems"] == []
    assert a["bundle"]["target_device"] == "00000000000000AB"


def test_inspect_identify_card(app, admin, hospital):
    rec = bytes([1, 1]) + bytes.fromhex("0000AC276EFB0250") + bytes(33) + bytes([0, 2, 0]) \
        + bytes.fromhex("31434F") + (4).to_bytes(2, "little") + bytes(13)
    app.state.card_reader = FakeCard({"4F4349": {0: rec}}, {"4F4349": None})
    a = admin.api("POST", "/t/hospital/reader/inspect").json()["applications"][0]
    assert a["identity"]["device_id"] == "0000AC276EFB0250" and a["identity"]["door"] == 4
    assert a["identity"]["state"] == "OWNED"


def test_no_card(app, admin, hospital):
    class Empty:
        def batch(self, cmds):
            return ["[-] iso14443a card select failed", ""]
    app.state.card_reader = Empty()
    assert admin.api("POST", "/t/hospital/reader/inspect").json()["present"] is False
