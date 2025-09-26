"""Interface for sending summarisation requests to Gemini."""
from __future__ import annotations

from dataclasses import dataclass
import logging
import time
from typing import Optional

import google.generativeai as genai

from youtube_summary.config import GeminiConfig
from youtube_summary.youtube_client import Video


LOG_PREFIX = "[gemini_summary_log]"
logger = logging.getLogger(__name__)


def _log_error(message: str, *args) -> None:
    logger.error("%s " + message, LOG_PREFIX, *args)


def _log_info(message: str, *args) -> None:
    logger.info("%s " + message, LOG_PREFIX, *args)


@dataclass
class GeminiSummary:
    video: Video
    summary: str


class GeminiSummarizer:
    """Wrapper around the Gemini API for generating video summaries."""

    def __init__(self, config: GeminiConfig):
        if not config.api_key:
            raise ValueError("A Gemini API key must be provided via GEMINI_API_KEY.")
        self._config = config
        genai.configure(api_key=config.api_key)
        self._model = genai.GenerativeModel(model_name=config.model)

    def summarize(
        self,
        video: Video,
        *,
        transcript: Optional[str] = None,
        language: Optional[str] = None,
    ) -> GeminiSummary:
        """Summarise a single video using Gemini."""

        instructions = (
            "用通俗易懂的语言，按视频内容顺序列出里面的所有观点。"
            "每条观点结尾必须附上可直接跳转的时间戳链接（格式 [83s](https://www.youtube.com/watch?v=...&t=83s)），只保留最开始的一个时间戳。"
            "可直接复用字幕行里已有的 Markdown 链接。全程使用中文回答。"
        )
        prompt = (
            f"{instructions}\n"
            f"视频标题: {video.title}\n"
            f"视频频道: {video.channel_title}\n"
            f"视频link: {video.url}\n"
        )

        if transcript:
            # Gemini models have context limits; keep the transcript excerpt compact.
            excerpt = transcript
            # if len(excerpt) > 15000:
            #     excerpt = f"{excerpt[:15000]}…"
            prompt += (
                "字幕每行格式为 [秒数s](跳转链接) 内容，总结时直接引用该链接。\n"
                f"视频内容:\n{excerpt}"
            )

        request_kwargs = {}
        if self._config.request_timeout:
            request_kwargs["request_options"] = {
                "timeout": self._config.request_timeout
            }

        deadline_tokens = ("504", "Deadline Exceeded")
        attempts = 5
        for attempt in range(attempts):
            try:
                response = self._model.generate_content(prompt, **request_kwargs)
                if attempt > 0:
                    _log_info(
                        "Gemini request succeeded for %s after %d retries.",
                        video.video_id,
                        attempt,
                    )
                break
            except Exception as error:  # pylint: disable=broad-except
                should_retry = any(token in str(error) for token in deadline_tokens)
                if attempt < attempts - 1 and should_retry:
                    _log_error(
                        "Gemini request hit %s on attempt %d for %s; retrying.",
                        error,
                        attempt + 1,
                        video.video_id,
                    )
                    time.sleep(3)
                    continue
                _log_error(
                    "Gemini request failed for %s: %s",
                    video.video_id,
                    error,
                )
                raise
        text = response.text if hasattr(response, "text") else str(response)
        summary = text.strip().replace("\n\n", "\n")
        if not transcript:
            summary += "!!!未获取到字幕!!!"
            

        return GeminiSummary(video=video, summary=summary)


__all__ = ["GeminiSummarizer", "GeminiSummary"]
