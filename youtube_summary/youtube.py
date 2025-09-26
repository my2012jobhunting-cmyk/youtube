"""Command line entry point for the YouTube subscription summariser."""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parent.parent))

from youtube_summary.config import AppConfig, load_config_from_env
from youtube_summary.document import build_markdown_document
from youtube_summary.gemini_client import GeminiSummary, GeminiSummarizer
from youtube_summary.transcript_client import TranscriptFetcher
from youtube_summary.notion_client import NotionResult, NotionUploader
from youtube_summary.youtube_client import Video, YouTubeClient


BEIJING_TZ = ZoneInfo("Asia/Shanghai")
LOG_PREFIX = "[gemini_summary_log]"
logger = logging.getLogger(__name__)


def _log_info(message: str, *args) -> None:
    logger.info("%s " + message, LOG_PREFIX, *args)


def _log_warning(message: str, *args) -> None:
    logger.warning("%s " + message, LOG_PREFIX, *args)


def _log_error(message: str, *args) -> None:
    logger.error("%s " + message, LOG_PREFIX, *args)


def _default_time_bounds(
    now_utc: Optional[datetime] = None,
) -> Tuple[datetime, datetime]:
    """Return default start/end times (UTC)."""

    if now_utc is None:
        now_utc = datetime.now(timezone.utc)
    beijing_now = now_utc.astimezone(BEIJING_TZ)
    default_start_local = (beijing_now - timedelta(days=1)).replace(
        hour=7, minute=0, second=0, microsecond=0
    )
    default_start_utc = default_start_local.astimezone(timezone.utc)
    return default_start_utc, now_utc


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--start",
        help="Start of the time range (ISO 8601). Defaults to previous day 07:00 Asia/Shanghai.",
    )
    parser.add_argument(
        "--end",
        help="End of the time range (ISO 8601). Defaults to current time if omitted.",
    )
    parser.add_argument(
        "--language",
        default="zh-CN",
        help="Language code for the summaries (default: zh-CN).",
    )
    parser.add_argument(
        "--max-per-channel",
        type=int,
        help="Limit the number of videos fetched per channel.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("subscription_summaries.md"),
        help="Path to save the generated Markdown document.",
    )
    parser.add_argument(
        "--title",
        help="Title for the generated document and Notion page. Defaults to today's date (Asia/Shanghai).",
    )
    parser.add_argument(
        "--skip-gemini",
        action="store_true",
        help="Skip calling Gemini and only collect video metadata.",
    )
    parser.add_argument(
        "--skip-notion",
        action="store_true",
        help="Skip uploading the result to Notion.",
    )
    return parser.parse_args(argv)


def _parse_datetime(value: str) -> datetime:
    normalised = value.strip()
    if normalised.endswith("Z"):
        normalised = normalised[:-1] + "+00:00"
    dt = datetime.fromisoformat(normalised)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _summarise_videos(
    videos: Iterable[Video],
    *,
    config: AppConfig,
    language: Optional[str],
    skip_gemini: bool,
    transcript_fetcher: Optional[TranscriptFetcher],
) -> List[GeminiSummary]:
    video_list = list(videos)
    summaries: List[GeminiSummary] = []

    if skip_gemini:
        _log_info("Skipping Gemini summarisation for %d videos.", len(video_list))
        for video in video_list:
            summaries.append(
                GeminiSummary(
                    video=video,
                    summary=(
                        "Gemini summarisation was skipped. Please provide your own notes for this video."
                    ),
                )
            )
        return summaries

    summarizer = GeminiSummarizer(config.gemini)
    for video in video_list:
        transcript: Optional[str] = None
        if transcript_fetcher:
            try:
                _log_info(
                    "Fetching transcript for %s (%s)", video.video_id, video.title
                )
                transcript = transcript_fetcher.fetch(
                    video.video_id, video_url=video.url
                )
                if transcript:
                    _log_info(
                        "Retrieved transcript for %s (chars=%d)",
                        video.video_id,
                        len(transcript),
                    )
                else:
                    _log_warning(
                        "Transcript unavailable for %s", video.video_id
                    )
            except Exception as error:  # pylint: disable=broad-except
                _log_error(
                    "Failed to fetch transcript for %s: %s",
                    video.video_id,
                    error,
                )
        try:
            _log_info("Gemini summary start generated for %s", video.video_id)
            summaries.append(
                summarizer.summarize(
                    video,
                    transcript=transcript,
                    language=language,
                )
            )
            _log_info("Gemini summary end generated for %s", video.video_id)
            time.sleep(3)
        except Exception as error:  # pylint: disable=broad-except
            _log_error("Gemini summary failed for %s: %s", video.video_id, error)
            summaries.append(
                GeminiSummary(
                    video=video,
                    summary=f"Failed to summarise via Gemini: {error}",
                )
            )

    return summaries


