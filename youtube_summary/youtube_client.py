"""Utilities for interacting with the YouTube Data API."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Dict, Iterable, List, Optional, Sequence

from googleapiclient.discovery import Resource, build
from googleapiclient.http import HttpRequest
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from youtube_summary.config import YouTubeConfig


@dataclass
class Video:
    """Representation of a YouTube video."""

    video_id: str
    title: str
    description: str
    channel_title: str
    published_at: datetime
    duration_seconds: Optional[int] = None

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
        playlist_map = self._map_upload_playlists(list(channel_ids))
        candidate_ids: List[str] = []
        metadata: Dict[str, Dict[str, object]] = {}

        for channel_id, playlist_id in playlist_map.items():
            if not playlist_id:
                continue

            page_token: Optional[str] = None
            fetched_for_channel = 0

            while True:
                request_kwargs = {
                    "part": "contentDetails,snippet",
                    "playlistId": playlist_id,
                    "maxResults": 10,
                }
                if page_token:
                    request_kwargs["pageToken"] = page_token

                response = self.service.playlistItems().list(**request_kwargs).execute()
                items = response.get("items", [])
                if not items:
                    break

                stop_paging = False
                for item in items:
                    snippet = item.get("snippet", {})
                    content_details = item.get("contentDetails", {})
                    video_id = content_details.get("videoId")
                    if not video_id:
                        continue

                    published_at_value = (
                        content_details.get("videoPublishedAt")
                        or snippet.get("publishedAt")
                    )
                    published_at = _parse_datetime(published_at_value)
                    if published_at is None:
                        continue
                    if end_time and published_at > end_time:
                        continue
                    if published_at < start_time:
                        stop_paging = True
                        break

                    candidate_ids.append(video_id)
                    metadata[video_id] = {
                        "published_at": published_at,
                        "playlist_snippet": snippet,
                    }
                    fetched_for_channel += 1
                    if max_videos_per_channel and fetched_for_channel >= max_videos_per_channel:
                        stop_paging = True
                        break

                if stop_paging:
                    break

                page_token = response.get("nextPageToken")
                if not page_token:
                    break

        unique_ids = list(dict.fromkeys(candidate_ids))
        details_map = self._fetch_video_details(unique_ids)

        for video_id in unique_ids:
            info = metadata.get(video_id)
            details = details_map.get(video_id)
            if not info or not details:
                continue

            snippet = details.get("snippet", {}) or info["playlist_snippet"]
            content_details = details.get("contentDetails", {})
            duration_seconds = _parse_duration_seconds(content_details.get("duration"))
            if _is_probable_short(snippet, duration_seconds):
                continue

            title = snippet.get("title") or info["playlist_snippet"].get("title", "")
            description = (
                snippet.get("description")
                or info["playlist_snippet"].get("description", "")
            )
            channel_title = (
                snippet.get("channelTitle")
                or snippet.get("videoOwnerChannelTitle")
                or info["playlist_snippet"].get("channelTitle", "")
            )
            published_at = (
                _parse_datetime(snippet.get("publishedAt"))
                or info["published_at"]
            )

            videos.append(
                Video(
                    video_id=video_id,
                    title=title,
                    description=description,
                    channel_title=channel_title,
                    published_at=published_at,
                    duration_seconds=duration_seconds,
                )
            )

        videos.sort(key=lambda v: v.published_at, reverse=True)
        return videos

    def _map_upload_playlists(self, channel_ids: Sequence[str]) -> Dict[str, str]:
        """Return mapping of channel IDs to their uploads playlist."""

        playlist_map: Dict[str, str] = {}
        ids = list(channel_ids)
        if not ids:
            return playlist_map

        for index in range(0, len(ids), 50):
            batch = ids[index : index + 50]
            response = (
                self.service.channels()
                .list(part="contentDetails", id=",".join(batch))
                .execute()
            )
            for item in response.get("items", []):
                channel_id = item.get("id")
                uploads = (
                    item.get("contentDetails", {})
                    .get("relatedPlaylists", {})
                    .get("uploads")
                )
                if channel_id and uploads:
                    playlist_map[channel_id] = uploads
        return playlist_map

    def _fetch_video_details(self, video_ids: Sequence[str]) -> Dict[str, Dict[str, object]]:
        """Retrieve supplemental metadata for the given video IDs."""

        if not video_ids:
            return {}
        details: Dict[str, Dict[str, object]] = {}
        # The videos.list endpoint accepts up to 50 IDs per request.
        for index in range(0, len(video_ids), 50):
            batch = video_ids[index : index + 50]
            response = (
                self.service.videos()
                .list(part="contentDetails,snippet", id=",".join(batch))
                .execute()
            )
            for item in response.get("items", []):
                video_id = item.get("id")
                if not video_id:
                    continue
                details[video_id] = {
                    "contentDetails": item.get("contentDetails", {}),
                    "snippet": item.get("snippet", {}),
                }
        return details


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value).astimezone(timezone.utc)
    except ValueError:
        return None


_ISO_8601_DURATION = re.compile(
    r"P(?:(?P<days>\d+)D)?(?:T(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?)?"
)


def _parse_duration_seconds(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    match = _ISO_8601_DURATION.fullmatch(value)
    if not match:
        return None
    days = int(match.group("days") or 0)
    hours = int(match.group("hours") or 0)
    minutes = int(match.group("minutes") or 0)
    seconds = int(match.group("seconds") or 0)
    total_seconds = (((days * 24) + hours) * 60 + minutes) * 60 + seconds
    return total_seconds


def _is_probable_short(snippet: Dict[str, object], duration_seconds: Optional[int]) -> bool:
    """Best-effort heuristic to filter out YouTube Shorts style videos."""

    if duration_seconds is not None and duration_seconds <= 480:
        return True
    text_fragments = [
        str(snippet.get("title", "")),
        str(snippet.get("description", "")),
    ]
    lowered = " ".join(fragment.lower() for fragment in text_fragments)
    if "#short" in lowered:
        return True
    if str(snippet.get("liveBroadcastContent", "")).lower() == "shorts":
        return True
    return False


__all__ = ["Video", "YouTubeClient"]
