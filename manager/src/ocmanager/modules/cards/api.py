"""JSON API for card jobs — also what a remote encoder agent would use:
prepare a job in the UI, then GET its plan with the card UID and run it locally."""

from fastapi import APIRouter, Depends

from ...core.tenancy import TenantContext, requires
from ..locks.models import Lock
from ..people.models import Person
from . import service as J
from .models import CardJob
from .schemas import JobOut, MaintenanceIn, PlanIn, TargetedIn, WrittenIn

router = APIRouter(prefix="/t/{tenant}/sites/{site_id}/cards", tags=["cards"])
READ, ISSUE, BUNDLES, LOCKS = (requires("site.read"), requires("cards.issue"), requires("bundles.issue"),
                               requires("locks.manage"))


@router.get("", response_model=list[JobOut])
def jobs(site_id: int, ctx: TenantContext = Depends(READ)):
    return J.list_jobs(ctx, ctx.site(site_id))


@router.post("/user/{person_id}", response_model=JobOut, status_code=201)
def user_card(site_id: int, person_id: int, ctx: TenantContext = Depends(ISSUE)):
    site = ctx.site(site_id)
    return J.issue_user_card(ctx, site, ctx.get(Person, person_id, site))


@router.post("/maintenance", response_model=JobOut, status_code=201)
def maintenance(site_id: int, data: MaintenanceIn, ctx: TenantContext = Depends(BUNDLES)):
    return J.issue_maintenance(ctx, ctx.site(site_id), data.valid_days, data.blacklist_only)


@router.post("/lock/{lock_id}", response_model=JobOut, status_code=201)
def targeted(site_id: int, lock_id: int, data: TargetedIn, ctx: TenantContext = Depends(LOCKS)):
    ctx.require("bundles.issue")
    site = ctx.site(site_id)
    return J.issue_targeted(ctx, site, ctx.get(Lock, lock_id, site), data.kind, data.door, data.valid_days)


@router.post("/{job_id}/plan", summary="Proxmark3 commands for this job and card (contains per-card keys)")
def plan(site_id: int, job_id: int, data: PlanIn, ctx: TenantContext = Depends(ISSUE)):
    site = ctx.site(site_id)
    job = ctx.get(CardJob, job_id, site)
    ctx.audit("card.plan", f"site {site.aid} job {job.id}", uid=data.uid)
    return [s.as_dict() for s in J.plan(ctx, site, job, data.uid, data.app_exists)]


@router.post("/{job_id}/written", response_model=JobOut)
def written(site_id: int, job_id: int, data: WrittenIn, ctx: TenantContext = Depends(ISSUE)):
    site = ctx.site(site_id)
    job = ctx.get(CardJob, job_id, site)
    J.mark_written(ctx, site, job, data.uid, data.log)
    return job
