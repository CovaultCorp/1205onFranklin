# Building Access Registry

Dockerized internal FastAPI app for managing building access companies, suites, users, access requests, approvals, reports, verification links, and dry-run UniFi Access sync planning.

The local PostgreSQL database is the source of truth. UniFi Access is a target access-control system, but Phase 1 and Phase 2 do not write to UniFi.

## Phase 1 Scope

Implemented:

- Local registry models for accounts, companies, suites, company-suite occupancy, users, access profiles, access requests, UniFi snapshots, sync jobs, conflicts, reports, verification requests, and audit logs.
- First-admin setup and local admin login.
- Public access request form.
- Admin dashboard and registry management pages.
- Request approval/denial/needs-info workflow.
- Approval queues `SyncJob` dry-run records instead of calling UniFi write APIs.
- Report preview, CSV export, report run records, and email preview files when `ENABLE_EMAIL=false`.
- Verification links that allow recipients to mark a report accurate or request changes.
- Docker Compose / Portainer stack with `web`, `worker`, and `db`.
- Existing read-only UniFi exporter code is preserved under `src/`.

Not implemented in Phase 1:

- UniFi writes.
- NFC, PIN, Touch Pass, or raw credential provisioning.
- User deletion in UniFi.
- Read-only reconciliation beyond a Phase 1 dry-run placeholder.
- Scheduled reports.

## Phase 2 Scope

Implemented:

- Paginated read-only UniFi Access API methods:
  - `list_users(expand_access_policy=True)`
  - `get_user(user_id)`
  - `list_access_policies()`
  - `list_user_groups()`
- Read-only reconciliation from UniFi into local `UnifiUser` snapshots.
- Matching by existing UniFi mapping, then employee number, then email.
- Conflict detection for unmatched active users, missing company/suite assignments, status mismatch, name/email mismatch, access policy mismatch, duplicate UniFi email/employee number, inactive company, and inactive suite.
- Idempotent open-conflict creation on repeated reconciliation runs.
- Dry-run `SyncJob(job_type="reconcile")` records containing proposed actions only.
- Admin “Run UniFi Reconciliation” action, reconciliation summary, improved conflict view, and improved sync job view.
- CLI entry point: `python scripts/run_reconcile.py`.

Not implemented in Phase 2:

- UniFi create, update, deactivate, delete, policy assignment, or credential provisioning.
- NFC, PIN, Touch Pass, or raw credential storage.
- Automatic conflict resolution.
- Scheduled reconciliation.

## Required Environment Variables

Core:

```text
DATABASE_URL=postgresql+psycopg://building_access:change_me@db:5432/building_access_registry
POSTGRES_PASSWORD=change_me
APP_SECRET_KEY=change_me
ADMIN_EMAIL=admin@example.com
ADMIN_INITIAL_PASSWORD=
PUBLIC_BASE_URL=http://localhost:8080
AUTH_MODE=local
TRUST_PROXY_HEADERS=false
LOG_LEVEL=INFO
EXPORT_DIR=/app/exports
```

UniFi:

```text
UNIFI_ACCESS_BASE_URL=https://192.168.1.1:12445
UNIFI_ACCESS_TOKEN=
UNIFI_ACCESS_VERIFY_SSL=false
UNIFI_ACCESS_PAGE_SIZE=100
ENABLE_WRITES=false
SYNC_INTERVAL_SECONDS=300
```

Email:

```text
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM_EMAIL=
SMTP_FROM_NAME=Building Access Registry
SMTP_USE_TLS=true
ENABLE_EMAIL=false
```

Reports:

```text
REPORT_DEFAULT_RECIPIENTS=
REPORT_VERIFICATION_EXPIRATION_DAYS=14
ENABLE_SCHEDULED_REPORTS=false
REPORT_SCHEDULE_CRON=0 8 1 * *
REPORT_TIMEZONE=America/New_York
REPORT_DEFAULT_TYPE=full_building_access
```

Do not commit `.env` files or secrets.

## Run Locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DATABASE_URL="sqlite:///./dev.db"
$env:EXPORT_DIR="./exports"
uvicorn app.main:app --reload --port 8080
```

Open `http://localhost:8080/setup-admin` to create the first admin.

Run read-only reconciliation from the command line:

```powershell
python scripts/run_reconcile.py
```

## Run With Docker Compose

```powershell
docker compose build
docker compose up -d
docker compose logs --tail=100 web
docker compose logs --tail=100 worker
```

The app listens on port `8080`. PostgreSQL data is stored in the Docker named volume `building_access_registry_pgdata`. Reports, previews, and exports are written to `/app/exports`.

## Portainer

Deploy the repository as a Git-backed stack using `docker-compose.yml` or `portainer-stack.yml`.

Expected services:

- `web`
- `worker`
- `db`

Expected export bind mount:

```text
/mnt/unas/docker-exports/building-access-registry:/app/exports
```

Supply environment variables in Portainer stack settings. Keep `ENABLE_WRITES=false` unless a future phase explicitly implements and approves UniFi write behavior.

## Safety Warnings

- `ENABLE_WRITES=false` is the default.
- Phase 1 and Phase 2 write methods in `app/unifi_client.py` raise unless writes are enabled, then raise `NotImplementedError` because UniFi write behavior is intentionally not implemented.
- The UniFi API token and SMTP password are server-side only.
- Email disabled mode writes preview files to `EXPORT_DIR/email_previews`.
- Approval creates `SyncJob` records and audit logs; it does not provision directly.
- Reconciliation creates local snapshots, open conflicts, and dry-run proposed actions only. It does not call UniFi write APIs.

## Tests

```powershell
pytest
```

The test suite covers the preserved exporter behavior, focused Phase 1 application behavior, and Phase 2 reconciliation behavior.
