"""Browser collection infrastructure."""

from litsearch.browser.downloads import BrowserDownloadWatcher, DownloadedFile
from litsearch.browser.harness import BrowserHarness, BrowserSnapshot, LoginState
from litsearch.browser.parsers import PaperSummary, detect_manual_block, parse_snapshot

__all__ = [
    "BrowserDownloadWatcher",
    "BrowserHarness",
    "BrowserSnapshot",
    "DownloadedFile",
    "LoginState",
    "PaperSummary",
    "detect_manual_block",
    "parse_snapshot",
]
