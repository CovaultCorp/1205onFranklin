from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy.engine import make_url

from app.db import Base, engine, init_db, safe_database_identity
import app.models  # noqa: F401
from scripts.seed_entrypoint import main as seed_entrypoint


LOCAL_HOSTS = {"", None, "localhost", "127.0.0.1", "::1", "db"}


def _is_local_database() -> bool:
    url = make_url(str(engine.url))
    if url.drivername.startswith("sqlite"):
        return True
    return url.host in LOCAL_HOSTS


def main() -> int:
    parser = argparse.ArgumentParser(description="Reset the local development database and seed ENTRY POINT.")
    parser.add_argument("--yes", action="store_true", help="Confirm the destructive local reset.")
    parser.add_argument("--force-remote", action="store_true", help="Allow reset even when the database host is not local.")
    args = parser.parse_args()

    db = safe_database_identity()
    print("Target database:")
    print(f"- {db['url']}")

    if not args.yes:
        print("Refusing to reset without --yes.")
        return 2
    if not _is_local_database() and not args.force_remote:
        print("Refusing to reset a non-local database. Export data first, then rerun with --force-remote only for disposable test databases.")
        return 3

    Base.metadata.drop_all(bind=engine)
    init_db()
    seed_entrypoint()
    print("Local development database reset complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
