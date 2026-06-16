from __future__ import annotations

import ast
from pathlib import Path


def test_alembic_revision_ids_fit_default_version_column() -> None:
    versions_dir = Path("alembic/versions")
    revision_ids: list[str] = []
    for path in versions_dir.glob("*.py"):
        module = ast.parse(path.read_text(encoding="utf-8"))
        for node in module.body:
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == "revision":
                        assert isinstance(node.value, ast.Constant)
                        assert isinstance(node.value.value, str)
                        revision_ids.append(node.value.value)

    assert revision_ids
    assert all(len(revision_id) <= 32 for revision_id in revision_ids)
