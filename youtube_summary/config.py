"""Application configuration utilities."""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import List, Optional


YOUTUBE_READONLY_SCOPE = "https://www.googleapis.com/auth/youtube.readonly"


@dataclass
class YouTubeConfig:
    """Configuration required to access the YouTube Data API."""

    client_secrets_file: str = "client_secret.json"
    token_file: str = "token.json"
    scopes: List[str] = field(default_factory=lambda: [YOUTUBE_READONLY_SCOPE])


@dataclass
class GeminiConfig:
    """Configuration required to access the Gemini API."""

    api_key: Optional[str] = None
    model: str = "gemini-1.5-flash"


@dataclass
class NotionConfig:
    """Configuration required to upload results to Notion."""

    api_key: Optional[str] = None
    database_id: Optional[str] = None
    parent_page_id: Optional[str] = None


@dataclass
class AppConfig:
    """Aggregate configuration for the CLI application."""

    youtube: YouTubeConfig = field(default_factory=YouTubeConfig)
    gemini: GeminiConfig = field(default_factory=GeminiConfig)
    notion: NotionConfig = field(default_factory=NotionConfig)


def load_config_from_env() -> AppConfig:
    """Load configuration values from environment variables."""

    youtube = YouTubeConfig(
        client_secrets_file=os.getenv("YOUTUBE_CLIENT_SECRETS", "client_secret.json"),
        token_file=os.getenv("YOUTUBE_TOKEN_FILE", "token.json"),
    )

    gemini = GeminiConfig(
        api_key=os.getenv("GEMINI_API_KEY"),
        model=os.getenv("GEMINI_MODEL", "gemini-1.5-flash"),
    )

    notion = NotionConfig(
        api_key=os.getenv("NOTION_API_KEY"),
        database_id=os.getenv("NOTION_DATABASE_ID"),
        parent_page_id=os.getenv("NOTION_PARENT_PAGE_ID"),
    )

    return AppConfig(youtube=youtube, gemini=gemini, notion=notion)


__all__ = [
    "AppConfig",
    "GeminiConfig",
    "NotionConfig",
    "YouTubeConfig",
    "YOUTUBE_READONLY_SCOPE",
    "load_config_from_env",
]
