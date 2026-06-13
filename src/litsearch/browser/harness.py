"""Small Playwright-backed browser harness.

The module keeps Playwright optional so normal metadata workflows and unit tests
do not require browser binaries. The CLI raises a clear validation error when a
real browser action is requested without Playwright installed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from litsearch.config import Settings
from litsearch.exceptions import LitSearchValidationError

LoginState = Literal["authenticated", "login_required", "unknown"]


@dataclass(frozen=True)
class BrowserSnapshot:
    """Files and login-state signal captured from one browser page."""

    url: str
    title: str
    login_state: LoginState
    html_path: Path
    screenshot_path: Path | None


def detect_login_state(
    html: str,
    *,
    login_text: str | None = None,
    authenticated_text: str | None = None,
) -> LoginState:
    """Infer login state from simple text markers in captured HTML."""

    lowered = html.casefold()
    if authenticated_text and authenticated_text.casefold() in lowered:
        return "authenticated"
    if login_text and login_text.casefold() in lowered:
        return "login_required"
    return "unknown"


def _safe_snapshot_stem(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.replace(":", "_") or "page"
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{host}"


class BrowserHarness:
    """Open pages, capture diagnostics, and infer whether login is needed."""

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
        """Open a URL and save HTML plus an optional screenshot."""

        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - depends on optional package
            raise LitSearchValidationError(
                "Playwright is required for browser inspect. Install it and run "
                "`playwright install chromium`, or use browser download archive commands only."
            ) from exc

        snapshot_dir = output_dir or self.settings.browser_snapshot_dir
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        stem = _safe_snapshot_stem(url)
        html_path = snapshot_dir / f"{stem}.html"
        screenshot_path = snapshot_dir / f"{stem}.png" if screenshot else None

        with sync_playwright() as playwright:
            if self.settings.browser_cdp_url:
                browser = playwright.chromium.connect_over_cdp(self.settings.browser_cdp_url)
                context = browser.contexts[0] if browser.contexts else browser.new_context()
                should_close_context = False
            else:
                browser = playwright.chromium.launch(headless=self.settings.browser_headless)
                context = browser.new_context(accept_downloads=True)
                should_close_context = True
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded")
            if wait_milliseconds > 0:
                page.wait_for_timeout(wait_milliseconds)
            title = page.title()
            html = page.content()
            html_path.write_text(html, encoding="utf-8")
            if screenshot_path:
                page.screenshot(path=str(screenshot_path), full_page=True)
            page.close()
            if should_close_context:
                context.close()
            browser.close()

        return BrowserSnapshot(
            url=url,
            title=title,
            login_state=detect_login_state(
                html,
                login_text=login_text,
                authenticated_text=authenticated_text,
            ),
            html_path=html_path,
            screenshot_path=screenshot_path,
        )
