import json
import re

from conftest import HOSPITAL, Browser, make_user


def test_login_required_and_wrong_password(app):
    make_user(app, "bob")
    b = Browser(app)
    r = b.get("/t/x", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/login")
    assert b.c.get("/api/v1/t/x/sites").status_code == 401
    tok = re.search(r'csrf-token" content="([^"]+)', b.get("/login").text).group(1)
    r = b.c.post("/login", data={"username": "bob", "password": "wrong-password!", "csrf_token": tok})
    assert "Wrong user name or password" in r.text


def test_csrf_required(app, admin):
    r = admin.c.post("/platform/tenants", data={"slug": "abc", "name": "x"})
    assert r.status_code == 403
    assert admin.c.post("/api/v1/platform/tenants", json={"slug": "abc"}).status_code == 403


def test_pages_render(admin, hospital):
    base = f"/t/hospital/s/{hospital}"
    for url in ["/t/hospital", base, base + "/zones", base + "/doors", base + "/profiles", base + "/people",
                base + "/roles", base + "/blacklist", base + "/locks", base + "/cards", base + "/access",
                "/t/hospital/audit", "/t/hospital/members", "/platform/tenants", "/platform/operators",
                "/platform/audit", "/account"]:
        r = admin.get(url)
        assert r.status_code == 200, (url, r.text[:500])
    assert "PUBLIC DEV TEST KEYS" in admin.get(base).text


def test_access_matrix_matches_reference(admin, hospital):
    import sys
    sys.path.insert(0, str(HOSPITAL))
    import check_access as ref
    from zoneinfo import ZoneInfo
    from datetime import datetime
    site = json.loads((HOSPITAL / "site.json").read_text())
    for at in ["2026-11-24T10:00", "2026-11-24T03:00"]:
        now = int(datetime.fromisoformat(at).replace(tzinfo=ZoneInfo("Europe/Berlin")).timestamp())
        ours = admin.api("GET", f"/t/hospital/sites/{hospital}/access-matrix", params={"at": at}).json()
        by_cred = {r["credential"]: [d["result"] for d in r["decisions"]] for r in ours["rows"]}
        sym = {"✓": "open", "·": "none", "t": "profile", "E": "expired", "B": "blacklisted", "?": "notime"}
        for u in site["users"]:
            f0, f1 = ref.encode_card(site, u)
            expect = [sym[ref.Lock(site, d).decide(f0, f1, now)[0]] for d in site["doors"]]
            assert by_cred[u["credential_id"]] == expect, (at, u["name"])


def test_issue_user_card_and_plan(admin, hospital):
    base = f"/t/hospital/s/{hospital}"
    people = admin.api("GET", f"/t/hospital/sites/{hospital}/people", params={"q": "2001"}).json()
    assert [p["name"] for p in people] == ["Sara Yilmaz"]
    job = admin.api("POST", f"/t/hospital/sites/{hospital}/cards/user/{people[0]['id']}").json()
    plan = admin.api("POST", f"/t/hospital/sites/{hospital}/cards/{job['id']}/plan",
                     json={"uid": "04AABBCCDDEE80"}).json()
    assert plan[0]["cmd"] == "hf mfdes formatpicc"
    assert "00112233445566778899AABBCCDDEEFF" not in json.dumps(plan)     # never the master read key
    html = admin.get(f"{base}/cards/{job['id']}?uid=04AABBCCDDEE80").text
    assert "hf mfdes createapp --aid 4F4331" in html
    r = admin.api("POST", f"/t/hospital/sites/{hospital}/cards/{job['id']}/written", json={"uid": "04AABBCCDDEE80"})
    assert r.json()["status"] == "written"
    p = admin.api("GET", f"/t/hospital/sites/{hospital}/people/{people[0]['id']}").json()
    assert p["credentials"][0]["card_uid"] == "04AABBCCDDEE80"


def test_blacklist_and_maintenance_bundle(admin, hospital):
    api = f"/t/hospital/sites/{hospital}"
    assert [b["credential_id"] for b in admin.api("GET", api + "/blacklist").json()] == [2003]
    sara = admin.api("GET", api + "/people", params={"q": "2001"}).json()[0]
    admin.api("PUT", api + f"/credentials/{sara['credentials'][0]['id']}/status", json={"status": "blacklisted"})
    assert [b["credential_id"] for b in admin.api("GET", api + "/blacklist").json()] == [2001, 2003]
    j1 = admin.api("POST", api + "/cards/maintenance", json={"valid_days": 2}).json()
    j2 = admin.api("POST", api + "/cards/maintenance", json={"valid_days": 2}).json()
    assert j2["sequence"] > j1["sequence"]                       # monotonic
    from ocmanager.protocol.bundle import parse_header
    raw = bytes.fromhex(j1["payload"]["bundle"])
    assert parse_header(raw)["site_aid_wire"] == bytes.fromhex("31434F")
    # signed with the dev management key the bench lock trusts
    pk = admin.api("GET", api + "/public-key").json()["public_key"]
    from ocmanager.protocol.bundle import load_signing_key_pem, public_key_raw
    dev = load_signing_key_pem((HOSPITAL / "dev_management_key.pem").read_bytes())
    assert pk == public_key_raw(dev).hex().upper()


def test_lock_lifecycle(admin, hospital):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    pub = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.CompressedPoint).hex().upper()
    api = f"/t/hospital/sites/{hospital}"
    lk = admin.api("POST", api + "/locks", json={"qr": f"OC1:00000000000000AA:{pub}"}).json()
    assert admin.api("POST", api + f"/cards/lock/{lk['id']}", json={"kind": "decommission"}).status_code == 409
    job = admin.api("POST", api + f"/cards/lock/{lk['id']}", json={"kind": "commissioning", "door": 4}).json()
    assert job["kind"] == "commissioning" and "zones [3, 4]" in job["summary"]
    assert admin.api("POST", api + f"/locks/{lk['id']}/confirm").json()["state"] == "owned"
    # the door now has a lock -> cannot be deleted
    doors = admin.api("GET", api + "/doors").json()
    d4 = next(d for d in doors if d["number"] == 4)
    assert admin.api("DELETE", api + f"/doors/{d4['id']}").status_code == 409
    job = admin.api("POST", api + f"/cards/lock/{lk['id']}", json={"kind": "reassign", "door": 6}).json()
    assert "door 6" in job["summary"]
    job = admin.api("POST", api + f"/cards/lock/{lk['id']}", json={"kind": "decommission"}).json()
    assert admin.api("POST", api + f"/locks/{lk['id']}/confirm").json()["state"] == "factory"


