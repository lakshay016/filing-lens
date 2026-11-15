from __future__ import annotations

from pathlib import Path

import pytest

from filinglens.config import Settings


def make(monkeypatch: pytest.MonkeyPatch, **env: str) -> Settings:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return Settings(_env_file=None)  # type: ignore[call-arg]


def test_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in ("FL_DATABASE_URL", "FL_DATA_DIR", "FL_SEC_USER_AGENT", "GROQ_API_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("FL_LLM_MODE", raising=False)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.database_url == "postgresql://filinglens:filinglens@localhost:5433/filinglens"
    assert s.data_dir == Path("./data")
    assert s.licensed_dir == Path("~/filinglens-licensed")
    assert s.holdings_file == Path("./holdings.local.toml")
    assert s.llm_mode == "live"
    assert s.sec_user_agent is None
    assert s.groq_api_key is None


def test_sqlalchemy_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FL_DATABASE_URL", raising=False)
    s = make(monkeypatch)
    assert s.sqlalchemy_url() == (
        "postgresql+psycopg://filinglens:filinglens@localhost:5433/filinglens"
    )
    s = make(monkeypatch, FL_DATABASE_URL="postgresql+asyncpg://u:p@localhost:5433/x")
    assert s.sqlalchemy_url() == "postgresql+asyncpg://u:p@localhost:5433/x"


def test_test_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    s = make(monkeypatch, FL_DATABASE_URL="postgresql://u:p@localhost:5433/filinglens")
    assert s.test_database_url() == "postgresql://u:p@localhost:5433/filinglens_test"


def test_is_local_database(monkeypatch: pytest.MonkeyPatch) -> None:
    local = make(monkeypatch, FL_DATABASE_URL="postgresql://u:p@localhost:5433/d")
    assert local.is_local_database()
    loopback = make(monkeypatch, FL_DATABASE_URL="postgresql://u:p@127.0.0.1:5433/d")
    assert loopback.is_local_database()
    remote = make(monkeypatch, FL_DATABASE_URL="postgresql://u:p@ep-x.us-east-2.aws.neon.tech/d")
    assert not remote.is_local_database()


def test_hosted_database_urls_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    before = make(monkeypatch).model_dump()
    after = make(
        monkeypatch,
        DATABASE_URL="postgresql://x:y@neon.tech/z",
        DATABASE_URL_UNPOOLED="postgresql://x:y@neon.tech/z",
    ).model_dump()
    assert before == after


def test_repr_hides_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    s = make(monkeypatch, GROQ_API_KEY="GROQMARKER42", GEMINI_API_KEY="GEMMARKER42")
    assert "GROQMARKER42" not in repr(s)
    assert "GEMMARKER42" not in repr(s)
    assert "GROQMARKER42" not in str(s.describe())


def test_describe_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FL_DATABASE_URL", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    s = make(monkeypatch, FL_SEC_USER_AGENT="UAMARKER42 a@b.c")
    d = s.describe()
    assert d["sec_user_agent"] == "set"
    assert d["groq_api_key"] == "not set"
    assert d["database"] == "localhost:5433"
