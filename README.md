# Building Access Registry

ENTRY POINT is the hosted access registry and operations dashboard for 1205 on Franklin.

## 2026 Vercel database update

The app is now structured for Vercel Postgres / Neon while preserving the existing clean backend ORM:

- ORM: SQLAlchemy 2.x
- Migrations: Alembic
- Frontend data flow: Next.js dashboard -> FastAPI JSON API -> PostgreSQL
- Production database recommendation: Vercel Postgres / Neon
- Optional migration URL: `DIRECT_URL`

There is no Prisma schema in this repository. Do not add Prisma just to use Vercel Postgres; the current SQLAlchemy layer works with Neon PostgreSQL URLs.

Before replacing any existing Railway database, run diagnostics and export anything that is not recoverable from UniFi Access or source files:

```bash
python scripts/diagnose_users.py
python scripts/import_unifi_old_dump.py all_unifi_users.csv --dry-run
```

The local workspace `dev.db` checked during this update contained no companies, suites, users, assignments, UniFi snapshots, or Alembic version state. That does not prove the remote Railway database is empty.

Local development reset:

```bash
python scripts/reset_local_db.py --yes
python scripts/seed_entrypoint.py
```

Vercel/Neon environment variables:

```text
DATABASE_URL=postgresql://... pooled Neon/Vercel URL ...
DIRECT_URL=postgresql://... optional direct Neon URL for Alembic ...
ENTRYPOINT_AGENT_TOKEN=replace_with_random_bearer_token
APP_SECRET_KEY=replace_me
PUBLIC_BASE_URL=https://your-vercel-app.example
BACKEND_API_URL=https://your-fastapi-backend.example
ENABLE_WRITES=false
```

Local LAN UniFi agent variables:

```text
ENTRYPOINT_AGENT_TOKEN=same_random_bearer_token_configured_in_hosted_app
ENTRYPOINT_API_BASE_URL=https://your-hosted-entry-point.example
UNIFI_ACCESS_BASE_URL=https://192.168.1.1:12445
# Optional alternative to UNIFI_ACCESS_BASE_URL. Hostnames are expanded to https://host:12445.
UNIFI_ACCESS_HOST=192.168.1.1
UNIFI_ACCESS_TOKEN=replace_me
UNIFI_ACCESS_VERIFY_SSL=false
UNIFI_ACCESS_PAGE_SIZE=100
UNIFI_REQUEST_TIMEOUT_SECONDS=30
UNIFI_REQUEST_RETRIES=3
UNIFI_AGENT_NAME=1205-local-lan-agent
UNIFI_SNAPSHOT_SOURCE=local_lan_agent
SYNC_INTERVAL_SECONDS=300
```

The hosted app accepts read-only agent snapshots at `POST /api/agent/snapshots`. It upserts UniFi users, access policies, user groups, doors, and door groups by stable UniFi IDs, stores normalized fields, stores sanitized raw JSON payloads, and records sync runs/logs. It does not write to UniFi Access.

Run one local sync:

```bash
python scripts/unifi_access_agent.py --once
```

Run continuously:

```bash
python scripts/unifi_access_agent.py
```

Portainer/local Docker deployment can run the optional `unifi-agent` service from `docker-compose.yml` or `portainer-stack.yml`. For a hosted Railway/Vercel app, set `ENTRYPOINT_API_BASE_URL` to the hosted FastAPI URL and keep `ENTRYPOINT_AGENT_TOKEN` identical on the hosted backend and local agent. The agent container must run on a network that can reach the UniFi Access console on port `12445`.

UniFi Access API notes from the vendor documentation:

- Create the API token in the UniFi Access application console under Access settings, General, Advanced, API Token. Copy it at creation time and store it only in server or local-agent environment variables.
- Required read-only scopes for Phase 1 are `view:user`, `view:policy`, and `view:space`. User groups require UniFi Access 2.2.6 or later.
- The local API is HTTPS on the UniFi console host at port `12445`, for example `https://192.168.1.1:12445`.
- UniFi Access commonly uses a self-signed local certificate. Set `UNIFI_ACCESS_VERIFY_SSL=false` only as an explicit local-LAN decision.
- The developer API requires UniFi Access 1.9.1 or later and is not available after upgrading to Identity Enterprise.