def test_tenant_isolation_and_roles(app, admin, hospital):
    make_user(app, "eve")
    make_user(app, "audrey")
    admin.post("/platform/tenants", {"slug": "other", "name": "Other org", "owner": "eve"})
    admin.post("/platform/tenants/2/members", {"username": "audrey", "role": "auditor"})
    with app.state.db.sessionmaker() as db:     # audrey: auditor of 'hospital', not of 'other'
        from ocmanager.core.models import Membership, Tenant
        from sqlalchemy import select
        t = db.scalar(select(Tenant).where(Tenant.slug == "hospital"))
        db.query(Membership).filter_by(operator_id=3).delete()
        db.add(Membership(tenant_id=t.id, operator_id=3, role="auditor"))
        db.commit()
    eve = Browser(app).login("eve")
    # eve owns 'other' but must not see anything of 'hospital' — not even that it exists
    assert eve.get("/t/hospital").status_code == 404
    assert eve.api("GET", f"/t/hospital/sites/{hospital}").status_code == 404
    # nor reach a hospital site through her own tenant's URL
    assert eve.api("GET", f"/t/other/sites/{hospital}").status_code == 404
    assert eve.api("GET", f"/t/other/sites/{hospital}/people").status_code == 404
    aud = Browser(app).login("audrey")
    assert aud.api("GET", f"/t/hospital/sites/{hospital}/people").status_code == 200
    assert aud.api("POST", f"/t/hospital/sites/{hospital}/zones", json={"number": 99, "name": "x"}).status_code == 403
    assert aud.api("POST", f"/t/hospital/sites/{hospital}/cards/maintenance", json={}).status_code == 403
    # platform admin without membership of 'other' cannot read it
    assert admin.get("/t/other").status_code == 404


