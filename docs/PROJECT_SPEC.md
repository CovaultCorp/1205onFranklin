# docs/PROJECT_SPEC.md

# Building Access Registry Project Specification

## Project name

`building-access-registry`

## Purpose

`building-access-registry` is a lightweight internal web application and local database for managing building access users, company membership, suite membership, access requests, approvals, reports, and UniFi Access synchronization.

The local application/database is the primary source of truth for registry and workflow data.

UniFi Access is the target access-control system.

## Implementation status

Phase 1 and Phase 2 are implemented in this repository: local registry models, request portal, admin UI, reporting, email preview mode, Docker stack, dry-run-only UniFi stubs, read-only UniFi reconciliation, local UniFi snapshots, conflict detection, dry-run proposed sync jobs, and a local-only bootstrap workflow for promoting unmatched UniFi snapshots into local users. Phase 3 through Phase 4 remain future work.

## Primary goals

The app should track:

* Which users have building access
* Which company each user belongs to
* Which suite/location each user belongs to
* What access profile or desired UniFi Access Policy/User Group each user should have
* Whether a user is active, inactive, pending, or offboarded
* Whether user/company/suite data has recently been verified
* Which access requests are pending, approved, denied, synced, failed, or conflicted
* What actions were taken and by whom

## Non-goals for v1

Do not implement these in v1:

* NFC badge provisioning
* PIN provisioning
* Touch Pass provisioning
* Raw credential secret storage
* Automatic deletion of UniFi users
* Fully automatic bidirectional conflict resolution
* Public internet self-service portal without an access-control layer
* Heavy frontend framework

## Architecture

Recommended stack:

* FastAPI web app
* Jinja2 templates
* HTMX for small interactive pieces
* Simple CSS
* PostgreSQL database
* SQLAlchemy 2.x ORM
* Alembic migrations
* Worker container for reconciliation/sync/report tasks
* SMTP email support
* Email preview mode
* Docker Compose
* Portainer Git-backed deployment

Docker services:

* `web`
* `worker`
* `db`

Data storage:

* PostgreSQL data should use a Docker named volume.
* Exports, reports, email previews, and backups should be written to `/app/exports`.
* Production bind mount target:
  `/mnt/unas/docker-exports/building-access-registry:/app/exports`

## Environment variables

Core:

