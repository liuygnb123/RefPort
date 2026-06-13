"""Browser collection infrastructure."""

from litsearch.browser.downloads import BrowserDownloadWatcher, DownloadedFile
from litsearch.browser.harness import BrowserHarness, BrowserSnapshot, LoginState

__all__ = [
    "BrowserDownloadWatcher",
    "BrowserHarness",
    "BrowserSnapshot",
    "DownloadedFile",
    "LoginState",
]