def _upload_to_notion(
    config: AppConfig,
    title: str,
    summaries: Iterable[GeminiSummary],
    skip_notion: bool,
) -> Optional[NotionResult]:
    if skip_notion:
        _log_info("Skipping Notion upload by request.")
        return None
    if not config.notion.api_key or not (
        config.notion.database_id or config.notion.parent_page_id
    ):
        _log_warning("Notion configuration incomplete; skipping upload.")
        return None

    uploader = NotionUploader(config.notion)
    result = uploader.upload(title, summaries)
    if result.success:
        _log_info("Notion page created: %s", result.url)
    else:
        _log_error("Notion upload failed: %s", result.error)
    return result


def run_youtube_summary(
    *,
    start: Optional[str] = None,
    end: Optional[str] = None,
    language: Optional[str] = "zh-CN",
    max_per_channel: Optional[int] = None,
    output_path: Path | str = Path("subscription_summaries.md"),
    title: Optional[str] = None,
    skip_gemini: bool = False,
    skip_notion: bool = False,
) -> dict:
    default_start, default_end = _default_time_bounds()
    start_time = _parse_datetime(start) if start else default_start
    end_time = _parse_datetime(end) if end else default_end
    if end_time < start_time:
        raise ValueError("End time must be after start time.")
    resolved_title = title or start_time.astimezone(BEIJING_TZ).strftime("%Y-%m-%d")

    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

    config = load_config_from_env()
    youtube_client = YouTubeClient(config.youtube)

    _log_info("Fetching subscription list…")
    channels = youtube_client.list_subscription_channel_ids()
    _log_info("Found %d subscription channels.", len(channels))
    if channels:
        _log_info("Subscription channels: %s", ", ".join(channels))

    _log_info("Fetching videos within the specified range…")
    videos = youtube_client.fetch_videos_for_channels(
        channels,
        start_time=start_time,
        end_time=end_time,
        max_videos_per_channel=max_per_channel,
    )
    videos = list(videos)
    _log_info("Discovered %d videos within the requested window.", len(videos))
    for video in videos:
        _log_info(
            "Video queued: %s | %s | %s",
            video.video_id,
            video.title,
            video.published_at.isoformat(),
        )

    transcript_fetcher: Optional[TranscriptFetcher] = None
    if not skip_gemini:
        transcript_languages: Optional[List[str]] = None
        if language:
            transcript_languages = [language]
        proxy_config = config.transcript.build_proxy_config()
        if proxy_config:
            _log_info("Using Webshare proxy for transcripts.")
        transcript_fetcher = TranscriptFetcher(
            preferred_languages=transcript_languages,
            proxy_config=proxy_config,
        )

    summaries = _summarise_videos(
        videos,
        config=config,
        language=language,
        skip_gemini=skip_gemini,
        transcript_fetcher=transcript_fetcher,
    )

    document = build_markdown_document(
        resolved_title,
        summaries,
        start_time=start_time,
        end_time=end_time,
    )

    output_file = Path(output_path)
    output_file.write_text(document.body, encoding="utf-8")
    _log_info("Saved Markdown document to %s", output_file.resolve())

    notion_result = _upload_to_notion(
        config,
        resolved_title,
        summaries,
        skip_notion=skip_notion,
    )

    if notion_result and not notion_result.success:
        _log_error("Failed to create Notion page: %s", notion_result.error)

    output_payload = {
        "video_count": len(videos),
        "document_path": str(output_file.resolve()),
        "notion_page_url": notion_result.url if notion_result else None,
    }
    _log_info(
        "Pipeline finished: %d videos processed. Document=%s NotionURL=%s",
        len(videos),
        output_payload["document_path"],
        output_payload["notion_page_url"],
    )
    return output_payload

def cli_main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    payload = run_youtube_summary(
        start=args.start,
        end=args.end,
        language=args.language,
        max_per_channel=args.max_per_channel,
        output_path=args.output,
        title=args.title,
        skip_gemini=args.skip_gemini,
        skip_notion=args.skip_notion,
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(cli_main())
