"""Snapshot helper: ``assert_snapshot(name, obj)``; ``FL_UPDATE_SNAPSHOTS=1`` rewrites."""

from __future__ import annotations

import difflib
import json
import os
from pathlib import Path
from typing import Any

import pytest

SNAPSHOT_DIR = Path(__file__).parent / "snapshots"


def assert_snapshot(name: str, obj: Any) -> None:
    text = json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    path = SNAPSHOT_DIR / f"{name}.json"
    update = os.environ.get("FL_UPDATE_SNAPSHOTS") == "1"
    if update or not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        existed = path.exists()
        path.write_text(text, encoding="utf-8")
        if not existed and not update:
            pytest.fail(f"Snapshot {name!r} did not exist; created {path}. Review it and re-run.")
        return
    expected = path.read_text(encoding="utf-8")
    if expected != text:
        diff = "".join(
            difflib.unified_diff(
                expected.splitlines(keepends=True),
                text.splitlines(keepends=True),
                fromfile=f"{name}.json (stored)",
                tofile=f"{name}.json (actual)",
            )
        )
        pytest.fail(f"Snapshot {name!r} mismatch:\n{diff}")
