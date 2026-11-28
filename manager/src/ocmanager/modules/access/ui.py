from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends

from ...core.tenancy import TenantContext, requires
from ...core.web import page
from ...protocol import decision as D
from . import service as A

router = APIRouter()
api = APIRouter(prefix="/t/{tenant}/sites/{site_id}", tags=["access"])
READ = requires("site.read")
SYMBOL = {D.OPEN: "✓", D.NO_RIGHT: "·", D.PROFILE: "t", D.EXPIRED: "E", D.BLACKLISTED: "B", D.NO_TIME: "?"}


@router.get("/t/{tenant}/s/{site_id}/access")
def access(site_id: int, at: str = "", time_unknown: str = "", door: str = "",
           ctx: TenantContext = Depends(READ)):
    site = ctx.site(site_id)
    now = None if time_unknown else A.parse_at(site, at or None)
    doors, rows = A.matrix(ctx, site, now, int(door) if door else None)
    when = "time UNKNOWN" if now is None else \
        datetime.fromtimestamp(now, ZoneInfo(site.timezone)).strftime("%a %Y-%m-%d %H:%M %Z")
    tpl = "access/matrix_body.html" if ctx.request.headers.get("hx-request") and \
        ctx.request.headers.get("hx-target") == "matrix" else "access/matrix.html"
    return page(ctx.request, tpl, ctx=ctx, site=site, doors=doors, rows=rows, when=when, at=at,
                time_unknown=time_unknown, door=door, symbol=SYMBOL, all_doors=site.doors)


@api.get("/access-matrix", summary="Decision of every door for every person (lock logic on real card bytes)")
def access_api(site_id: int, at: str = "", time_unknown: bool = False, ctx: TenantContext = Depends(READ)):
    site = ctx.site(site_id)
    now = None if time_unknown else A.parse_at(site, at or None)
    doors, rows = A.matrix(ctx, site, now)
    return {"at": now, "doors": [d.number for d in doors],
            "rows": [{"person": r["person"].name,
                      "credential": r["credential"].number if r["credential"] else None,
                      "error": r["error"],
                      "decisions": [{"result": s, "reason": why} for s, why in r["cells"]]} for r in rows]}
