"""Login / logout, own account, personal API tokens."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...core.audit import record
from ...core.models import ApiToken, Operator
from ...core.modules import Module
from ...core.security import (authenticate, current_operator, get_db, hash_password, login_session,
                              new_api_token, throttle, verify_password)
from ...core.web import flash, page, redirect

ui = APIRouter()


@ui.get("/")
def home(request: Request, op: Operator = Depends(current_operator)):
    tenants = [m.tenant for m in op.memberships if m.tenant.active]
    if len(tenants) >= 1:
        return redirect(f"/t/{tenants[0].slug}")
    return redirect("/platform/tenants" if op.is_platform_admin else "/account")


def _no_users(db: Session) -> bool:
    return db.scalar(select(Operator.id).limit(1)) is None


@ui.get("/login")
def login_form(request: Request, next: str = "/", db: Session = Depends(get_db)):
    if _no_users(db):
        return redirect("/setup")
    return page(request, "auth/login.html", next=next if next.startswith("/") else "/")


@ui.get("/setup")
def setup_form(request: Request, db: Session = Depends(get_db)):
    """First start only: create the first admin (and optionally the example site)."""
    if not _no_users(db):
        return redirect("/login")
    return page(request, "auth/setup.html")


@ui.post("/setup")
def setup(request: Request, username: str = Form(...), password: str = Form(...), org: str = Form(...),
          example: str = Form(""), db: Session = Depends(get_db)):
    from pathlib import Path

    from ...core.tenancy import PERMISSIONS, TenantContext
    from ..platform.service import create_operator, create_tenant, set_membership
    if not _no_users(db):
        return redirect("/login")
    try:
        op = create_operator(db, username, password, platform_admin=True, request=request)
        import re
        slug = re.sub(r"[^a-z0-9]+", "-", org.lower()).strip("-")[:48] or "main"
        t = create_tenant(db, slug, org, op, request)
        set_membership(db, t, op, "owner", op, request)
        if example:
            import json

            from ..sites.service import import_site_json
            ex = Path(__file__).resolve().parents[5] / "examples" / "hospital"
            ctx = TenantContext(db, op, t, "owner", request, PERMISSIONS["owner"])
            import_site_json(ctx, json.loads((ex / "site.json").read_text()),
                             (ex / "dev_management_key.pem").read_bytes())
    except HTTPException as e:
        db.rollback()
        flash(request, str(e.detail), "error")
        return redirect("/setup")
    login_session(request, op)
    return redirect(f"/t/{t.slug}")


@ui.post("/login")
def login(request: Request, username: str = Form(...), password: str = Form(...), next: str = Form("/"),
          db: Session = Depends(get_db)):
    key = f"{username.strip().lower()}|{request.client.host if request.client else ''}"
    if throttle.blocked(key):
        flash(request, "Too many failed logins — wait a few minutes.", "error")
        return redirect("/login")
    op = authenticate(db, username, password)
    if op is None:
        throttle.fail(key)
        record(db, "login.failed", username[:64], request=request)
        flash(request, "Wrong user name or password.", "error")
        return redirect("/login")
    throttle.reset(key)
    login_session(request, op)
    record(db, "login", op.username, operator=op, request=request)
    return redirect(next if next.startswith("/") and not next.startswith("//") else "/")


@ui.post("/logout")
def logout(request: Request):
    request.session.clear()
    return redirect("/login")


@ui.get("/account")
def account(request: Request, op: Operator = Depends(current_operator), db: Session = Depends(get_db)):
    tokens = db.scalars(select(ApiToken).where(ApiToken.operator_id == op.id).order_by(ApiToken.id)).all()
    new_token = request.session.pop("new_token", None)
    return page(request, "auth/account.html", tokens=tokens, new_token=new_token)


@ui.post("/account/password")
def change_password(request: Request, old: str = Form(...), new: str = Form(...), new2: str = Form(...),
                    op: Operator = Depends(current_operator), db: Session = Depends(get_db)):
    if not verify_password(op, old):
        flash(request, "Current password is wrong.", "error")
    elif new != new2:
        flash(request, "The new passwords differ.", "error")
    else:
        try:
            op.password_hash = hash_password(new)
        except ValueError as e:
            flash(request, str(e), "error")
            return redirect("/account")
        op.session_version += 1                # log out all other sessions
        login_session(request, op)
        record(db, "account.password", op.username, operator=op, request=request)
        flash(request, "Password changed; other sessions are logged out.")
    return redirect("/account")


@ui.post("/account/tokens")
def add_token(request: Request, name: str = Form(...), days: int = Form(90),
              op: Operator = Depends(current_operator), db: Session = Depends(get_db)):
    tok, h = new_api_token()
    db.add(ApiToken(operator_id=op.id, name=name[:100], token_hash=h, prefix=tok[:12],
                    expires_at=datetime.now(timezone.utc) + timedelta(days=max(1, min(days, 365)))))
    record(db, "token.create", name[:100], operator=op, request=request)
    request.session["new_token"] = tok
    return redirect("/account")


@ui.post("/account/tokens/{token_id}/delete")
def delete_token(request: Request, token_id: int, op: Operator = Depends(current_operator),
                 db: Session = Depends(get_db)):
    t = db.get(ApiToken, token_id)
    if t and t.operator_id == op.id:
        record(db, "token.delete", t.name, operator=op, request=request)
        db.delete(t)
    return redirect("/account")


MODULE = Module(name="auth", title="Login & account", ui=ui)
