"""Append-only audit trail. Every write that matters for security goes here."""

from sqlalchemy.orm import Session

from .models import AuditEvent


def record(db: Session, action: str, target: str = "", detail: dict | None = None, *,
           tenant=None, operator=None, request=None):
    ip = ""
    if request is not None and request.client:
        ip = request.client.host
    db.add(AuditEvent(tenant_id=tenant.id if tenant else None,
                      operator_id=operator.id if operator else None,
                      operator_name=operator.username if operator else "system",
                      action=action, target=target[:200], detail=detail or {}, ip=ip))
