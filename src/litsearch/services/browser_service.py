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
    PaperSummary,
    detect_manual_block,
    parse_snapshot,
)
from litsearch.config import Settings
from litsearch.db.session import create_db_engine
from litsearch.exceptions import LitSearchValidationError
from litsearch.models import (
    BrowserImport,
    BrowserLoginState,
    BrowserPlatform,
    BrowserSession,
    BrowserSessionStatus,
    BrowserSnapshotRecord,
    Download,
    DownloadStatus,
    Paper,
)
from litsearch.services.persistence import upsert_source_paper


@dataclass(frozen=True)
class ArchivedDownload:
    """A file archived into the downloads table."""

    download_id: int
    paper_id: int
    file_path: Path
    sha256: str
    size_bytes: int


@dataclass(frozen=True)
class BrowserImportSummary:
    """Result of importing parsed browser candidates."""

    session_id: int
    snapshot_id: int
    imported_count: int
    paper_ids: list[int]


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

    def start_session(self, platform: str, entry_url: str) -> BrowserSession:
        """Create a browser collection session."""

        self._validate_platform(platform)
        engine = create_db_engine(self.settings)
        with Session(engine) as session:
            browser_session = BrowserSession(platform=platform, entry_url=entry_url)
            session.add(browser_session)
            session.commit()
            session.refresh(browser_session)
            return browser_session

    def list_sessions(self, limit: int = 50) -> list[BrowserSession]:
        """List recent browser collection sessions."""

        engine = create_db_engine(self.settings)
        with Session(engine) as session:
            return list(
                session.exec(
                    select(BrowserSession).order_by(BrowserSession.id.desc()).limit(limit)
                ).all()
            )

    def get_session(self, session_id: int) -> BrowserSession | None:
        """Return one browser collection session."""

        engine = create_db_engine(self.settings)
        with Session(engine) as session:
            return session.get(BrowserSession, session_id)

    def capture_session_snapshot(
        self,
        session_id: int,
        *,
        login_text: str | None = None,
        authenticated_text: str | None = None,
        screenshot: bool = True,
        wait_milliseconds: int = 1500,
    ) -> BrowserSnapshotRecord:
        """Capture and persist a browser snapshot for a session."""

        engine = create_db_engine(self.settings)
        with Session(engine) as session:
            browser_session = session.get(BrowserSession, session_id)
            if not browser_session:
                raise LitSearchValidationError(f"Browser session not found: {session_id}")

        snapshot = self.inspect_page(
            browser_session.entry_url,
            output_dir=self.settings.browser_snapshot_dir,
            login_text=login_text,
            authenticated_text=authenticated_text,
            screenshot=screenshot,
            wait_milliseconds=wait_milliseconds,
        )
        html = snapshot.html_path.read_text(encoding="utf-8")
        blocked_reason = detect_manual_block(html)
        login_state = snapshot.login_state
        status = BrowserSessionStatus.snapshotted.value
        if blocked_reason:
            login_state = BrowserLoginState.blocked_manual_action_required.value
            status = BrowserSessionStatus.blocked_manual_action_required.value
        elif snapshot.login_state == BrowserLoginState.login_required.value:
            status = BrowserSessionStatus.blocked_manual_action_required.value

        with Session(engine) as session:
            browser_session = session.get(BrowserSession, session_id)
            if not browser_session:  # pragma: no cover - defensive
                raise LitSearchValidationError(f"Browser session not found: {session_id}")
            record = BrowserSnapshotRecord(
                session_id=session_id,
                url=snapshot.url,
                title=snapshot.title,
                html_path=str(snapshot.html_path),
                screenshot_path=str(snapshot.screenshot_path) if snapshot.screenshot_path else None,
                login_state=login_state,
                blocked_reason=blocked_reason,
            )
            browser_session.status = status
            browser_session.login_state = login_state
            browser_session.error = (
                f"Manual action required: {blocked_reason}" if blocked_reason else None
            )
            session.add(browser_session)
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def parse_session(self, session_id: int) -> list[PaperSummary]:
        """Parse the latest saved snapshot for a session."""

        engine = create_db_engine(self.settings)
        with Session(engine) as session:
            browser_session = session.get(BrowserSession, session_id)
            if not browser_session:
                raise LitSearchValidationError(f"Browser session not found: {session_id}")
            snapshot = self._latest_snapshot(session, session_id)
            if not snapshot:
                raise LitSearchValidationError(f"Browser session has no snapshots: {session_id}")
            if self._snapshot_requires_manual_action(snapshot):
                raise LitSearchValidationError(
                    f"Browser session requires manual action before parsing: {session_id}"
                )
            summaries = parse_snapshot(
                Path(snapshot.html_path),
                browser_session.platform,
                base_url=snapshot.url,
            )
            browser_session.status = BrowserSessionStatus.parsed.value
            session.add(browser_session)
            session.commit()
            return summaries

    def import_session(self, session_id: int) -> BrowserImportSummary:
        """Parse and import the latest saved snapshot into papers and paper_sources."""

        engine = create_db_engine(self.settings)
        with Session(engine) as session:
            browser_session = session.get(BrowserSession, session_id)
            if not browser_session:
                raise LitSearchValidationError(f"Browser session not found: {session_id}")
            snapshot = self._latest_snapshot(session, session_id)
            if not snapshot:
                raise LitSearchValidationError(f"Browser session has no snapshots: {session_id}")
            if self._snapshot_requires_manual_action(snapshot):
                raise LitSearchValidationError(
                    f"Browser session requires manual action before importing: {session_id}"
                )
            summaries = parse_snapshot(
                Path(snapshot.html_path),
                browser_session.platform,
                base_url=snapshot.url,
            )
            paper_ids: list[int] = []
            for summary in summaries:
                paper = upsert_source_paper(
                    session,
                    summary.to_source_paper(browser_session.platform),
                )
                if paper.id is None:  # pragma: no cover - defensive
                    session.flush()
                existing_import = session.exec(
                    select(BrowserImport).where(
                        BrowserImport.session_id == session_id,
                        BrowserImport.paper_id == paper.id,
                    )
                ).first()
                if not existing_import:
                    session.add(
                        BrowserImport(
                            session_id=session_id,
                            snapshot_id=snapshot.id,
                            paper_id=paper.id,
                        )
                    )
                paper_ids.append(paper.id)
            browser_session.status = BrowserSessionStatus.imported.value
            session.add(browser_session)
            session.commit()
            return BrowserImportSummary(
                session_id=session_id,
                snapshot_id=snapshot.id or 0,
                imported_count=len(paper_ids),
                paper_ids=paper_ids,
            )

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

    def _latest_snapshot(
        self,
        session: Session,
        session_id: int,
    ) -> BrowserSnapshotRecord | None:
        return session.exec(
            select(BrowserSnapshotRecord)
            .where(BrowserSnapshotRecord.session_id == session_id)
            .order_by(BrowserSnapshotRecord.id.desc())
        ).first()

    def _validate_platform(self, platform: str) -> None:
        allowed = {item.value for item in BrowserPlatform}
        if platform not in allowed:
            raise LitSearchValidationError(
                f"Unsupported browser platform: {platform}. Expected one of: "
                f"{', '.join(sorted(allowed))}"
            )

    def _snapshot_requires_manual_action(self, snapshot: BrowserSnapshotRecord) -> bool:
        return snapshot.login_state in {
            BrowserLoginState.blocked_manual_action_required.value,
            BrowserLoginState.login_required.value,
        }
