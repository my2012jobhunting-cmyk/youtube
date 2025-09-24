"""Command line entry point for the YouTube subscription summariser."""
from __future__ import annotations

import argparse
import time
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Iterable, List, Optional

if __package__ in (None, ""):
    sys.path.append(str(Path(__file__).resolve().parent.parent))

from youtube_summary.config import AppConfig, load_config_from_env
from youtube_summary.document import build_markdown_document
from youtube_summary.gemini_client import GeminiSummary, GeminiSummarizer
from youtube_summary.transcript_client import TranscriptFetcher
from youtube_summary.notion_client import NotionResult, NotionUploader
from youtube_summary.youtube_client import Video, YouTubeClient


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", required=True, help="Start of the time range (ISO 8601).")
    parser.add_argument("--end", help="End of the time range (ISO 8601).")
    parser.add_argument(
        "--language",
        help="Optional language code for the summaries (e.g. zh-CN).",
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
        default="YouTube Subscription Summaries",
        help="Title for the generated document and Notion page.",
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
    summaries: List[GeminiSummary] = []

    if skip_gemini:
        for video in videos:
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
    for video in videos:
        transcript: Optional[str] = None
        if transcript_fetcher:
            try:
                transcript = transcript_fetcher.fetch(
                    video.video_id, video_url=video.url
                )
            except Exception as error:  # pylint: disable=broad-except
                print(f"Failed to fetch transcript for {video.video_id}: {error}")
        try:
            summaries.append(
                summarizer.summarize(
                    video,
                    transcript=transcript,
                    language=language,
                )
            )
            time.sleep(3)
        except Exception as error:  # pylint: disable=broad-except
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
        return None
    if not config.notion.api_key or not (
        config.notion.database_id or config.notion.parent_page_id
    ):
        return None

    uploader = NotionUploader(config.notion)
    return uploader.upload(title, summaries)


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    start_time = _parse_datetime(args.start)
    end_time = _parse_datetime(args.end) if args.end else None
    if end_time and end_time < start_time:
        raise ValueError("End time must be after start time.")

    config = load_config_from_env()
    youtube_client = YouTubeClient(config.youtube)

    print("Fetching subscription list…")
    channels = youtube_client.list_subscription_channel_ids()
    print(f"Found {len(channels)} channels.")

    print("Fetching videos within the specified range…")
    videos = youtube_client.fetch_videos_for_channels(
        channels,
        start_time=start_time,
        end_time=end_time,
        max_videos_per_channel=args.max_per_channel,
    )
    print(f"Discovered {len(videos)} videos in the requested window.")

    transcript_fetcher: Optional[TranscriptFetcher] = None
    if not args.skip_gemini:
        transcript_languages: Optional[List[str]] = None
        if args.language:
            transcript_languages = [args.language]
        transcript_fetcher = TranscriptFetcher(preferred_languages=transcript_languages)

    summaries = _summarise_videos(
        videos,
        config=config,
        language=args.language,
        skip_gemini=args.skip_gemini,
        transcript_fetcher=transcript_fetcher,
    )

    document = build_markdown_document(
        args.title,
        summaries,
        start_time=start_time,
        end_time=end_time,
    )
    args.output.write_text(document.body, encoding="utf-8")
    print(f"Saved Markdown document to {args.output.resolve()}")

    notion_result = _upload_to_notion(
        config,
        args.title,
        summaries,
        skip_notion=args.skip_notion,
    )

    if notion_result:
        if notion_result.success:
            print(f"Created Notion page: {notion_result.url}")
        else:
            print(f"Failed to create Notion page: {notion_result.error}")

    # Provide a JSON dump on stdout for automation.
    output_payload = {
        "video_count": len(videos),
        "document_path": str(args.output.resolve()),
        "notion_page_url": notion_result.url if notion_result else None,
    }
    print(json.dumps(output_payload, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
