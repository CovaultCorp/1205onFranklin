from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import SyncJob


def queue_phase1_reconcile_stub(session: Session) -> SyncJob:
    job = SyncJob(
        job_type="dry_run",
        status="pending",
        proposed_actions={
            "phase": 1,
            "message": "Read-only reconciliation is reserved for Phase 2. No UniFi writes will be attempted.",
        },
    )
    session.add(job)
    session.flush()
    return job

