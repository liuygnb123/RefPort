"""Local HTML snapshot parsers for browser-assisted collection."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

from pydantic import BaseModel, Field

from litsearch.connectors.base import SourcePaper

BLOCKED_TEXT_MARKERS = (
    "captcha",
    "unusual traffic",
    "verify you are human",
    "robot check",
    "安全验证",
    "验证码",
    "登录",
    "sign in",
    "login",
)


class PaperSummary(BaseModel):
    title: str
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    doi: str | None = None
    source_url: str | None = None
    abstract: str | None = None
    raw: dict = Field(default_factory=dict)

    def to_source_paper(self, source: str) -> SourcePaper:
        return SourcePaper(
            source=source,
            title=self.title,
            authors=self.authors,
            publication_year=self.year,
            doi=self.doi,
            source_url=self.source_url,
            abstract=self.abstract,
            raw=self.raw,
        )


@dataclass
class _Node:
    tag: str
    attrs: dict[str, str]
    text: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class _Anchor:
    href: str | None
    text: str


class _SnapshotHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[_Node] = []
        self.title_parts: list[str] = []
        self.headings: list[_Node] = []
        self.anchors: list[_Anchor] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        self.stack.append(_Node(tag=tag.lower(), attrs=attr_map))

    def handle_data(self, data: str) -> None:
        if not self.stack:
            return
        self.stack[-1].text.append(data)

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        for _index in range(len(self.stack) - 1, -1, -1):
            node = self.stack.pop()
            text = _clean_text(" ".join(node.text))
            if text and self.stack:
                self.stack[-1].text.append(text)
            if node.tag == "title" and text:
                self.title_parts.append(text)
            if node.tag in {"h1", "h2", "h3"} and text:
                self.headings.append(_Node(tag=node.tag, attrs=node.attrs, text=[text]))
            if node.tag == "a" and text:
                self.anchors.append(_Anchor(href=node.attrs.get("href"), text=text))
            if node.tag == lowered:
                break


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _extract_year(text: str) -> int | None:
    match = re.search(r"\b(19\d{2}|20\d{2})\b", text)
    return int(match.group(1)) if match else None


def _extract_doi(text: str) -> str | None:
    match = re.search(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+\b", text, flags=re.IGNORECASE)
    return match.group(0).rstrip(".,;") if match else None


def _split_authors(text: str) -> list[str]:
    text = re.sub(r"\b(19\d{2}|20\d{2})\b", "", text)
    text = re.split(r"\s[-–—]\s|\.{3,}| - ", text, maxsplit=1)[0]
    parts = re.split(r",|;|\band\b|、|，", text)
    return [part.strip() for part in parts if 2 <= len(part.strip()) <= 80]


def detect_manual_block(html: str) -> str | None:
    """Return a blocking marker when a snapshot needs user action."""

    lowered = html.casefold()
    for marker in BLOCKED_TEXT_MARKERS:
        if marker.casefold() in lowered:
            return marker
    return None


def _parse_html(html: str) -> _SnapshotHTMLParser:
    parser = _SnapshotHTMLParser()
    parser.feed(html)
    parser.close()
    return parser


def parse_snapshot(path: Path, platform: str, *, base_url: str | None = None) -> list[PaperSummary]:
    """Parse a saved HTML snapshot into normalized paper candidates."""

    html = path.read_text(encoding="utf-8")
    if platform == "google_scholar":
        return _parse_google_scholar(html, base_url=base_url)
    if platform == "cnki":
        return _parse_cnki(html, base_url=base_url)
    return _parse_generic(html, base_url=base_url)


def _anchor_summaries(html: str, *, base_url: str | None, source_hint: str) -> list[PaperSummary]:
    parser = _parse_html(html)
    summaries: list[PaperSummary] = []
    seen: set[str] = set()
    for anchor in parser.anchors:
        title = _clean_text(anchor.text)
        if len(title) < 8 or title.casefold() in seen:
            continue
        if title.lower() in {"pdf", "html", "download", "view", "引用", "收藏"}:
            continue
        seen.add(title.casefold())
        href = urljoin(base_url, anchor.href) if anchor.href and base_url else anchor.href
        summaries.append(
            PaperSummary(
                title=title,
                year=_extract_year(title),
                doi=_extract_doi(title),
                source_url=href,
                raw={"parser": source_hint, "href": anchor.href},
            )
        )
        if len(summaries) >= 20:
            break
    return summaries


def _parse_generic(html: str, *, base_url: str | None) -> list[PaperSummary]:
    parser = _parse_html(html)
    title = next((node.text[0] for node in parser.headings if node.text), None)
    title = title or (parser.title_parts[0] if parser.title_parts else None)
    if title:
        return [
            PaperSummary(
                title=title,
                year=_extract_year(title),
                doi=_extract_doi(html),
                source_url=base_url,
                raw={"parser": "generic"},
            )
        ]
    return _anchor_summaries(html, base_url=base_url, source_hint="generic")


def _parse_google_scholar(html: str, *, base_url: str | None) -> list[PaperSummary]:
    summaries = _anchor_summaries(html, base_url=base_url, source_hint="google_scholar")
    for item in summaries:
        item.raw["minimal_parser"] = True
    return summaries


def _parse_cnki(html: str, *, base_url: str | None) -> list[PaperSummary]:
    summaries = _anchor_summaries(html, base_url=base_url, source_hint="cnki")
    for item in summaries:
        item.raw["minimal_parser"] = True
    return summaries
