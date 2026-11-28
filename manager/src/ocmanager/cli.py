"""ocm — command line for setup and bench workflows.

  ocm init --admin alice                 create the database + first platform admin
  ocm create-tenant hospital "St. Example Hospital" --owner alice
  ocm import-site hospital ../examples/hospital/site.json [--dev-pem ../examples/hospital/dev_management_key.pem]
  ocm serve [--host 127.0.0.1] [--port 8243]
"""

import argparse
import getpass
import json
import sys
from pathlib import Path

from sqlalchemy import select


def _app():
    from .app import create_app
    return create_app()


def _cli_ctx(app, db, tenant_slug, username):
    from fastapi import HTTPException  # noqa: F401
    from starlette.requests import Request

    from .core.models import Membership, Operator, Tenant
    from .core.tenancy import PERMISSIONS, TenantContext
    t = db.scalar(select(Tenant).where(Tenant.slug == tenant_slug))
    if t is None:
        sys.exit(f"unknown tenant {tenant_slug}")
    op = db.scalar(select(Operator).where(Operator.username == username)) if username else \
        db.scalar(select(Operator).join(Membership).where(Membership.tenant_id == t.id, Membership.role == "owner"))
    if op is None:
        sys.exit("no operator (owner) found for this tenant")
    req = Request({"type": "http", "app": app, "headers": [], "client": ("cli", 0), "method": "POST",
                   "path": "/cli", "query_string": b""})
    return TenantContext(db, op, t, "owner", req, PERMISSIONS["owner"])


def main(argv=None):
    ap = argparse.ArgumentParser(prog="ocm", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("init", help="create database, keys and the first platform admin")
    p.add_argument("--admin", required=True)
    p.add_argument("--password", help="default: ask")
    p = sub.add_parser("create-tenant")
    p.add_argument("slug")
    p.add_argument("name")
    p.add_argument("--owner", required=True)
    p = sub.add_parser("import-site", help="import an examples/*/site.json")
    p.add_argument("tenant")
    p.add_argument("site_json", type=Path)
    p.add_argument("--dev-pem", type=Path, help="import the PUBLIC dev test keys (bench) with this signing key")
    p.add_argument("--locks", type=Path, help="also import a locks.local.json")
    p.add_argument("--as", dest="as_user")
    p = sub.add_parser("serve")
    p.add_argument("--host", default=None)
    p.add_argument("--port", type=int, default=8243)
    p.add_argument("--reload", action="store_true")
    args = ap.parse_args(argv)

    if args.cmd == "serve":
        import uvicorn

        from .config import get_settings
        st = get_settings()
        host = args.host or ("127.0.0.1" if st.mode == "local" else "0.0.0.0")
        if st.mode == "server" and host != "127.0.0.1":
            print("server mode: run behind a TLS reverse proxy (cookies are Secure-only)")
        uvicorn.run("ocmanager.app:create_app", factory=True, host=host, port=args.port, reload=args.reload,
                    proxy_headers=True)
        return

    app = _app()
    with app.state.db.sessionmaker() as db:
        _run(args, app, db)
        db.commit()


def _run(args, app, db):
    if True:
        if args.cmd == "init":
            from .modules.platform.service import create_operator
            pw = args.password or getpass.getpass(f"password for {args.admin}: ")
            op = create_operator(db, args.admin, pw, platform_admin=True)
            print(f"platform admin {op.username} created; data in {app.state.settings.data_dir.resolve()}")
        elif args.cmd == "create-tenant":
            from .core.models import Operator
            from .modules.platform.service import create_tenant, set_membership
            owner = db.scalar(select(Operator).where(Operator.username == args.owner))
            if owner is None:
                sys.exit(f"unknown user {args.owner}")
            t = create_tenant(db, args.slug, args.name)
            set_membership(db, t, owner, "owner")
            print(f"tenant {t.slug} created, owner {owner.username}")
        elif args.cmd == "import-site":
            from .modules.sites.service import import_site_json
            ctx = _cli_ctx(app, db, args.tenant, args.as_user)
            pem = args.dev_pem.read_bytes() if args.dev_pem else None
            site = import_site_json(ctx, json.loads(args.site_json.read_text()), pem)
            db.flush()
            print(f"site {site.aid} '{site.name}' imported (id {site.id})"
                  + (" — PUBLIC DEV TEST KEYS" if site.dev_keys else " — fresh keys"))
            if args.locks:
                from .modules.locks.service import import_locks_local
                n = import_locks_local(ctx, site, json.loads(args.locks.read_text()))
                print(f"{n} lock(s) imported")
