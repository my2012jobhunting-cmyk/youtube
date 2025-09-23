"""Utilities for interacting with the YouTube Data API."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Optional

from googleapiclient.discovery import Resource, build
from googleapiclient.http import HttpRequest
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from .config import YouTubeConfig


@dataclass
class Video:
    """Representation of a YouTube video."""

    video_id: str
    title: str
    description: str
    channel_title: str
    published_at: datetime

    @property
    def url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.video_id}"


class YouTubeClient:
    """Client wrapper around the YouTube Data API."""

    def __init__(self, config: YouTubeConfig):
        self._config = config
        self._service: Optional[Resource] = None

    def authenticate(self) -> Resource:
        """Authenticate with the YouTube API and return a service resource."""

        creds: Optional[Credentials] = None
        if self._config.token_file:
            try:
                creds = Credentials.from_authorized_user_file(
                    self._config.token_file, self._config.scopes
                )
            except FileNotFoundError:
                creds = None

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self._config.client_secrets_file, self._config.scopes
                )
                creds = flow.run_local_server(port=0)
            if self._config.token_file:
                with open(self._config.token_file, "w", encoding="utf-8") as token_file:
                    token_file.write(creds.to_json())

        self._service = build("youtube", "v3", credentials=creds)
        return self._service

    @property
    def service(self) -> Resource:
        if self._service is None:
            return self.authenticate()
        return self._service

    def list_subscription_channel_ids(self) -> List[str]:
        """Return the list of channel IDs the user is subscribed to."""

        channel_ids: List[str] = []
        request: Optional[HttpRequest] = self.service.subscriptions().list(
            part="snippet",
            mine=True,
            maxResults=50,
            order="alphabetical",
        )

        while request is not None:
            response = request.execute()
            for item in response.get("items", []):
                snippet = item.get("snippet", {})
                resource_id = snippet.get("resourceId", {})
                channel_id = resource_id.get("channelId")
                if channel_id:
                    channel_ids.append(channel_id)
            request = self.service.subscriptions().list_next(request, response)

        return channel_ids

    def fetch_videos_for_channels(
        self,
        channel_ids: Iterable[str],
        *,
        start_time: datetime,
        end_time: Optional[datetime] = None,
        max_videos_per_channel: Optional[int] = None,
    ) -> List[Video]:
        """Fetch videos for the provided channel IDs within the time window."""

        videos: List[Video] = []
        start_iso = _isoformat(start_time)
        end_iso = _isoformat(end_time) if end_time else None

        for channel_id in channel_ids:
            page_token: Optional[str] = None
            fetched_for_channel = 0
            while True:
                request_kwargs = dict(
                    part="snippet",
                    channelId=channel_id,
                    type="video",
                    order="date",
                    publishedAfter=start_iso,
                    maxResults=50,
                )
                if end_iso:
                    request_kwargs["publishedBefore"] = end_iso
                if page_token:
                    request_kwargs["pageToken"] = page_token

                request = self.service.search().list(**request_kwargs)
                response = request.execute()

                for item in response.get("items", []):
                    snippet = item.get("snippet", {})
                    published_at_str = snippet.get("publishedAt")
                    published_at = _parse_datetime(published_at_str)
                    if published_at is None:
                        continue
                    if published_at < start_time or (end_time and published_at > end_time):
                        continue

                    video = Video(
                        video_id=item.get("id", {}).get("videoId", ""),
                        title=snippet.get("title", ""),
                        description=snippet.get("description", ""),
                        channel_title=snippet.get("channelTitle", ""),
                        published_at=published_at,
                    )
                    if video.video_id:
                        videos.append(video)
                        fetched_for_channel += 1
                        if max_videos_per_channel and fetched_for_channel >= max_videos_per_channel:
                            break

                if max_videos_per_channel and fetched_for_channel >= max_videos_per_channel:
                    break

                page_token = response.get("nextPageToken")
                if not page_token:
                    break

        videos.sort(key=lambda v: v.published_at)
        return videos


def _isoformat(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value).astimezone(timezone.utc)
    except ValueError:
        return None


__all__ = ["Video", "YouTubeClient"]
