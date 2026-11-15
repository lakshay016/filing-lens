from __future__ import annotations

from pathlib import Path

import pytest

from tests import snapshot


@pytest.fixture(autouse=True)
def _tmp_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(snapshot, "SNAPSHOT_DIR", tmp_path)
    monkeypatch.delenv("FL_UPDATE_SNAPSHOTS", raising=False)


def test_create_then_match(tmp_path: Path) -> None:
    with pytest.raises(pytest.fail.Exception, match="created"):
        snapshot.assert_snapshot("a", {"b": 1, "a": "é"})
    text = (tmp_path / "a.json").read_text(encoding="utf-8")
    assert text == '{\n  "a": "é",\n  "b": 1\n}\n'
    snapshot.assert_snapshot("a", {"a": "é", "b": 1})


def test_mismatch_shows_diff(tmp_path: Path) -> None:
    (tmp_path / "m.json").write_text('{\n  "x": 1\n}\n', encoding="utf-8")
    with pytest.raises(pytest.fail.Exception) as info:
        snapshot.assert_snapshot("m", {"x": 2})
    assert "mismatch" in str(info.value)
    assert '+  "x": 2' in str(info.value)


def test_update(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    (tmp_path / "u.json").write_text("{}\n", encoding="utf-8")
    monkeypatch.setenv("FL_UPDATE_SNAPSHOTS", "1")
    snapshot.assert_snapshot("u", {"x": 2})
    assert (tmp_path / "u.json").read_text(encoding="utf-8") == '{\n  "x": 2\n}\n'
    snapshot.assert_snapshot("new", [1])
    assert (tmp_path / "new.json").exists()