Data flow:

```text
UniFi Access on building LAN -> local sync agent -> Entry Point /api/agent/snapshots -> PostgreSQL -> dashboard users page
```

Dockerized internal FastAPI app for managing building access companies, suites, users, access requests, approvals, reports, verification links, and dry-run UniFi Access sync planning. The repository now includes a split Next.js dashboard frontend under `frontend/` while preserving the existing Jinja admin UI.

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
- Split dashboard frontend service built with Next.js, TypeScript, NextUI, dark/light mode, sidebar navigation, cards, tables, and forms.
- JSON API endpoints under `/api` for the Next.js dashboard, while the existing Jinja routes remain available.
- Existing read-only UniFi exporter code is preserved under `src/`.

Not implemented in Phase 1:

- UniFi writes.
- NFC, PIN, Touch Pass, or raw credential provisioning.
- User deletion in UniFi.
- Local LAN read-only UniFi Access snapshot agent and hosted ingestion endpoint.
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
- Admin "Run UniFi Reconciliation" action, reconciliation summary, improved conflict view, improved sync job view, and reviewable import batches for proposed local registry changes.
- CLI entry point: `python scripts/run_reconcile.py`.
- Local-only bootstrap CSV and reference ZIP workflow with preview/commit review batches to promote unlinked UniFi snapshots, update linked local users, and store desired UniFi Access Policy/User Group choices.
- Exporter-compatible UniFi snapshot normalization, including non-admin email fallbacks, suite number derivation, policy/group names, NFC counts, Touch Pass status/activity, and license plate counts.
- Reconciliation enriches `/users` list results with read-only per-user detail payloads before storing snapshots, which is required when UniFi omits non-admin email fields from the list response.

Not implemented in Phase 2:

- UniFi create, update, deactivate, delete, policy assignment, or credential provisioning.
- NFC, PIN, Touch Pass, or raw credential storage.
- Automatic conflict resolution.
- Scheduled reconciliation.

## Bootstrap UniFi Users

After running read-only reconciliation, go to:

```text
/admin/bootstrap
```

Workflow:

1. Run UniFi reconciliation so local `UnifiUser` snapshots are current.
2. Download `all_unifi_users.csv` from `/admin/bootstrap/export`.
3. Optionally download the reference ZIP from `/admin/bootstrap/reference-export`.
4. Use `companies.csv`, `suites.csv`, `unifi_access_policies.csv`, and `unifi_user_groups.csv` as lookup references.
5. Fill in `promote=yes` for unlinked UniFi users to create or link local registry users.
6. Fill in `update_existing=yes` for linked users whose local registry fields should be updated.
7. Assign each imported row to existing local Company and Suite records, and desired UniFi Access Policy/User Group values, using either IDs or names.
8. Use `local_suite_id` or `local_suite_number` for the local registry suite. The exported `suite_number` column is the UniFi-derived compatibility value and can also be used by import when the local suite column is blank.
9. Upload a small test batch first, review the generated import batch, then commit it.

The reference ZIP contains:

```text
companies.csv
suites.csv
all_unifi_users.csv
unifi_access_policies.csv
unifi_user_groups.csv
```

CSV import:

- Creates an `ImportBatch` preview first; local `User`, `UserSuiteAssignment`, and snapshot links are not changed until an admin clicks Commit.
- Shows create/update/link/skip/error counts plus row-level before/after diffs.
- Highlights changed fields with `.field-changed`, `.diff-before`, and `.diff-after`.
- Blocks commit when any row has validation errors. Cancel leaves local registry records unchanged.
- Creates local `User` records only when no matching user exists.
- Matches existing local users by employee number, then email to avoid duplicates.
- Updates linked local users only when `update_existing=yes`.
- Skips rows where both `promote` and `update_existing` are blank.
- Resolves `company_id` or `company_name`.
- Resolves `local_suite_id`, `local_suite_number`, or the old exporter `suite_number`.
- Resolves desired UniFi Access Policy/User Group selections by ID or by name.
- Rejects rows with missing or ambiguous name lookups.
- Sets `company_id`, `primary_suite_id`, `desired_unifi_access_policy_ids`, and `desired_unifi_user_group_ids`.
- Creates a primary `UserSuiteAssignment`.
- Links the `UnifiUser` snapshot to the local user.
- Writes audit logs.
- Does not call UniFi write APIs.

