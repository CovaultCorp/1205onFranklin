from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select

from app.db import SessionLocal, init_db, safe_database_identity
from app.models import BuildingProperty


def main() -> int:
    init_db()
    with SessionLocal() as session:
        property_ = session.scalar(select(BuildingProperty).where(BuildingProperty.slug == "1205-franklin"))
        if property_ is None:
            property_ = BuildingProperty(
                slug="1205-franklin",
                name="ENTRY POINT",
                display_name="1205 on Franklin",
                address_line1="1205 Franklin",
                city="Tampa",
                state="FL",
                status="active",
                notes="Seed property for Entry Point at 1205 on Franklin.",
            )
            session.add(property_)
            session.commit()
            action = "created"
        else:
            property_.name = "ENTRY POINT"
            property_.display_name = "1205 on Franklin"
            property_.address_line1 = "1205 Franklin"
            property_.city = property_.city or "Tampa"
            property_.state = property_.state or "FL"
            property_.status = "active"
            session.commit()
            action = "updated"

        db = safe_database_identity()
        print(f"ENTRY POINT seed {action}: {property_.display_name} ({property_.slug})")
        print(f"Database: {db['url']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
