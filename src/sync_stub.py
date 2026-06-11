from __future__ import annotations

import logging
import os
from typing import Any

import requests

LOGGER = logging.getLogger(__name__)


def push_to_home_assistant_webhook(users: list[dict[str, Any]]) -> None:
    """Send normalized users to Home Assistant when explicitly configured."""
    _post_webhook(os.getenv("HOME_ASSISTANT_WEBHOOK_URL", ""), users, "Home Assistant")


def push_to_n8n_webhook(users: list[dict[str, Any]]) -> None:
    """Send normalized users to n8n when explicitly configured."""
    _post_webhook(os.getenv("N8N_WEBHOOK_URL", ""), users, "n8n")


def push_to_microsoft_list_webhook(users: list[dict[str, Any]]) -> None:
    """Send normalized users to a Microsoft List/SharePoint middleware endpoint."""
    _post_webhook(os.getenv("MICROSOFT_LIST_WEBHOOK_URL", ""), users, "Microsoft List")


def _post_webhook(url: str, users: list[dict[str, Any]], target_name: str) -> None:
    if not url:
        LOGGER.info("%s webhook URL is not configured; skipping.", target_name)
        return

    # Write-back/provisioning into UniFi Access is intentionally not implemented.
    # These webhook pushes are outbound-only integration placeholders.
    response = requests.post(url, json={"users": users}, timeout=(5, 30))
    response.raise_for_status()
