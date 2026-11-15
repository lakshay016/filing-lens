from __future__ import annotations

from collections.abc import Iterator

import pytest

from filinglens.config import Settings, get_settings


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv("FL_LLM_MODE", "replay")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def settings() -> Settings:
    """Fresh settings that never read the real ``.env``."""
    return Settings(_env_file=None)  # type: ignore[call-arg]


# TODO(0.2): add the ``db_session`` fixture (separate ``filinglens_test`` database).
