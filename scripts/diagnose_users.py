from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import func, select, text

from app.db import SessionLocal, safe_database_identity
from app.models import (
    BuildingProperty,
    Company,
    CompanySuite,
    Suite,
    SyncRun,
    SyncSnapshot,
    UnifiAccessPolicy,
    UnifiDoor,
    UnifiDoorGroup,
    UnifiUser,
    UnifiUserGroup,
    User,
    UserSuiteAssignment,
)


def _count(session, model) -> int:
    try:
        return session.scalar(select(func.count()).select_from(model)) or 0
    except Exception:
        session.rollback()
        return -1


def main() -> int:
    with SessionLocal() as session:
        db = safe_database_identity()
        print("Connected database:")
        print(f"- Driver: {db['driver']}")
        print(f"- Host: {db['host']}")
        print(f"- Database: {db['database']}")
        print(f"- URL: {db['url']}")

        print("\nRegistry counts:")
        print(f"- companies: {_count(session, Company)}")
        print(f"- building_properties: {_count(session, BuildingProperty)}")
        print(f"- suites: {_count(session, Suite)}")
        print(f"- company_suites: {_count(session, CompanySuite)}")
        print(f"- users: {_count(session, User)}")
        print(f"- active users: {session.scalar(select(func.count(User.id)).where(User.status == 'active')) or 0}")
        print(f"- user_suite_assignments: {_count(session, UserSuiteAssignment)}")
        print(f"- unifi snapshots: {_count(session, UnifiUser)}")
        print(f"- unifi access policies: {_count(session, UnifiAccessPolicy)}")
        print(f"- unifi user groups: {_count(session, UnifiUserGroup)}")
        print(f"- unifi doors: {_count(session, UnifiDoor)}")
        print(f"- unifi door groups: {_count(session, UnifiDoorGroup)}")
        print(f"- sync runs: {_count(session, SyncRun)}")
        print(f"- raw sync snapshots: {_count(session, SyncSnapshot)}")
        print(
            f"- unmatched unifi snapshots: "
            f"{session.scalar(select(func.count(UnifiUser.id)).where(UnifiUser.local_user_id.is_(None))) or 0}"
        )

        try:
            versions = session.execute(text("select version_num from alembic_version order by version_num")).scalars().all()
        except Exception as exc:
            versions = [f"unavailable: {exc}"]
        print("\nAlembic versions:")
        for version in versions:
            print(f"- {version}")

        print("\nSample users:")
        try:
            users = session.scalars(select(User).order_by(User.last_name, User.first_name).limit(10)).all()
            if not users:
                print("- none")
            for user in users:
                company = user.company.name if user.company else "Unassigned"
                suite = user.primary_suite.suite_number if user.primary_suite else "Unassigned"
                policies = ", ".join(user.desired_unifi_access_policy_names or []) or "Not set"
                print(f"- {user.first_name} {user.last_name} <{user.email}> | {company} | {suite} | {user.status} | {policies}")
        except Exception as exc:
            session.rollback()
            print(f"- unavailable until migrations are applied: {exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
