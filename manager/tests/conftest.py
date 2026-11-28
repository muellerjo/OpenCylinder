import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ocmanager.app import create_app
from ocmanager.config import Settings

REPO = Path(__file__).resolve().parents[2]
HOSPITAL = REPO / "examples" / "hospital"
PW = "correct-horse-battery"


@pytest.fixture
def app(tmp_path):
    return create_app(Settings(data_dir=tmp_path, allow_dev_keys=True))


def csrf_of(client: TestClient) -> str:
    html = client.get("/login").text
    return re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)


class Browser:
    """TestClient wrapper that sends the CSRF token like the htmx pages do."""

    def __init__(self, app):
        self.c = TestClient(app, base_url="http://localhost")
        self.token = None

    def login(self, user, pw=PW):
        self.token = csrf_of(self.c)
        r = self.c.post("/login", data={"username": user, "password": pw, "csrf_token": self.token},
                        follow_redirects=False)
        assert r.status_code == 303, r.text
        self.token = re.search(r'name="csrf-token" content="([^"]+)"', self.c.get("/account").text).group(1)
        return self

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, data=None, files=None, **kw):
        data = dict(data or {})
        data["csrf_token"] = self.token
        return self.c.post(url, data=data, files=files, follow_redirects=kw.pop("follow", True), **kw)

    def api(self, method, url, **kw):
        return self.c.request(method, "/api/v1" + url, headers={"X-CSRF-Token": self.token}, **kw)


def make_user(app, name, admin=False):
    from ocmanager.modules.platform.service import create_operator
    with app.state.db.sessionmaker() as db:
        create_operator(db, name, PW, platform_admin=admin)
        db.commit()


@pytest.fixture
def admin(app):
    make_user(app, "alice", admin=True)
    return Browser(app).login("alice")


@pytest.fixture
def hospital(app, admin):
    """Tenant 'hospital' with the example site imported using the public dev keys."""
    admin.post("/platform/tenants", {"slug": "hospital", "name": "St. Example", "owner": "alice"})
    r = admin.post("/t/hospital/sites/import",
                   files={"file": ("site.json", (HOSPITAL / "site.json").read_bytes(), "application/json"),
                          "dev_pem": ("k.pem", (HOSPITAL / "dev_management_key.pem").read_bytes(), "text/plain")})
    assert r.status_code == 200, r.text
    site_id = int(re.search(r"/t/hospital/s/(\d+)", str(r.url)).group(1))
    return site_id