Reconciliation still updates raw observed `UnifiUser` snapshots automatically. Proposed local registry work from unmatched UniFi users is placed in an import batch for admin review instead of being applied automatically.

UniFi Access does not use the app's internal `AccessProfile` field. Access Profiles remain available as optional local templates for other workflows, but the bootstrap master sheet uses the user-facing Company, Suite, UniFi Access Policy, and UniFi User Group terms.

Suite number normalization prefers explicit UniFi fields `suite_number`, `suiteNumber`, or `suite`. If none is present, the app falls back to the first three digits found in `employee_number`, matching the older exporter behavior used by the current building workflow.

After deploying normalization changes, rerun UniFi reconciliation before exporting bootstrap CSVs. Existing snapshot rows keep their previous normalized values until reconciliation refreshes them from UniFi.

## Import Old UniFi Dump

For the older `all_unifi_users.csv` format with columns `Name, Email, Company, Suite, Status`, use the safe importer. It is a dry run by default:

```powershell
python scripts/import_unifi_old_dump.py all_unifi_users.csv --dry-run
python scripts/import_unifi_old_dump.py all_unifi_users.csv --commit
python scripts/import_unifi_old_dump.py all_unifi_users.csv --commit --placeholder-emails
```

Rows with blank emails still create/update `UnifiUser` snapshots. Local `User` records are created only when a valid email exists, unless `--placeholder-emails` is passed. Placeholder emails are deterministic, using:

```text
unifi-{slugified-name}-{row-number}@placeholder.local
```

The importer uses the app's SQLAlchemy models and active `DATABASE_URL`; it does not hardcode credentials, drop tables, truncate tables, or reset production data. The command is idempotent and safe to rerun. It prints the connected database host/name with the password hidden, previews all create/update/reuse counts, and requires explicit confirmation for `--commit` unless `--yes` is supplied.

### Railway legacy UniFi import

Upload or place `all_unifi_users.csv` where the Railway one-off command can read it, then run a dry run first:

```bash
railway run python scripts/import_unifi_old_dump.py all_unifi_users.csv --dry-run
```

If the preview looks correct, commit with noninteractive confirmation:

```bash
railway run python scripts/import_unifi_old_dump.py all_unifi_users.csv --commit --yes
```

To create local users for blank-email rows with deterministic placeholder emails:

```bash
railway run python scripts/import_unifi_old_dump.py all_unifi_users.csv --commit --placeholder-emails --yes
```

Alternative explicit database URL form:

```bash
DATABASE_URL="$RAILWAY_DATABASE_URL" python scripts/import_unifi_old_dump.py all_unifi_users.csv --commit
```

Never commit `.env` files or database secrets. Run the dry run against production before committing, and confirm the printed host/database are the intended Railway database.

## Diagnose Empty Users Dashboard

The new dashboard Users page reads local registry `users` records from:

```text
frontend /dashboard/users
  -> Next.js /api/backend/admin/users
  -> FastAPI /api/admin/users
  -> users table joined through ORM relationships to companies, suites, access profiles, and linked unifi_users snapshots
```

There is no `buildingId`, `tenantId`, `organizationId`, source, or status filter on the Users API. This app currently models 1205 on Franklin as a single-property registry database. If the dashboard shows no users, first confirm that the Railway database actually contains local `users` rows:

```bash
railway run python scripts/diagnose_users.py
```