def test_api_token(admin, hospital):
    r = admin.post("/account/tokens", {"name": "agent", "days": "30"})
    tok = re.search(r'<pre id="tok">(ocm_[^<]+)</pre>', r.text).group(1)
    from fastapi.testclient import TestClient
    c = TestClient(admin.c.app)
    h = {"Authorization": f"Bearer {tok}"}
    assert c.get(f"/api/v1/t/hospital/sites/{hospital}/doors", headers=h).status_code == 200
    # bearer requests need no CSRF token
    assert c.post(f"/api/v1/t/hospital/sites/{hospital}/zones", json={"number": 50, "name": "API"},
                  headers=h).status_code == 201
    assert c.get("/api/v1/t/hospital/sites", headers={"Authorization": "Bearer ocm_bogus"}).status_code == 401


def test_export_roundtrip_has_no_keys(admin, hospital):
    data = admin.api("GET", f"/t/hospital/sites/{hospital}/export").json()
    text = json.dumps(data)
    assert "dev_keys" not in text and "0F0E0D0C" not in text
    assert len(data["users"]) == 11 and data["blacklist"] == [2003]
    data["site"]["aid"], data["site"]["admin_aid"] = "4F4339", "4F4349"
    r = admin.api("POST", "/t/hospital/sites/import", json=data)
    assert r.status_code == 201 and r.json()["dev_keys"] is False


def test_ui_forms(admin, hospital):
    base = f"/t/hospital/s/{hospital}"
    r = admin.post(base + "/zones", {"number": "20", "name": "Garage"})
    assert "Zone added" in r.text
    r = admin.post(base + "/zones", {"number": "20", "name": "dup"})
    assert "exists" in r.text
    r = admin.post(base + "/doors", {"number": "30", "name": "Garage door", "zones[]": "20"})
    assert "Door added" in r.text and "Garage door" in r.text
    r = admin.post(base + "/profiles", {"number": "9", "name": "Night", "days[]": ["Mon", "Tue"],
                                        "from1": "22:00", "to1": "06:00"})
    assert "Profile added" in r.text
    r = admin.post(base + "/people", {"name": "New Person", "roles[]": "it", "with_card": "1"})
    assert "Person added" in r.text and "IT administrator" in r.text
    pid = re.search(r"/people/(\d+)", str(r.url)).group(1)
    r = admin.post(base + f"/people/{pid}", {"name": "New Person", "roles[]": "it",
                                             "e_target[]": ["door:30", ""], "e_profile[]": ["9", "0"]})
    assert "Saved" in r.text and "door 30" in r.text
    r = admin.post(base + f"/cards/user/{pid}")
    assert "User card" in r.text and "Card UID" in r.text
    r = admin.get(base + "/access?at=2026-11-24T23:00")
    assert "New Person" in r.text


def test_manager_card_bytes_match_golden(admin, hospital):
    """A user card issued in the GUI carries the recorded bytes (except issued_at = now)."""
    gold = json.loads((HOSPITAL.parents[1] / "manager" / "tests" / "golden" / "hospital.json").read_text())
    api = f"/t/hospital/sites/{hospital}"
    for p in admin.api("GET", api + "/people").json():
        cred = next((c for c in p["credentials"] if c["status"] == "active"), None)
        if cred is None:
            continue
        job = admin.api("POST", api + f"/cards/user/{p['id']}").json()
        g = gold["cards"][str(cred["number"])]
        assert job["payload"]["file0"][:24] == g["file0"][:24], p["name"]          # all but issued_at
        n = len(job["payload"]["file1"])
        assert job["payload"]["file1"] == g["file1"][:n] and set(g["file1"][n:]) <= {"0"}, p["name"]