```text
DATABASE_URL=postgresql+psycopg://building_access:change_me@db:5432/building_access_registry
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
UNIFI_ACCESS_TOKEN=replace_me
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

## Security requirements

* UniFi API token must remain server-side.
* SMTP password must remain server-side.
* Do not log secrets.
* Do not expose secrets to templates or browser JavaScript.
* Admin pages require authentication.
* Admin approval is required before sync/provisioning.
* All UniFi write methods must check `ENABLE_WRITES`.
* `ENABLE_WRITES=false` must be the default.
* `ENABLE_EMAIL=false` must be safe and useful by writing preview files.
* Admin dashboard must clearly show write mode and email mode.

## Main entities

### PortalAccount

Represents app login accounts.

Fields:

* id
* email
* password_hash
* role: requester/admin/auditor
* active
* created_at
* updated_at

### Company

Represents tenant/company membership.

Fields:

* id
* name
* legal_name
* status: active/inactive
* primary_contact_name
* primary_contact_email
* phone
* notes
* created_at
* updated_at

### Suite

Represents a physical suite/location.

Fields:

* id
* suite_number
* floor
* building_area
* description
* status: active/inactive
* created_at
* updated_at

### CompanySuite

Represents company occupancy of suites.

Fields:

* id
* company_id
* suite_id
* occupancy_status: active/inactive/pending
* start_date
* end_date
* notes
* created_at
* updated_at

### User

Represents a person in the local registry.

Fields:

* id
* first_name
* last_name
* email
* employee_number
* company_id
* primary_suite_id
* access_profile_id
* desired_unifi_access_policy_ids
* desired_unifi_access_policy_names
* desired_unifi_user_group_ids
* desired_unifi_user_group_names
* title
* phone
* department
* status: active/inactive/pending/offboarded
* notes
* last_verified_at
* last_verified_by
* created_at
* updated_at

### UserSuiteAssignment

Allows multiple suite assignments per user.

Fields:

* id
* user_id
* suite_id
* company_id
* assignment_type: primary/secondary/temporary
* start_date
* end_date
* active
* created_at
* updated_at

### AccessProfile

Friendly local access profile mapped to UniFi policies/groups.

Fields:

* id
* name
* description
* default_for_company_id
* default_for_suite_id
* unifi_access_policy_ids
* unifi_user_group_ids
* active
* created_at
* updated_at

### AccessRequest

Represents a submitted access request.

Fields:

* id
* request_type: new_access/change_access/offboarding/temporary_access/lost_badge
* requested_for_user_id
* requested_for_first_name
* requested_for_last_name
* requested_for_email
* requested_for_employee_number
* requested_for_company_text
* requested_for_suite_text
* requested_for_company_id
* requested_for_suite_id
* requested_for_department
* requested_access_profile_id
* requested_start_date
* requested_end_date
* reason
* status
* requester_name
* requester_email
* admin_notes
* denial_reason
* approved_by_account_id
* approved_at
* denied_by_account_id
* denied_at
* created_at
* updated_at

Allowed statuses:

* submitted
* pending_approval
* needs_info
* approved
* denied
* pending_sync
* synced
* sync_failed
* conflict
* cancelled

### UnifiUser

Represents latest known UniFi user snapshot.

Fields:

* id
* local_user_id
* unifi_user_id
* email
* email_status
* employee_number
* suite_number
* first_name
* last_name
* full_name
* phone
* username
* alias
* status
* onboard_time
* access_policy_ids
* access_policy_names
* group_ids
* group_names
* nfc_card_count
* touch_pass_status
* touch_pass_last_activity
* license_plate_count
* raw_user_json_file
* raw_snapshot_json
* last_seen_at
* last_synced_at
* created_at
* updated_at

### SyncJob

Represents proposed or executed sync work.

Fields:

* id
* access_request_id
* job_type: reconcile/create_user/update_user/deactivate_user/assign_policies/dry_run
* status: pending/running/succeeded/failed/skipped/conflict
* proposed_actions
* result_json
* attempt_count
* last_error
* created_at
* updated_at
* completed_at

### AuditLog

Tracks important actions.

Fields:

* id
* actor_account_id
* actor_email
* action
* target_type
* target_id
* before_json
* after_json
* ip_address
* created_at

### Conflict

Represents mismatches requiring admin review.

Fields:

* id
* local_user_id
* unifi_user_id
* conflict_type
* description
* local_state_json
* unifi_state_json
* status: open/accepted_unifi/reapply_portal/ignored/resolved
* resolved_by_account_id
* resolved_at
* created_at
* updated_at

### ReportRun

Represents a generated or emailed report.

Fields:

* id
* report_type: company_users/suite_users/full_building_access/verification
* status: pending/running/sent/failed
* requested_by_account_id
* recipient_email
* subject
* body
* filters_json
* output_csv_path
* output_html_path
* sent_at
* last_error
* created_at
* updated_at

### VerificationRequest

Represents an emailed verification workflow.

Fields:

* id
* report_run_id
* company_id
* suite_id
* recipient_email
* status: pending/verified/changes_requested/expired
* verification_token_hash
* verified_at
* verified_by_name
* verified_by_email
* comments
* expires_at
* created_at
* updated_at

## Access request workflow

Normal request flow:

```text
submitted
  -> pending_approval
  -> approved
  -> pending_sync
  -> synced
