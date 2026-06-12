# AGENTS.md

# building-access-registry Agent Instructions

This repository contains `building-access-registry`, a Dockerized internal web app for managing building access users, companies, suites, access requests, reports, and UniFi Access synchronization.

## Primary project intent

The local application/database is the primary source of truth for:

* Building access users
* Company membership
* Suite/location membership
* Desired access profile
* Access request workflow
* Approval history
* Verification/reporting history

UniFi Access is the target access-control system. It is not the workflow database.

## Safety rules

Follow these rules strictly:

1. Do not implement UniFi write behavior unless the task explicitly asks for it.
2. All UniFi write methods must be guarded by `ENABLE_WRITES=true`.
3. `ENABLE_WRITES=false` must be the default.
4. Never expose the UniFi API token to the browser.
5. Never log UniFi API tokens, SMTP passwords, session secrets, or other secrets.
6. Do not store PINs, raw badge secrets, NFC secrets, Touch Pass secrets, or credential tokens.
7. Do not implement NFC/PIN/Touch Pass provisioning in v1.
8. Never delete UniFi users in v1. Offboarding means deactivate only.
9. Admin approval is required before any provisioning action.
10. All proposed provisioning actions should be represented as `SyncJob` records before execution.
11. All meaningful actions must create `AuditLog` records.

## Deployment rules

The app must be deployable as a Portainer Git-backed stack.

Expected deployment shape:

* `docker-compose.yml` at repository root
* Services: `web`, `worker`, `db`
* Web port: `8080`
* PostgreSQL data in a Docker named volume
* Exports/reports/backups written to `/app/exports`
* Compose bind mount target:
  `/mnt/unas/docker-exports/building-access-registry:/app/exports`
* No committed `.env` secrets
* Environment variables supplied through Portainer stack environment variables

## Development stack

Use:

* Python 3.12
* FastAPI
* Jinja2 templates
* HTMX where useful
* Simple CSS only
* PostgreSQL
* SQLAlchemy 2.x
* Alembic migrations
* Pydantic settings
* httpx or requests for UniFi API
* pytest for tests

Avoid:

* Heavy frontend build chains
* Unnecessary JavaScript frameworks
* Cloud-only dependencies
* Storing secrets in the repo

## App structure

Prefer this structure:

```text
app/
  main.py
  config.py
  models.py
  db.py
  unifi_client.py
  reconcile.py
  sync_worker.py
  reports.py
  mailer.py
  verification.py
  import_export.py
  routes/
    auth.py
    requester.py
    admin.py
    reports.py
    verify.py
  templates/
  static/
alembic/
scripts/
tests/
docs/
```

## Testing expectations

Before finishing a task, run the relevant tests. If the full test suite is available and reasonable to run, run it.

Preferred commands:

```bash
pytest
```

For Docker smoke tests:

```bash
docker compose build
docker compose up -d
docker compose logs --tail=100 web
docker compose logs --tail=100 worker
```

## Implementation style

* Keep code readable and boring.
* Prefer explicit database models over generic JSON blobs for core business entities.
* Use JSON fields only for external snapshots, proposed actions, report filters, and raw API responses.
* Keep routes thin; put business logic in service modules.
* Make dangerous operations idempotent.
* Do not create duplicate users on retries.
* Match users by UniFi user ID first, then employee number, then email.
* Use clear status fields instead of ambiguous booleans.

## Required docs

Keep `docs/PROJECT_SPEC.md` updated when product behavior changes.

When implementing a major feature, update the README with:

* What changed
* Required environment variables
* How to test it
* How to use it in Portainer
* Any safety warnings

## Current implementation phases

Phase 1:
Build the local registry, request portal, admin UI, reporting, email preview mode, Docker stack, and dry-run-only UniFi stubs.

Phase 2:
Add read-only UniFi reconciliation, snapshots, conflict detection, and proposed dry-run sync jobs.

Phase 3:
Add controlled UniFi writes for approved requests only, guarded by `ENABLE_WRITES=true`.

Phase 4:
Add scheduled reports, verification workflow improvements, imports/exports, and operational polish.
