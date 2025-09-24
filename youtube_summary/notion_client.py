"""Helpers for exporting summaries to Notion."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable, List, Optional

import requests
from urllib.parse import parse_qs, urlparse

from youtube_summary.config import NotionConfig
from youtube_summary.gemini_client import GeminiSummary

NOTION_API_VERSION = "2022-06-28"


@dataclass
class NotionResult:
    success: bool
    page_id: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None


class NotionUploader:
    """Upload generated summaries to a Notion database or page."""

    def __init__(self, config: NotionConfig):
        if not config.api_key:
            raise ValueError("A Notion integration token must be provided via NOTION_API_KEY.")
        if not config.database_id and not config.parent_page_id:
            raise ValueError(
                "Provide either NOTION_DATABASE_ID or NOTION_PARENT_PAGE_ID to store the summaries."
            )

        self._config = config
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {config.api_key}",
                "Content-Type": "application/json",
                "Notion-Version": NOTION_API_VERSION,
            }
        )

    def upload(self, title: str, entries: Iterable[GeminiSummary]) -> NotionResult:
        """Create a page in Notion with the provided summaries."""

        blocks = _build_blocks(entries)
        payload = {
            "properties": {
                "title": {
                    "title": [
                        {
                            "type": "text",
                            "text": {"content": title},
                        }
                    ]
                }
            },
            "children": blocks,
        }

        if self._config.database_id:
            payload["parent"] = {"database_id": self._config.database_id}
        else:
            payload["parent"] = {"page_id": self._config.parent_page_id}

        response = self._session.post("https://api.notion.com/v1/pages", json=payload, timeout=60)
        if response.ok:
            data = response.json()
            return NotionResult(success=True, page_id=data.get("id"), url=data.get("url"))

        return NotionResult(success=False, error=response.text)


def _chunk_text(text: str, *, limit: int = 1900) -> List[str]:
    """Split text into chunks that stay within Notion's 2000 char limit."""

    if not text:
        return [""]

    return [text[index : index + limit] for index in range(0, len(text), limit)]


_MARKDOWN_LINK_PATTERN = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_PARENS_LINK_PATTERN = re.compile(r"[（(](https?://[^()（）\s]+)[)）]")


def _normalise_markdown_links(text: str) -> str:
    """Convert bare parentheses YouTube links to Markdown format."""

    if not text:
        return text

    def _replace(match: re.Match[str]) -> str:
        url = match.group(1)
        label = _label_for_timestamp_url(url) or url
        preceding = match.string[: match.start()]
        needs_space = bool(preceding) and not preceding[-1].isspace()
        prefix = " " if needs_space else ""
        return f"{prefix}[{label}]({url})"

    converted = _PARENS_LINK_PATTERN.sub(_replace, text)
    converted = re.sub(r"(?:\[\d{1,2}:\d{2}]\s*)+(?=\[\d+s]\()", "", converted)
    converted = re.sub(r"(?:\[\d+s]\s*)+(?=\[\d+s]\()", "", converted)
    return converted


def _label_for_timestamp_url(url: str) -> Optional[str]:
    """Derive a short label for a YouTube timestamp URL."""

    try:
        parsed = urlparse(url)
    except Exception:  # pragma: no cover - defensive
        return None

    query = parse_qs(parsed.query)
    values = query.get("t")
    if not values:
        return None

    raw_value = values[0]
    if raw_value.endswith("s"):
        raw_seconds = raw_value[:-1]
    else:
        raw_seconds = raw_value

    try:
        seconds = max(int(raw_seconds), 0)
    except ValueError:
        return None

    if raw_value.endswith("s"):
        return f"{seconds}s"

    return f"{seconds}s"


def _build_blocks(entries: Iterable[GeminiSummary]) -> List[dict]:
    blocks: List[dict] = []
    for entry in entries:
        blocks.append(
            {
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": entry.video.title,
                                "link": {"url": entry.video.url} if entry.video.url else None,
                            },
                        }
                    ],
                },
            }
        )
        blocks.extend(_build_summary_blocks(entry.summary))
    return blocks


