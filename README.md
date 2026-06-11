# UniFi Access User Exporter

Dockerized Python utility for exporting users from a local UniFi Access system through the UniFi Access developer API.

The first version is export-first and read-only. It fetches users from:

```text
GET /api/v1/developer/users
```

It writes timestamped exports:

- Normalized CSV for spreadsheet and inventory tools
- Normalized JSON for automation systems
- Sanitized raw JSON for audit/debug use

Sensitive-looking fields such as tokens, PINs, hashes, card credential data, passwords, secrets, and webhook values are redacted from the raw export and are not included in the CSV.

## Create A UniFi Access API Token

In UniFi Access, create a local developer/API token from the UniFi Access console settings. The exact UI can vary by UniFi Access version, but the flow is generally:

1. Open UniFi Access on your local console.
2. Go to the developer/API integration settings.
3. Create a new API token.
4. Grant the token read/view permissions for users.
5. Store the token in `.env` as `UNIFI_ACCESS_TOKEN`.

Minimum permission:

- Read/view users

Avoid granting write, admin, or provisioning permissions to the token used by this exporter.

## Configuration

Copy the example file and edit it:

```powershell
cp .env.example .env
```

Required:

```text
UNIFI_ACCESS_BASE_URL=https://192.168.1.1:12445
UNIFI_ACCESS_TOKEN=replace_me
```

Common options:

```text
UNIFI_ACCESS_VERIFY_SSL=false
UNIFI_ACCESS_PAGE_SIZE=100
OUTPUT_DIR=./exports
EXPORT_CSV=true
EXPORT_JSON=true
LOG_LEVEL=INFO
```

`UNIFI_ACCESS_VERIFY_SSL` defaults to safe certificate verification when omitted. Set it to `false` only when your local UniFi Access console uses a self-signed certificate and you understand the risk.

Future sync placeholders:

```text
SYNC_MODE=export_only
SOURCE_OF_TRUTH=unifi_access
ENABLE_WRITES=false
MICROSOFT_LIST_WEBHOOK_URL=
HOME_ASSISTANT_WEBHOOK_URL=
N8N_WEBHOOK_URL=
```

Any mode other than `export_only` requires `ENABLE_WRITES=true`, but write-back/provisioning is intentionally not implemented in this version.

## Run With Python

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
# edit .env
python src/unifi_access_exporter.py
```

On Linux/macOS:

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env
python src/unifi_access_exporter.py
```

## Run With Docker Compose

```sh
cp .env.example .env
# edit .env
docker compose build
docker compose run --rm unifi-access-exporter
```

Exports are written to `./exports`.

## Schedule With Cron

Example hourly export:

```cron
0 * * * * cd /opt/unifi-access-exporter && docker compose run --rm unifi-access-exporter >> /var/log/unifi-access-exporter.log 2>&1
```

Example nightly export:

```cron
15 2 * * * cd /opt/unifi-access-exporter && docker compose run --rm unifi-access-exporter >> /var/log/unifi-access-exporter.log 2>&1
```

Use a service account, protect `.env`, and rotate the UniFi Access token on a regular schedule.

## Import CSV Into Excel, SharePoint, Or Microsoft Lists

Excel:

1. Open Excel.
2. Choose Data -> From Text/CSV.
3. Select the latest `exports/unifi_access_users_YYYYMMDD_HHMMSS.csv`.
4. Confirm comma delimiter and UTF-8 encoding.

SharePoint or Microsoft Lists:

1. Create a new List from CSV or import the CSV into an existing List.
2. Use `employee_number` or `email` as the human-readable match key.
3. Store `id` as the UniFi Access user identifier after first match.
4. Keep `access_policy_ids` and `group_ids` as text columns unless you have a controlled lookup model.

For recurring inventory updates, prefer an automation layer such as Power Automate, n8n, or Node-RED that consumes the normalized JSON or CSV and updates a controlled List.

## Future Sync Modes

Recommended progression:

1. Export-only inventory from UniFi Access.
2. One-way UniFi Access -> Microsoft Lists/SharePoint inventory sync.
3. Controlled source-of-truth -> UniFi Access provisioning.

Do not enable bidirectional identity sync without a complete conflict-resolution design. UniFi Access, HR systems, Microsoft Lists, SharePoint, Home Assistant, and workflow middleware can all disagree about user lifecycle state. A bad sync design can re-enable offboarded users, delete valid users, overwrite access policies, or create duplicate identities.

Use stable match keys:

- Prefer `employee_number` when present and governed.
- Use `email` when it is unique and stable.
- Store the UniFi Access `id` after first match.

Offboarding should deactivate or suspend users first, not delete them. Delete operations should require explicit review.

Home Assistant should be treated as an event and automation layer, not the source of truth for identity lifecycle. Node-RED and n8n are good middleware options for approval routing, notifications, and human-in-the-loop workflows.