```

Alternative paths:

```text
needs_info
denied
sync_failed
conflict
cancelled
```

Rules:

* Only admin users can approve or deny.
* Denial requires a reason.
* Approval creates an AuditLog entry.
* Admin may modify company, suite, and access profile before approval.
* Admin must map free-text company/suite values to real records before approval.
* Approval should queue a SyncJob.
* Approval should not directly call UniFi write APIs from the request/response cycle.

## Reporting

Required reports:

### Users by company

Show active users assigned to selected company.

Columns:

* Full name
* Email
* Employee number
* Company
* Suite
* Status
* Access profile
* UniFi status
* Current UniFi Access Policies
* Desired UniFi Access Policies
* Current UniFi User Groups
* Desired UniFi User Groups
* Last verified date
* Notes

### Users by suite

Show active users assigned to selected suite.

Columns:

* Full name
* Email
* Employee number
* Company
* Suite
* Status
* Access profile
* UniFi status
* Current UniFi Access Policies
* Desired UniFi Access Policies
* Current UniFi User Groups
* Desired UniFi User Groups
* Last verified date
* Notes

### Full building access report

Show all active users grouped by suite and company.

### Verification report

Email a building manager or company contact a list of users for review.

Rules:

* Reports default to active users only.
* Inactive/offboarded users appear only if explicitly selected.
* Reports support CSV download.
* Reports support HTML preview.
* Reports are stored in `EXPORT_DIR/reports`.
* ReportRun records are created.
* Email previews are stored in `EXPORT_DIR/email_previews` when `ENABLE_EMAIL=false`.

## Email behavior

If `ENABLE_EMAIL=false`:

* Do not send SMTP email.
* Write email preview files to `EXPORT_DIR/email_previews`.
* Still create ReportRun records.

If `ENABLE_EMAIL=true`:

* Send via SMTP.
* Support CSV attachments.
* Do not log SMTP password.
* If sending fails, mark ReportRun failed and store last_error.

## Verification workflow

When a verification report is sent:

* Generate CSV attachment.
* Generate simple HTML body.
* Include instructions asking recipient to review and reply with corrections.
* Include a verification link if implemented.

Verification link:

* `GET /verify/{token}`
* `POST /verify/{token}`
* Recipient can mark:

  * verified accurate
  * changes requested
* Recipient can leave comments.
* Recipient cannot directly edit users.
* Token must be random, hashed in database, and expire.

## UniFi integration

Phase 1:

* Read-only methods or stubs.
* No writes.
* Existing exporter functionality should be preserved if present.

Read methods:

* list_users
* get_user
* list_access_policies
* list_user_groups

Write methods may exist but must raise `WritesDisabledError` unless `ENABLE_WRITES=true`.

Future write methods:

* create_user
* update_user
* set_user_status
* assign_access_policies

v1 restrictions:

* Do not delete UniFi users.
* Do not manage NFC/PIN/Touch Pass.
* Offboarding means set status to deactivated only.

## Reconciliation

Reconciliation should:

* Pull users from UniFi.
* Normalize each UniFi user with the compatibility extractor before matching or storing.
* Upsert all returned `UnifiUser` snapshots, not only admin users.
* Store exporter-compatible normalized fields, including fallback email fields, suite number, phone, username, alias, onboard time, policies, groups, NFC count, Touch Pass status/activity, and license plate count.
* Store sanitized raw snapshots only; card, license plate, PIN, credential, token, password, and secret-like fields must be redacted.
* Match users by:

  1. existing UniFi user ID mapping
  2. employee number
  3. email
* Create Conflict records for risky mismatches.
* Create dry-run SyncJob records with proposed actions.

Detect:

* UniFi user exists but no local company
* UniFi user exists but no local suite
* Local active user not found in UniFi
* UniFi active user not found locally
* Status mismatch
* Name/email mismatch
* Access policy mismatch
* Duplicate email
* Duplicate employee number
* User belongs to inactive company
* User assigned to inactive suite

## Bootstrap workflow

The bootstrap workflow supports initial population and cleanup of the local registry from read-only UniFi snapshots.

Rules:

* Bootstrap operates on local database records only.
* Bootstrap must not call UniFi write APIs.
* `/admin/bootstrap/export` exports all locally stored `UnifiUser` snapshots to `all_unifi_users.csv`, including linked and unlinked users.
* Bootstrap CSV includes the old exporter fields: `id`, `first_name`, `last_name`, `full_name`, `email`, `email_status`, `employee_number`, `suite_number`, `phone`, `username`, `alias`, `status`, `onboard_time`, `access_policy_ids`, `access_policy_names`, `group_ids`, `group_names`, `nfc_card_count`, `touch_pass_status`, `touch_pass_last_activity`, `license_plate_count`, and `raw_user_json_file`.
* Bootstrap CSV separates the UniFi-derived `suite_number` from local registry enrichment fields `local_suite_id` and `local_suite_number`.
* CSV import promotes unlinked snapshots only when explicitly marked with `promote=yes`.
* CSV import updates linked local users only when explicitly marked with `update_existing=yes`.
* CSV import skips rows where both `promote` and `update_existing` are blank.
* Reference export must provide companies, suites, UniFi access policies, UniFi user groups, and all UniFi users in a ZIP.
* CSV import must resolve company and suite to existing local records by ID or by name/number.
* CSV import accepts Suite by `local_suite_id`, `local_suite_number`, or the old exporter `suite_number` field.
* CSV import must resolve desired UniFi Access Policy and UniFi User Group selections by ID or by name.
* CSV import must reject a row when name/number lookup is missing or ambiguous.
* CSV import must not create duplicate users; existing users are matched by employee number, then email.
* CSV import links the `UnifiUser` snapshot to the created or existing local `User`.
* CSV import creates a primary `UserSuiteAssignment`.
* CSV import creates `AuditLog` records.
* Bootstrap UI must use the user-facing terms Company, Suite, UniFi Access Policy, and UniFi User Group.
* UniFi Access does not use the app's internal `AccessProfile` field; access profiles remain optional local templates and are not required for bootstrap.
* Suite number normalization prefers explicit UniFi fields `suite_number`, `suiteNumber`, or `suite`; if absent, it falls back to the first three digits found in `employee_number`. This fallback is retained for compatibility with the current building registry workflow.

Required bootstrap routes:

* GET /admin/bootstrap
* GET /admin/bootstrap/reference-export
* GET /admin/bootstrap/export
* POST /admin/bootstrap/import

## Admin dashboard

Show:

* Total active users
* Users by company count
* Users by suite count
* Users not assigned to a company
* Users not assigned to a suite
* Users not verified in last 90 days
* Pending access requests
* Open conflicts
* Sync failures
* Recent synced requests
* Recent report runs
* Current `ENABLE_WRITES` mode
* Current `ENABLE_EMAIL` mode

## Required routes

Requester:

* GET /request
* POST /request
* GET /request/thanks/{id}

Auth:

* GET /login
* POST /login
* POST /logout
* GET /setup-admin
* POST /setup-admin

Admin:

* GET /admin
* GET /admin/requests
* GET /admin/requests/{id}
* POST /admin/requests/{id}/approve
* POST /admin/requests/{id}/deny
* POST /admin/requests/{id}/needs-info
* POST /admin/requests/{id}/sync
* GET /admin/users
* GET /admin/users/{id}
* GET /admin/companies
* POST /admin/companies
* POST /admin/companies/{id}/update
* GET /admin/suites
* POST /admin/suites
* POST /admin/suites/{id}/update
* GET /admin/company-suites
* POST /admin/company-suites
* GET /admin/access-profiles
* POST /admin/access-profiles
* POST /admin/access-profiles/{id}/update
* GET /admin/conflicts
* POST /admin/conflicts/{id}/resolve
* GET /admin/sync-jobs
* POST /admin/reconcile/run
* GET /admin/bootstrap
* GET /admin/bootstrap/reference-export
* GET /admin/bootstrap/export
* POST /admin/bootstrap/import

Reports:

* GET /admin/reports
* GET /admin/reports/company-users
* POST /admin/reports/company-users/preview
* POST /admin/reports/company-users/send
* GET /admin/reports/suite-users
* POST /admin/reports/suite-users/preview
* POST /admin/reports/suite-users/send
* GET /admin/reports/full-building
* POST /admin/reports/full-building/preview
* POST /admin/reports/full-building/send
* GET /admin/reports/runs
* GET /admin/reports/runs/{id}
* POST /admin/reports/runs/{id}/resend
* GET /admin/reports/runs/{id}/download-csv

Verification:

* GET /verify/{token}
* POST /verify/{token}

## Tests

Required tests:

* Admin auth required
* First-admin setup
* Company creation
* Suite creation
* Company-suite occupancy
* User assigned to company and suite
* Access request creation
* Approval state transition
* Dry-run sync when `ENABLE_WRITES=false`
* UniFi write guard
* No duplicate user creation on retry
* Conflict detection
* Access profile policy mapping
* Report generation by company
* Report generation by suite
* Full building report grouping
* Email disabled mode writes preview file
* SMTP enabled mode uses mailer mock
* VerificationRequest creation
* Verification token expiration logic
* Reconciliation flags UniFi user with no company/suite
* CSV export includes company and suite columns
* Import dry-run does not write records

## First-run workflow

1. Deploy app through Portainer.
2. Create first admin.
3. Create companies.
4. Create suites.
5. Map companies to suites.
6. Create access profiles and enter UniFi policy IDs.
7. Run read-only UniFi reconciliation.
8. Submit a test access request.
9. Approve the request in dry-run mode.
10. Review SyncJob proposed actions.
11. Keep `ENABLE_WRITES=false` until the dry-run behavior is verified.
12. Only enable `ENABLE_WRITES=true` when ready for controlled provisioning.
