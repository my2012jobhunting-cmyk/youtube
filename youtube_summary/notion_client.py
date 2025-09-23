"""Helpers for exporting summaries to Notion."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional

import requests

from .config import NotionConfig
from .gemini_client import GeminiSummary

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
                            "text": {"content": entry.video.title},
                        }
                    ],
                },
            }
        )
        blocks.append(
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {
                            "type": "text",
                            "text": {
                                "content": entry.summary,
                                "link": {"url": entry.video.url},
                            },
                        }
                    ]
                },
            }
        )
    return blocks


__all__ = ["NotionUploader", "NotionResult"]
