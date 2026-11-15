from __future__ import annotations

import pytest
from typer.testing import CliRunner

import filinglens
from filinglens import cli
from filinglens.cli import app
from filinglens.config import Settings

runner = CliRunner()


@pytest.fixture(autouse=True)
def _no_env_file(monkeypatch: pytest.MonkeyPatch) -> None:
    # Never read the real .env in tests.
    monkeypatch.setattr(cli, "get_settings", lambda: Settings(_env_file=None))  # type: ignore[call-arg]


def test_help_lists_commands() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "version" in result.output
    assert "env" in result.output


def test_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.output.strip() == filinglens.__version__


def test_env_hides_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FL_SEC_USER_AGENT", "UAMARKER42 someone")
    monkeypatch.setenv("GROQ_API_KEY", "GROQMARKER42")
    result = runner.invoke(app, ["env"])
    assert result.exit_code == 0
    assert "@" not in result.output
    assert "UAMARKER42" not in result.output
    assert "GROQMARKER42" not in result.output
    assert "sec_user_agent" in result.output
