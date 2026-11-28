"""Server-rendered UI helpers (Jinja2 + htmx, all assets served locally)."""

from pathlib import Path

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm.exc import DetachedInstanceError

from .security import csrf_token

WEB = Path(__file__).resolve().parent.parent / "web"
templates = Jinja2Templates(directory=[str(WEB / "templates")])


def add_template_dir(path: Path):
    """Modules from other packages can ship their own templates."""
    templates.env.loader.searchpath.append(str(path))


def flash(request: Request, msg: str, kind: str = "ok"):
    request.session.setdefault("flash", []).append([kind, msg])


def redirect(url: str, request: Request | None = None) -> RedirectResponse:
    resp = RedirectResponse(url, status_code=303)
    if request is not None and request.headers.get("hx-request"):
        resp.headers["HX-Location"] = url
    return resp


def _nav(request: Request, ctx, site):
    out = {"platform": [], "tenant": [], "site": []}
    op = getattr(request.state, "operator", None)
    for m in request.app.state.modules:
        for item in m.nav:
            if item.scope == "platform" and not (op and op.is_platform_admin):
                continue
            if item.scope != "platform" and ctx is None:
                continue
            if item.scope == "site" and site is None:
                continue
            if item.perm and ctx is not None and not ctx.can(item.perm):
                continue
            path = item.path.format(tenant=ctx.tenant.slug if ctx else "", site=site.id if site else "")
            out[item.scope].append({"label": item.label, "path": path, "order": item.order})
    for v in out.values():
        v.sort(key=lambda i: i["order"])
    return out


def page(request: Request, template: str, *, ctx=None, site=None, status: int = 200, **data):
    from ..modules.sites.models import Site
    op = getattr(request.state, "operator", None)
    try:
        tenants = [m.tenant for m in op.memberships if m.tenant.active] if op else []
    except DetachedInstanceError:          # error pages render after the request's session closed
        tenants = []
    sites = []
    if ctx is not None:
        sites = ctx.db.scalars(select(Site).where(Site.tenant_id == ctx.tenant.id).order_by(Site.name)).all()
    messages = request.session.pop("flash", []) if "flash" in request.session else []
    return templates.TemplateResponse(request, template, status_code=status, context={
        "op": op, "ctx": ctx, "tenant": ctx.tenant if ctx else None, "site": site,
        "tenants": tenants, "sites": sites, "nav": _nav(request, ctx, site),
        "csrf": csrf_token(request), "messages": messages,
        "settings": request.app.state.settings,
        "modules": {m.name for m in request.app.state.modules}, **data})


# ------------------------------------------------------------- form handling

async def form(request: Request) -> dict:
    """Form fields as dict; repeated fields (checkbox groups) as lists."""
    f = await request.form()
    out: dict = {}
    for k in f.keys():
        if k == "csrf_token":
            continue
        vals = f.getlist(k)
        out[k] = vals if len(vals) > 1 or k.endswith("[]") else vals[0]
    return {k.removesuffix("[]"): v for k, v in out.items()}


def error_text(e: Exception) -> str:
    from fastapi import HTTPException
    from pydantic import ValidationError
    from sqlalchemy.exc import IntegrityError
    if isinstance(e, HTTPException):
        return str(e.detail)
    if isinstance(e, ValidationError):
        return "; ".join(f"{'.'.join(str(x) for x in err['loc']) or 'input'}: {err['msg']}"
                         for err in e.errors())
    if isinstance(e, IntegrityError):
        return "conflicts with existing data (duplicate?)"
    return str(e)


def attempt(ctx, request: Request, fn, ok_msg: str | None = None):
    """Run fn in a SAVEPOINT; on a user error roll it back and flash the message.
    Returns (result, ok)."""
    from fastapi import HTTPException
    from pydantic import ValidationError
    from sqlalchemy.exc import IntegrityError
    sp = ctx.db.begin_nested()
    try:
        result = fn()
        ctx.db.flush()
        sp.commit()
    except (HTTPException, ValidationError, IntegrityError, ValueError, KeyError) as e:
        if isinstance(e, HTTPException) and e.status_code == 403:
            raise
        sp.rollback()
        flash(request, error_text(e), "error")
        return None, False
    if ok_msg:
        flash(request, ok_msg)
    return result, True


async def form_body(request: Request) -> dict:
    """Dependency: parsed form (lets the route itself stay sync / threadpooled)."""
    return await form(request)
