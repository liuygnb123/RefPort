"""Application settings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from litsearch.log_utils import SECRET_MASK, mask_secret


class Settings(BaseSettings):
    """Environment-backed settings for the CLI."""

    model_config = SettingsConfigDict(
        env_prefix="LITSEARCH_",
        env_file=".env",
        extra="ignore",
    )

    db_url: str = "sqlite:///./data/litsearch.db"
    download_dir: Path = Path("./data/downloads")
    paper_dir: Path = Path("./data/papers")
    browser_snapshot_dir: Path = Path("./data/browser_snapshots")
    browser_cdp_url: str | None = None
    browser_headless: bool = True
    log_level: str = "INFO"
    http_timeout_seconds: int = 30
    proxy_url: str | None = None

    contact_email: str | None = None
    crossref_email: str | None = None
    openalex_email: str | None = None
    unpaywall_email: str | None = None

    ieee_api_key: str | None = Field(default=None, repr=False)
    scopus_api_key: str | None = Field(default=None, repr=False)
    scopus_inst_token: str | None = Field(default=None, repr=False)
    wos_api_key: str | None = Field(default=None, repr=False)

    def safe_dump(self) -> dict[str, Any]:
        """Return settings with credentials masked."""

        data = self.model_dump(mode="json")
        for key in ("ieee_api_key", "scopus_api_key", "scopus_inst_token", "wos_api_key"):
            if data.get(key):
                data[key] = SECRET_MASK
        if data.get("proxy_url"):
            data["proxy_url"] = mask_secret(data["proxy_url"])
        return data

    def source_email(self, source_id: str) -> str | None:
        """Return source-specific email, falling back to contact email."""

        specific = getattr(self, f"{source_id}_email", None)
        return specific or self.contact_email


def get_settings() -> Settings:
    """Load settings from the current environment."""

    return Settings()
