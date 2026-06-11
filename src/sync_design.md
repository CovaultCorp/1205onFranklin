# Sync Design

## Phase 1: UniFi Access Read-Only Export

The initial implementation only reads UniFi Access users and writes normalized CSV/JSON exports. This keeps the API token low-privilege and avoids accidental identity lifecycle changes.

The exporter should remain safe by default:

- `SYNC_MODE=export_only`
- `ENABLE_WRITES=false`
- Read/view user permission only
- No provisioning or write-back code paths

## Phase 2: UniFi Access -> Microsoft List/SharePoint Inventory

The next safe step is one-way inventory sync from UniFi Access into Microsoft Lists or SharePoint.

Recommended behavior:

- Treat UniFi Access as the observed source for door-access inventory.
- Upsert List rows using `employee_number` when reliable.
- Fall back to `email` only when it is unique and stable.
- Store the UniFi Access user `id` after the first match.
- Keep historical exports for auditability.

This phase should not provision users back into UniFi Access.

## Phase 3: Controlled Source-Of-Truth -> UniFi Access Provisioning

Provisioning should only happen after the identity source of truth is explicit. In many organizations this is HR, Entra ID, an access request system, or a controlled SharePoint/Microsoft List with approval workflow.

Recommended behavior:

- Require explicit approval before creating or changing access users.
- Match existing UniFi users by stored UniFi `id`, then `employee_number`, then `email`.
- Deactivate first during offboarding.
- Avoid deleting users automatically.
- Log every intended change before applying it.
- Keep dry-run mode as the default.

## Avoid True Bidirectional Sync

True bidirectional sync should be avoided unless conflict resolution is fully designed.

Risk examples:

- A deactivated UniFi user is re-enabled by a stale Microsoft List row.
- A renamed employee creates a duplicate account because email changed.
- Middleware overwrites access policies from a partial record.
- A delete in one system removes identity evidence needed for audit.

If bidirectional sync is ever required, define field ownership, freshness rules, conflict states, manual review queues, rollback behavior, and audit retention before implementation.

## Match Keys

Prefer match keys in this order:

1. Stored UniFi Access user `id`
2. Governed `employee_number`
3. Unique and stable `email`

Do not use full name as a durable match key.

## Offboarding

Offboarding should deactivate first, not delete. Deactivation preserves audit history and gives administrators time to verify that access policy removal worked as expected.

Delete operations should require a separate approval path.

## Middleware Roles

Home Assistant should be treated as an event/automation layer, not as the source of truth for identity lifecycle.

Node-RED and n8n can act as middleware for:

- Approval routing
- Notifications
- Scheduled inventory updates
- Exception queues
- Human review before provisioning

They should not silently resolve identity conflicts without a controlled workflow.
