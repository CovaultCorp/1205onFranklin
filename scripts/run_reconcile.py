from __future__ import annotations

import asyncio
import json

from app.db import SessionLocal, init_db
from app.reconcile import run_unifi_reconciliation


async def main() -> None:
    init_db()
    with SessionLocal() as session:
        job, summary = await run_unifi_reconciliation(session)
        session.commit()
        print(json.dumps({"sync_job_id": job.id, **summary.as_dict()}, indent=2, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(main())
