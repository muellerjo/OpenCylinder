from fastapi import APIRouter, Depends, Form

from ...core.tenancy import TenantContext, requires
from ...core.web import attempt, page, redirect
from ..locks.models import Lock
from ..people.models import Person
from . import service as J
from .models import JOB_KINDS, CardJob

router = APIRouter()
READ, ISSUE, BUNDLES, LOCKS = (requires("site.read"), requires("cards.issue"), requires("bundles.issue"),
                               requires("locks.manage"))
SITE = "/t/{tenant}/s/{site_id}"


def _url(ctx, site, sub=""):
    return f"/t/{ctx.tenant.slug}/s/{site.id}/cards{sub}"


@router.get(SITE + "/cards")
def jobs(site_id: int, ctx: TenantContext = Depends(READ)):
    site = ctx.site(site_id)
    return page(ctx.request, "cards/list.html", ctx=ctx, site=site, jobs=J.list_jobs(ctx, site), kinds=JOB_KINDS)


@router.post(SITE + "/cards/user/{person_id}")
def user_card(site_id: int, person_id: int, ctx: TenantContext = Depends(ISSUE)):
    site = ctx.site(site_id)
    p = ctx.get(Person, person_id, site)
    job, ok = attempt(ctx, ctx.request, lambda: J.issue_user_card(ctx, site, p), "Card job prepared.")
    return redirect(_url(ctx, site, f"/{job.id}") if ok else
                    f"/t/{ctx.tenant.slug}/s/{site.id}/people/{p.id}", ctx.request)


@router.post(SITE + "/cards/maintenance")
def maintenance(site_id: int, valid_days: float = Form(2), blacklist_only: str = Form(""),
                ctx: TenantContext = Depends(BUNDLES)):
    site = ctx.site(site_id)
    job, ok = attempt(ctx, ctx.request, lambda: J.issue_maintenance(ctx, site, valid_days, bool(blacklist_only)),
                      "Signed bundle prepared.")
    return redirect(_url(ctx, site, f"/{job.id}" if ok else ""), ctx.request)


@router.post(SITE + "/cards/lock/{lock_id}")
def targeted(site_id: int, lock_id: int, kind: str = Form(...), door: str = Form(""),
             valid_days: float = Form(2), ctx: TenantContext = Depends(LOCKS)):
    ctx.require("bundles.issue")
    site = ctx.site(site_id)
    lk = ctx.get(Lock, lock_id, site)
    job, ok = attempt(ctx, ctx.request, lambda: J.issue_targeted(
        ctx, site, lk, kind, int(door) if door else None, valid_days), "Signed bundle for this lock prepared.")
    return redirect(_url(ctx, site, f"/{job.id}") if ok else
                    f"/t/{ctx.tenant.slug}/s/{site.id}/locks/{lk.id}", ctx.request)


@router.get(SITE + "/cards/{job_id}")
def job(site_id: int, job_id: int, uid: str = "", ctx: TenantContext = Depends(READ)):
    site = ctx.site(site_id)
    jb = ctx.get(CardJob, job_id, site)
    steps, plan_error = None, None
    if ctx.can("cards.issue") and (uid or not J.needs_uid(jb)):
        try:
            steps = J.plan(ctx, site, jb, uid.strip() or None)
            ctx.audit("card.plan", f"site {site.aid} job {jb.id}", uid=uid)
        except Exception as e:  # noqa: BLE001
            plan_error = str(getattr(e, "detail", e))
    return page(ctx.request, "cards/job.html", ctx=ctx, site=site, job=jb, kinds=JOB_KINDS, uid=uid,
                steps=steps, plan_error=plan_error, needs_uid=J.needs_uid(jb), pm3=J.pm3_available(ctx),
                results=None)


@router.post(SITE + "/cards/{job_id}/run")
def run(site_id: int, job_id: int, confirm_format: str = Form(""), ctx: TenantContext = Depends(ISSUE)):
    site = ctx.site(site_id)
    jb = ctx.get(CardJob, job_id, site)
    res, ok = attempt(ctx, ctx.request, lambda: J.run_local(ctx, site, jb, bool(confirm_format)))
    return page(ctx.request, "cards/job.html", ctx=ctx, site=site, job=jb, kinds=JOB_KINDS, uid=jb.card_uid or "",
                steps=None, plan_error=None, needs_uid=J.needs_uid(jb), pm3=True,
                results=res[1] if ok else None, run_ok=res[0] if ok else False)


@router.post(SITE + "/cards/{job_id}/written")
def written(site_id: int, job_id: int, uid: str = Form(""), ctx: TenantContext = Depends(ISSUE)):
    site = ctx.site(site_id)
    jb = ctx.get(CardJob, job_id, site)
    attempt(ctx, ctx.request, lambda: J.mark_written(ctx, site, jb, uid.strip() or None, "marked by hand"),
            "Marked as written.")
    return redirect(_url(ctx, site, f"/{jb.id}"), ctx.request)


@router.post(SITE + "/cards/{job_id}/cancel")
def cancel(site_id: int, job_id: int, ctx: TenantContext = Depends(ISSUE)):
    site = ctx.site(site_id)
    jb = ctx.get(CardJob, job_id, site)
    attempt(ctx, ctx.request, lambda: J.cancel(ctx, site, jb), "Job cancelled.")
    return redirect(_url(ctx, site, f"/{jb.id}"), ctx.request)
