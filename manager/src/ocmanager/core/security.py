"""Authentication: password hashing, session cookie, API tokens, CSRF, login throttling."""

import hashlib
import hmac
import secrets
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import utcnow
from .models import ApiToken, Operator

_ph = PasswordHasher()
TOKEN_PREFIX = "ocm_"


class NotAuthenticated(Exception):
    """Handled in app.py: redirect to /login (HTML) or 401 (API)."""


# ------------------------------------------------------------------ passwords

def hash_password(pw: str) -> str:
    if len(pw) < 10:
        raise ValueError("password must have at least 10 characters")
    return _ph.hash(pw)


def verify_password(op: Operator, pw: str) -> bool:
    try:
        return _ph.verify(op.password_hash, pw)
    except (VerifyMismatchError, InvalidHashError):
        return False


_DUMMY = _ph.hash("timing-equaliser-not-a-password")


def authenticate(db: Session, username: str, pw: str) -> Operator | None:
    op = db.scalar(select(Operator).where(Operator.username == username.strip().lower()))
    if op is None:
        try:
            _ph.verify(_DUMMY, pw)          # same cost as a real check
        except VerifyMismatchError:
            pass
        return None
    if not op.active or not verify_password(op, pw):
        return None
    if _ph.check_needs_rehash(op.password_hash):
        op.password_hash = _ph.hash(pw)
    op.last_login_at = utcnow()
    return op


class LoginThrottle:
    """At most `limit` failed logins per key in `window` seconds (in-memory, per process)."""

    def __init__(self, limit=8, window=300):
        self.limit, self.window = limit, window
        self.fails: dict[str, deque] = defaultdict(deque)

    def blocked(self, key: str) -> bool:
        q = self.fails[key]
        while q and q[0] < time.monotonic() - self.window:
            q.popleft()
        return len(q) >= self.limit

    def fail(self, key: str):
        self.fails[key].append(time.monotonic())

    def reset(self, key: str):
        self.fails.pop(key, None)


throttle = LoginThrottle()


# ------------------------------------------------------------------- sessions

def login_session(request: Request, op: Operator):
    request.session.clear()
    request.session.update({"uid": op.id, "sv": op.session_version, "csrf": secrets.token_urlsafe(24),
                            "t": int(time.time())})


def csrf_token(request: Request) -> str:
    tok = request.session.get("csrf")
    if not tok:
        tok = request.session["csrf"] = secrets.token_urlsafe(24)
    return tok


# ----------------------------------------------------------------- API tokens

def new_api_token() -> tuple[str, str]:
    """-> (token shown once, sha256 hex stored)."""
    tok = TOKEN_PREFIX + secrets.token_urlsafe(32)
    return tok, hashlib.sha256(tok.encode()).hexdigest()


def _bearer(request: Request) -> str | None:
    h = request.headers.get("authorization", "")
    return h[7:].strip() if h.lower().startswith("bearer ") else None


# --------------------------------------------------------------- dependencies

def get_db(request: Request):
    yield from request.app.state.db.session()


def current_operator(request: Request, db: Session = Depends(get_db)) -> Operator:
    tok = _bearer(request)
    if tok:
        row = db.scalar(select(ApiToken).where(
            ApiToken.token_hash == hashlib.sha256(tok.encode()).hexdigest()))
        now = datetime.now(timezone.utc)
        if row is None or not row.operator.active or \
                (row.expires_at and row.expires_at.replace(tzinfo=timezone.utc) < now):
            raise HTTPException(401, "invalid API token")
        row.last_used_at = now
        request.state.via_token = True
        request.state.operator = row.operator
        return row.operator
    uid = request.session.get("uid")
    if uid is None:
        raise NotAuthenticated()
    op = db.get(Operator, uid)
    if op is None or not op.active or request.session.get("sv") != op.session_version:
        request.session.clear()
        raise NotAuthenticated()
    max_age = request.app.state.settings.session_max_age
    if time.time() - request.session.get("t", 0) > max_age:
        request.session.clear()
        raise NotAuthenticated()
    request.state.operator = op
    return op


def require_platform_admin(op: Operator = Depends(current_operator)) -> Operator:
    if not op.is_platform_admin:
        raise HTTPException(403, "platform admin only")
    return op


async def csrf_protect(request: Request):
    """Unsafe methods with a session cookie need the CSRF token (header or form field)."""
    if request.method in ("GET", "HEAD", "OPTIONS") or _bearer(request):
        return
    expected = request.session.get("csrf")
    sent = request.headers.get("x-csrf-token")
    if sent is None and request.headers.get("content-type", "").startswith(
            ("application/x-www-form-urlencoded", "multipart/form-data")):
        sent = (await request.form()).get("csrf_token")
    if not expected or not sent or not hmac.compare_digest(str(sent), expected):
        raise HTTPException(403, "CSRF token missing or wrong — reload the page")
