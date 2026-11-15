"""Runtime settings, read from the environment and an optional ``.env`` file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# DATABASE_URL and DATABASE_URL_UNPOOLED (hosted Neon) are deliberately not fields.

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    sec_user_agent: str | None = Field(default=None, validation_alias="FL_SEC_USER_AGENT")
    database_url: str = Field(
        default="postgresql://filinglens:filinglens@localhost:5433/filinglens",
        validation_alias="FL_DATABASE_URL",
    )
    data_dir: Path = Field(default=Path("./data"), validation_alias="FL_DATA_DIR")
    licensed_dir: Path = Field(
        default=Path("~/filinglens-licensed"), validation_alias="FL_LICENSED_DIR"
    )
    holdings_file: Path = Field(
        default=Path("./holdings.local.toml"), validation_alias="FL_HOLDINGS_FILE"
    )
    llm_mode: Literal["live", "replay"] = Field(default="live", validation_alias="FL_LLM_MODE")
    gemini_api_key: SecretStr | None = Field(default=None, validation_alias="GEMINI_API_KEY")
    groq_api_key: SecretStr | None = Field(default=None, validation_alias="GROQ_API_KEY")

    def sqlalchemy_url(self) -> str:
        """URL for SQLAlchemy with the psycopg driver; an explicit driver is kept."""
        prefix = "postgresql://"
        if self.database_url.startswith(prefix):
            return "postgresql+psycopg://" + self.database_url[len(prefix) :]
        return self.database_url

    def test_database_url(self) -> str:
        """Same server as ``database_url`` with the database named ``filinglens_test``."""
        parts = urlsplit(self.database_url)
        return urlunsplit(parts._replace(path="/filinglens_test"))

    def is_local_database(self) -> bool:
        return urlsplit(self.database_url).hostname in _LOCAL_HOSTS

    def describe(self) -> dict[str, str]:
        """Non-secret summary of the settings; secrets appear only as set / not set."""
        parts = urlsplit(self.database_url)
        host = parts.hostname or "?"
        if ":" in host:
            host = f"[{host}]"
        db = host if parts.port is None else f"{host}:{parts.port}"

        def flag(value: object) -> str:
            return "set" if value else "not set"

        return {
            "sec_user_agent": flag(self.sec_user_agent),
            "database": db,
            "data_dir": str(self.data_dir),
            "licensed_dir": flag(self.licensed_dir),
            "holdings_file": flag(self.holdings_file),
            "llm_mode": self.llm_mode,
            "gemini_api_key": flag(self.gemini_api_key),
            "groq_api_key": flag(self.groq_api_key),
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