The diagnostic command is read-only. It prints the connected database host/name with credentials hidden, Alembic version rows, counts for companies, suites, company_suites, users, user_suite_assignments, and unifi snapshots, plus a small sample of users.

If `unifi snapshots` is greater than zero but `users` is zero, reconciliation has only stored read-only UniFi snapshots. Promote snapshots through the bootstrap review flow, or import the old dump:

```bash
railway run python scripts/import_unifi_old_dump.py all_unifi_users.csv --dry-run
railway run python scripts/import_unifi_old_dump.py all_unifi_users.csv --commit --yes
```

If `users` is greater than zero but the dashboard is empty, check Railway logs for `admin users fetch` from FastAPI and `ENTRY POINT users proxy fetch` from Next.js. Those log lines show whether the frontend reached the correct endpoint, the upstream status, the database host/name, how many users were found, and that no filters were applied.

## UI and Dark Mode

The admin UI uses reusable CSS utilities for cards, badges, buttons, responsive tables, alerts, and changed-field diffs. A theme toggle in the base layout stores `light` or `dark` in browser `localStorage`; first visit respects the system `prefers-color-scheme` setting. No backend preference or frontend build chain is required.

## Required Environment Variables

Core:

```text
DATABASE_URL=postgresql+psycopg://building_access:change_me@db:5432/building_access_registry
POSTGRES_PASSWORD=change_me
APP_SECRET_KEY=change_me
ADMIN_EMAIL=admin@example.com
ADMIN_INITIAL_PASSWORD=
PUBLIC_BASE_URL=http://localhost:8080
BACKEND_API_URL=http://web:8080
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

Run the new dashboard frontend in another shell:

```powershell
cd frontend
npm install
$env:BACKEND_API_URL="http://localhost:8080"
npm run dev
```

Open `http://localhost:3000` for the Next.js dashboard. The frontend talks to FastAPI through its own `/api/backend/...` proxy routes.

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

The FastAPI backend listens on port `8080`. The Next.js dashboard listens separately on port `3000`. PostgreSQL data is stored in the Docker named volume `building_access_registry_pgdata`. Reports, previews, and exports are written to `/app/exports`.

## Portainer

Deploy the repository as a Git-backed stack using `docker-compose.yml` or `portainer-stack.yml`.

Expected services:

- `web`
- `frontend`
- `worker`
- `db`

Expected export bind mount:

```text
/mnt/unas/docker-exports/building-access-registry:/app/exports
```

Supply environment variables in Portainer stack settings. Keep `ENABLE_WRITES=false` unless a future phase explicitly implements and approves UniFi write behavior.

Set `BACKEND_API_URL=http://web:8080` for the frontend service in Docker/Portainer. Use `PUBLIC_BASE_URL=http://localhost:8080` or your deployed backend URL for backend-generated links.

After pulling a new version, redeploy the stack and run database migrations before using new schema fields:

```powershell
docker compose run --rm web alembic upgrade head
docker compose up -d --build
```

In Portainer, use the equivalent stack redeploy flow, then run `alembic upgrade head` in the `web` service or an attached one-off console.

## Safety Warnings

- `ENABLE_WRITES=false` is the default.
- Phase 1 and Phase 2 write methods in `app/unifi_client.py` raise unless writes are enabled, then raise `NotImplementedError` because UniFi write behavior is intentionally not implemented.
- The UniFi API token and SMTP password are server-side only.
- The Next.js dashboard receives no UniFi API token, SMTP password, session secret, or other backend secret. It calls FastAPI through server-side proxy routes.
- Email disabled mode writes preview files to `EXPORT_DIR/email_previews`.
- Approval creates `SyncJob` records and audit logs; it does not provision directly.
- Reconciliation creates local snapshots, open conflicts, and dry-run proposed actions only. It does not call UniFi write APIs.
- Bootstrap import creates or links local registry records only. It does not provision or modify UniFi users.

## Tests

```powershell
pytest
```

The test suite covers the preserved exporter behavior, focused Phase 1 application behavior, and Phase 2 reconciliation behavior.
