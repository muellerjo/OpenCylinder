"""Card inspector: "what does the card on the reader hold?"."""

from fastapi import APIRouter, Depends

from ...core.modules import Module, NavItem
from ...core.tenancy import TenantContext, requires
from ...core.web import error_text, page
from . import service as R

ui = APIRouter()
api = APIRouter(tags=["reader"])
READ = requires("site.read")


def _reader_ready(ctx) -> bool:
    return bool(ctx.request.app.state.settings.pm3_path or getattr(ctx.request.app.state, "card_reader", None))


@ui.get("/t/{tenant}/reader")
def reader_page(ctx: TenantContext = Depends(READ)):
    return page(ctx.request, "reader/page.html", ctx=ctx, ready=_reader_ready(ctx), result=None, error=None)


@ui.post("/t/{tenant}/reader")
def reader_read(ctx: TenantContext = Depends(READ)):
    result, error = None, None
    try:
        result = R.inspect(ctx)
    except Exception as e:  # noqa: BLE001  (reader / subprocess problems are shown, not raised)
        error = error_text(e) or repr(e)
    tpl = "reader/result.html" if ctx.request.headers.get("hx-request") else "reader/page.html"
    return page(ctx.request, tpl, ctx=ctx, ready=_reader_ready(ctx), result=result, error=error)


@api.post("/t/{tenant}/reader/inspect", summary="Read the card on this machine's reader and decode it")
def reader_api(ctx: TenantContext = Depends(READ)):
    r = R.inspect(ctx)
    if not r["present"]:
        return r

    def app_json(a):
        out = {"kind": a["kind"], "aid": a["aid"], "site": a["site"].name if a.get("site") else None,
               "problems": a["problems"]}
        if a["kind"] == "user" and "header" in a:
            out.update(credential_id=a["header"]["credential_id"],
                       person=a["person"].name if a.get("person") else None,
                       entries=a["entries"], valid_until=a["header"]["valid_until"],
                       issued_at=a["header"]["issued_at"], opens_now=[d.number for d in a["opens"]])
        if a.get("bundle"):
            b = a["bundle"]
            out["bundle"] = {k: b[k] for k in ("site_aid", "target_device", "sequence", "issued_at",
                                               "valid_until", "records", "length")}
        if a.get("identity"):
            out["identity"] = a["identity"]
        return out
    return {"present": True, "uid": r["uid"], "type": r["type"], "aids": r["aids"],
            "applications": [app_json(a) for a in r["apps"]]}


MODULE = Module(
    name="reader", title="Card inspector", api=api, ui=ui, requires=["sites", "people", "locks"],
    nav=[NavItem("Card on the reader", "/t/{tenant}/reader", "tenant", "site.read", 20)],
)
