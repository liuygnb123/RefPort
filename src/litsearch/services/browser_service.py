"""Browser infrastructure service."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from sqlmodel import Session, select

from litsearch.browser import (
    BrowserDownloadWatcher,
    BrowserHarness,
    BrowserSnapshot,
    DownloadedFile,
)
from litsearch.config import Settings
from litsearch.db.session import create_db_engine
from litsearch.exceptions import LitSearchValidationError
from litsearch.models import Download, DownloadStatus, Paper


@dataclass(frozen=True)
class ArchivedDownload:
    """A file archived into the downloads table."""

    download_id: int
    paper_id: int
    file_path: Path
    sha256: str
    size_bytes: int


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class BrowserService:
    """Coordinate browser snapshots and downloaded-file bookkeeping."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def inspect_page(
        self,
        url: str,
        *,
        output_dir: Path | None = None,
        login_text: str | None = None,
        authenticated_text: str | None = None,
        screenshot: bool = True,
        wait_milliseconds: int = 1500,
    ) -> BrowserSnapshot:
        """Capture a page through the browser harness."""

        return BrowserHarness(self.settings).inspect_page(
            url,
            output_dir=output_dir,
            login_text=login_text,
            authenticated_text=authenticated_text,
            screenshot=screenshot,
            wait_milliseconds=wait_milliseconds,
        )

    def list_downloads(self, directory: Path | None = None) -> list[DownloadedFile]:
        """List completed files in a browser download directory."""

        return BrowserDownloadWatcher(directory or self.settings.download_dir).list_completed()

    def archive_download(self, paper_id: int, file_path: Path) -> ArchivedDownload:
        """Record a downloaded browser file against an existing paper."""

        path = file_path.expanduser().resolve()
        if not path.is_file():
            raise LitSearchValidationError(f"Download file not found: {file_path}")

        engine = create_db_engine(self.settings)
        with Session(engine) as session:
            paper = session.exec(select(Paper).where(Paper.id == paper_id)).first()
            if not paper:
                raise LitSearchValidationError(f"Paper not found: {paper_id}")
            stat = path.stat()
            download = Download(
                paper_id=paper_id,
                status=DownloadStatus.downloaded,
                source="browser",
                file_path=str(path),
                sha256=_sha256_file(path),
                size_bytes=stat.st_size,
            )
            session.add(download)
            session.commit()
            session.refresh(download)
            if download.id is None:  # pragma: no cover - defensive
                raise LitSearchValidationError("Download archive did not return an id")
            return ArchivedDownload(
                download_id=download.id,
                paper_id=paper_id,
                file_path=path,
                sha256=download.sha256 or "",
                size_bytes=stat.st_size,
            )
