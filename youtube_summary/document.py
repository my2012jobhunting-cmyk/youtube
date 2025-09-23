"""Document generation helpers."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, List, Optional

from .gemini_client import GeminiSummary


@dataclass
class Document:
    title: str
    body: str


def build_markdown_document(
    title: str,
    summaries: Iterable[GeminiSummary],
    *,
    start_time: datetime,
    end_time: Optional[datetime],
) -> Document:
    """Create a Markdown document for the provided summaries."""

    lines: List[str] = [f"# {title}", ""]
    if end_time:
        lines.append(
            f"Time window: {start_time.isoformat()} — {end_time.isoformat()}"
        )
    else:
        lines.append(f"Time window starting from {start_time.isoformat()}")
    lines.append("")

    for entry in summaries:
        lines.append(f"## {entry.video.title}")
        lines.append(f"*Channel:* {entry.video.channel_title}")
        lines.append(f"*Published:* {entry.video.published_at.isoformat()}")
        lines.append(f"*Link:* {entry.video.url}")
        lines.append("")
        lines.append(entry.summary)
        lines.append("")

    body = "\n".join(lines).strip() + "\n"
    return Document(title=title, body=body)


__all__ = ["Document", "build_markdown_document"]
