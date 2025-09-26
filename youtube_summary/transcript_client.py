"""Utilities for fetching YouTube video transcripts."""
from __future__ import annotations

from dataclasses import dataclass, field
import logging
from typing import List, Optional

from youtube_transcript_api import (
    NoTranscriptFound,
    TranscriptsDisabled,
    YouTubeTranscriptApi,
    YouTubeTranscriptApiException,
)
from youtube_transcript_api.proxies import ProxyConfig

_DEFAULT_LANGUAGES = [
    "zh-Hans",
    "zh-Hant",
    "zh-CN",
    "zh",
    "en",
]


def _format_timestamp(seconds: int) -> str:
    """Return a human-friendly timestamp for the given second count."""

    safe_seconds = max(seconds, 0)
    return f"{safe_seconds}s"


def _build_timestamp_url(video_id: str, video_url: Optional[str], seconds: int) -> str:
    """Compose a YouTube URL that jumps to the given timestamp."""

    base_url = (video_url or "").strip() or f"https://www.youtube.com/watch?v={video_id}"
    separator = "&" if "?" in base_url else "?"
    return f"{base_url}{separator}t={seconds}s"


@dataclass
class TranscriptFetcher:
    """Fetch transcripts for YouTube videos."""

    preferred_languages: Optional[List[str]] = None
    proxy_config: Optional[ProxyConfig] = None
    _client: YouTubeTranscriptApi = field(init=False, repr=False)
    _logger = logging.getLogger(__name__)
    _log_prefix = "[gemini_summary_log]"

    @classmethod
    def _log_error(cls, message: str, *args) -> None:
        cls._logger.error("%s " + message, cls._log_prefix, *args)

    @classmethod
    def _log_debug(cls, message: str, *args) -> None:
        cls._logger.debug("%s " + message, cls._log_prefix, *args)

    def __post_init__(self) -> None:
        self._client = YouTubeTranscriptApi(proxy_config=self.proxy_config)

    def fetch(self, video_id: str, *, video_url: Optional[str] = None) -> Optional[str]:
        """Return the transcript text for the given video ID if available."""

        if self.preferred_languages:
            candidate_languages = list(
                dict.fromkeys(self.preferred_languages + _DEFAULT_LANGUAGES)
            )
        else:
            candidate_languages = _DEFAULT_LANGUAGES

        try:
            transcript = self._client.fetch(video_id, languages=candidate_languages)
        except Exception as error:  # pylint: disable=broad-except
            self._log_error("Transcript fetch failed for %s: %s", video_id, error)
            return None
        lines: List[str] = []
        for snippet in transcript.to_raw_data():
            text = snippet.get("text", "").strip()
            if not text:
                continue
            start = snippet.get("start")
            if start is not None:
                try:
                    timestamp_seconds = max(int(float(start)), 0)
                except (TypeError, ValueError):
                    timestamp_seconds = 0
                timestamp = _format_timestamp(timestamp_seconds)
                timestamp_url = _build_timestamp_url(
                    video_id, video_url, timestamp_seconds
                )
                lines.append(f"[{timestamp}]({timestamp_url}) {text}")
            else:
                lines.append(text)

        cleaned = "\n".join(lines).strip()
        if cleaned:
            self._log_debug(
                "Returning transcript for %s with %d lines.", video_id, len(lines)
            )
        return cleaned or None


__all__ = ["TranscriptFetcher"]
