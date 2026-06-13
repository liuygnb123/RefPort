"""Helpers for observing browser download directories."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

TEMP_DOWNLOAD_SUFFIXES = (".crdownload", ".part", ".tmp")


@dataclass(frozen=True)
class DownloadedFile:
    """A completed file found in a browser download directory."""

    path: Path
    size_bytes: int
    modified_at: float


class BrowserDownloadWatcher:
    """Compare directory snapshots and return newly completed downloads."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def snapshot(self) -> set[Path]:
        """Return the current completed files under the watched directory."""

        return {item.path for item in self.list_completed()}

    def list_completed(self) -> list[DownloadedFile]:
        """List completed files, ignoring browser temporary download files."""

        if not self.directory.exists():
            return []
        files: list[DownloadedFile] = []
        for path in self.directory.iterdir():
            if not path.is_file() or path.name.startswith("."):
                continue
            if path.suffix.lower() in TEMP_DOWNLOAD_SUFFIXES:
                continue
            stat = path.stat()
            files.append(
                DownloadedFile(path=path, size_bytes=stat.st_size, modified_at=stat.st_mtime)
            )
        return sorted(files, key=lambda item: item.modified_at, reverse=True)

    def new_completed_since(self, before: set[Path]) -> list[DownloadedFile]:
        """Return completed files that were not present in a prior snapshot."""

        return [item for item in self.list_completed() if item.path not in before]
