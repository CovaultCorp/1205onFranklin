from __future__ import annotations

import time

from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal, init_db
from app.models import SyncJob, utcnow


def run_pending_dry_jobs_once() -> int:
    with SessionLocal() as session:
        jobs = session.scalars(select(SyncJob).where(SyncJob.status == "pending")).all()
        for job in jobs:
            job.status = "succeeded"
            job.attempt_count += 1
            job.result_json = {
                "dry_run": True,
                "message": "Phase 1 records proposed actions only; no UniFi writes were attempted.",
            }
            job.completed_at = utcnow()
        session.commit()
        return len(jobs)


def main() -> None:
    init_db()
    settings = get_settings()
    while True:
        run_pending_dry_jobs_once()
        time.sleep(settings.sync_interval_seconds)


if __name__ == "__main__":
    main()

