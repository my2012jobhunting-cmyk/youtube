"""Application configuration utilities."""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import List, Optional

from youtube_transcript_api.proxies import WebshareProxyConfig


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
    request_timeout: Optional[float] = None


@dataclass
class NotionConfig:
    """Configuration required to upload results to Notion."""

    api_key: Optional[str] = None
    database_id: Optional[str] = None
    parent_page_id: Optional[str] = None


@dataclass
class TranscriptConfig:
    """Configuration for fetching YouTube transcripts."""

    webshare_username: Optional[str] = None
    webshare_password: Optional[str] = None
    webshare_domain: str = WebshareProxyConfig.DEFAULT_DOMAIN_NAME
    webshare_port: int = WebshareProxyConfig.DEFAULT_PORT
    webshare_locations: List[str] = field(default_factory=list)
    webshare_retries: int = 10

    def build_proxy_config(self) -> Optional[WebshareProxyConfig]:
        """Return a Webshare proxy configuration when credentials are available."""

        if not self.webshare_username or not self.webshare_password:
            return None

        return WebshareProxyConfig(
            proxy_username=self.webshare_username,
            proxy_password=self.webshare_password,
            filter_ip_locations=self.webshare_locations or None,
            retries_when_blocked=self.webshare_retries,
            domain_name=self.webshare_domain,
            proxy_port=self.webshare_port,
        )


@dataclass
class AppConfig:
    """Aggregate configuration for the CLI application."""

    youtube: YouTubeConfig = field(default_factory=YouTubeConfig)
    gemini: GeminiConfig = field(default_factory=GeminiConfig)
    notion: NotionConfig = field(default_factory=NotionConfig)
    transcript: TranscriptConfig = field(default_factory=TranscriptConfig)


def load_config_from_env() -> AppConfig:
    """Load configuration values from environment variables."""

    
    youtube = YouTubeConfig(
        client_secrets_file=os.getenv("YOUTUBE_CLIENT_SECRETS", "client_secret.json"),
        token_file=os.getenv("YOUTUBE_TOKEN_FILE", "token.json"),
    )

    timeout_env = os.getenv("GEMINI_TIMEOUT")
    try:
        timeout_value: Optional[float] = float(timeout_env) if timeout_env else 120.0
    except ValueError:
        timeout_value = 300.0

    gemini = GeminiConfig(
        api_key=os.getenv("GEMINI_API_KEY"),
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        request_timeout=timeout_value,
    )

    webshare_locations_env = os.getenv("WEBSHARE_LOCATIONS")
    webshare_locations = (
        [entry.strip() for entry in webshare_locations_env.split(",") if entry.strip()]
        if webshare_locations_env
        else []
    )
    try:
        webshare_port = int(os.getenv("WEBSHARE_PORT", str(WebshareProxyConfig.DEFAULT_PORT)))
    except ValueError:
        webshare_port = WebshareProxyConfig.DEFAULT_PORT
    try:
        webshare_retries = int(os.getenv("WEBSHARE_RETRIES", "10"))
    except ValueError:
        webshare_retries = 10

    transcript = TranscriptConfig(
        webshare_username=os.getenv("WEBSHARE_USERNAME"),
        webshare_password=os.getenv("WEBSHARE_PASSWORD"),
        webshare_domain=os.getenv(
            "WEBSHARE_DOMAIN", WebshareProxyConfig.DEFAULT_DOMAIN_NAME
        ),
        webshare_port=webshare_port,
        webshare_locations=webshare_locations,
        webshare_retries=webshare_retries,
    )

    notion = NotionConfig(
        api_key= os.getenv("NOTION_API_KEY"),
        database_id= os.getenv("NOTION_DATABASE_ID"),
        parent_page_id= os.getenv("NOTION_PARENT_PAGE_ID"),
    )

    return AppConfig(
        youtube=youtube,
        gemini=gemini,
        notion=notion,
        transcript=transcript,
    )


__all__ = [
    "AppConfig",
    "GeminiConfig",
    "NotionConfig",
    "TranscriptConfig",
    "YouTubeConfig",
    "YOUTUBE_READONLY_SCOPE",
    "load_config_from_env",
]
