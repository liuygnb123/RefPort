"""Local paper file management."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlmodel import Session, select

from litsearch.config import Settings
from litsearch.db.session import create_db_engine, init_database
from litsearch.exceptions import LitSearchValidationError
from litsearch.models import Download, DownloadStatus, Paper


@dataclass(frozen=True)
class PaperFile:
    paper_id: int
    title: str
    year: int | None
    file_path: Path
    size_bytes: int | None
    sha256: str | None
    download_id: int | None


class FileService:
    """Manage locally stored paper files."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def paper_root(self, output_dir: Path | None = None) -> Path:
        return (output_dir or self.settings.paper_dir).expanduser()

    def paper_directory(self, paper: Paper, output_dir: Path | None = None) -> Path:
        year = str(paper.publication_year) if paper.publication_year else "unknown"
        return self.paper_root(output_dir) / year / str(paper.id)

    def write_paper_files(
        self,
        paper: Paper,
        pdf_bytes: bytes,
        metadata: dict,
        *,
        output_dir: Path | None = None,
    ) -> Path:
        directory = self.paper_directory(paper, output_dir)
        directory.mkdir(parents=True, exist_ok=True)
        pdf_path = directory / "paper.pdf"
        pdf_path.write_bytes(pdf_bytes)
        (directory / "metadata.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )
        return pdf_path

    def list_files(self) -> list[PaperFile]:
        init_database(self.settings)
        engine = create_db_engine(self.settings)
        with Session(engine) as session:
            downloads = session.exec(
                select(Download)
                .where(Download.status == DownloadStatus.downloaded)
                .order_by(Download.id.desc())
            ).all()
            files: list[PaperFile] = []
            seen: set[int] = set()
            for download in downloads:
                if download.paper_id in seen or not download.file_path:
                    continue
                path = Path(download.file_path)
                if not path.is_file():
                    continue
                paper = session.get(Paper, download.paper_id)
                if not paper:
                    continue
                seen.add(download.paper_id)
                files.append(
                    PaperFile(
                        paper_id=paper.id or download.paper_id,
                        title=paper.title,
                        year=paper.publication_year,
                        file_path=path,
                        size_bytes=download.size_bytes,
                        sha256=download.sha256,
                        download_id=download.id,
                    )
                )
            return files

    def file_for_paper(self, paper_id: int) -> PaperFile | None:
        init_database(self.settings)
        engine = create_db_engine(self.settings)
        with Session(engine) as session:
            paper = session.get(Paper, paper_id)
            if not paper:
                raise LitSearchValidationError(f"Paper not found: {paper_id}")
            downloads = session.exec(
                select(Download)
                .where(
                    Download.paper_id == paper_id,
                    Download.status == DownloadStatus.downloaded,
                )
                .order_by(Download.id.desc())
            ).all()
            for download in downloads:
                if download.file_path and Path(download.file_path).is_file():
                    return PaperFile(
                        paper_id=paper_id,
                        title=paper.title,
                        year=paper.publication_year,
                        file_path=Path(download.file_path),
                        size_bytes=download.size_bytes,
                        sha256=download.sha256,
                        download_id=download.id,
                    )
            return None

    def open_file(self, paper_id: int) -> Path:
        paper_file = self.file_for_paper(paper_id)
        if not paper_file:
            raise LitSearchValidationError(f"No downloaded file found for paper: {paper_id}")
        if sys.platform == "darwin":
            subprocess.run(["open", str(paper_file.file_path)], check=False)
        return paper_file.file_path