def _text_to_rich_text(text: str) -> List[dict]:
    """Convert plain text into Notion rich text segments respecting length limits."""

    if not text:
        return []

    text = _normalise_markdown_links(text)

    rich_text: List[dict] = []
    cursor = 0
    for match in _MARKDOWN_LINK_PATTERN.finditer(text):
        start, end = match.span()
        if start > cursor:
            rich_text.extend(_plain_text_segments(text[cursor:start]))

        label = match.group(1).strip()
        url = match.group(2).strip()
        if label:
            rich_text.append(
                {
                    "type": "text",
                    "text": {
                        "content": label,
                        "link": {"url": url} if url else None,
                    },
                }
            )
        cursor = end

    if cursor < len(text):
        rich_text.extend(_plain_text_segments(text[cursor:]))

    rich_text = _dedupe_timestamp_segments(rich_text)
    return [segment for segment in rich_text if segment["text"].get("content")]


def _plain_text_segments(text: str) -> List[dict]:
    """Return rich-text objects for plain content respecting chunk limits."""

    segments: List[dict] = []
    for chunk in _chunk_text(text):
        if not chunk:
            continue
        segments.append({"type": "text", "text": {"content": chunk}})
    return segments


def _dedupe_timestamp_segments(segments: List[dict]) -> List[dict]:
    """Remove duplicate plain-text timestamps following linked timestamps."""

    if not segments:
        return segments

    result: List[dict] = []
    for segment in segments:
        if result:
            previous = result[-1]
            if _is_timestamp_link(previous) and _strip_duplicate_label(previous, segment):
                if segment["text"].get("content"):
                    result.append(segment)
                continue
        result.append(segment)

    return result


def _is_timestamp_link(segment: dict) -> bool:
    text_payload = segment.get("text", {})
    label = text_payload.get("content", "").strip()
    has_link = bool(text_payload.get("link", {}).get("url"))
    return has_link and bool(re.fullmatch(r"\d+s", label))


def _strip_duplicate_label(previous: dict, current: dict) -> bool:
    """Remove duplicate timestamp text content if it matches the previous link label."""

    label = previous["text"]["content"].strip()
    current_text = current.get("text", {}).get("content", "")
    if not current_text:
        return False

    leading_spaces_len = len(current_text) - len(current_text.lstrip())
    leading = current_text[:leading_spaces_len]
    trimmed = current_text.lstrip()
    if not trimmed.startswith(label):
        return False

    remainder = trimmed[len(label) :]
    if remainder and any(char.isalnum() for char in remainder):
        return False

    current["text"]["content"] = f"{leading}{remainder}" if remainder else leading
    return True


def _build_summary_blocks(summary: Optional[str]) -> List[dict]:
    """Convert a summary string into Notion blocks, preserving bullet structure."""

    if not summary:
        return [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "(No summary available)"}}
                    ]
                },
            }
        ]

    blocks: List[dict] = []
    bullet_markers = ("- ", "* ", "• ")
    for raw_line in summary.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue

        block_type = "paragraph"
        content = _normalise_markdown_links(stripped)
        for marker in bullet_markers:
            if stripped.startswith(marker):
                block_type = "bulleted_list_item"
                content = _normalise_markdown_links(stripped[len(marker) :].strip())
                break

        rich_text = _text_to_rich_text(content)
        if not rich_text:
            continue

        blocks.append(
            {
                "object": "block",
                "type": block_type,
                block_type: {"rich_text": rich_text},
            }
        )

    if not blocks:
        fallback_text = summary.strip() or "(No summary available)"
        rich_text = _text_to_rich_text(fallback_text)
        if not rich_text:
            rich_text = [{"type": "text", "text": {"content": "(No summary available)"}}]
        blocks.append(
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {"rich_text": rich_text},
            }
        )

    return blocks


__all__ = ["NotionUploader", "NotionResult"]
