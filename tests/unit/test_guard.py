"""Tests for scripts/check_licensed_data.py, each in a throwaway git repository."""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "check_licensed_data.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_licensed_data", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


guard = _load()


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.name", "Test")
    _git(tmp_path, "config", "user.email", "test@example.com")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _track(repo: Path, name: str, content: bytes = b"x") -> None:
    (repo / name).write_bytes(content)
    _git(repo, "add", "-f", name)


@pytest.mark.parametrize("name", ["x.parquet", "x.csv", "x.sas7bdat", "x.dta", "X.PARQUET"])
def test_banned_extension_fails(repo: Path, name: str, capsys: pytest.CaptureFixture[str]) -> None:
    _track(repo, name)
    assert guard.main([]) == 1
    assert name in capsys.readouterr().out


def test_permno_in_data_file_fails(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _track(repo, "notes.json", b'{"PERMNO": 10107}')
    assert guard.main([]) == 1
    assert "notes.json" in capsys.readouterr().out


@pytest.mark.parametrize("name", ["loader.py", "README.md"])
def test_permno_in_code_or_docs_passes(repo: Path, name: str) -> None:
    _track(repo, name, b'"PERMNO": 10107')
    assert guard.main([]) == 0


def test_clean_repo_passes(repo: Path) -> None:
    _track(repo, "a.py", b"print(1)\n")
    assert guard.main([]) == 0


def test_staged_banned_file_fails(repo: Path) -> None:
    _track(repo, "x.parquet")
    assert guard.main(["--staged"]) == 1


def test_untracked_banned_file_passes(repo: Path) -> None:
    (repo / "x.parquet").write_bytes(b"x")
    assert guard.main([]) == 0
    assert guard.main(["--staged"]) == 0


def test_allowed_path_passes(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _track(repo, "fixture.parquet")
    monkeypatch.setattr(guard, "ALLOWED_PATHS", frozenset({"fixture.parquet"}))
    assert guard.main([]) == 0
