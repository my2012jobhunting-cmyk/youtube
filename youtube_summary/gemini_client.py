"""Interface for sending summarisation requests to Gemini."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import google.generativeai as genai

from .config import GeminiConfig
from .youtube_client import Video


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

    def summarize(self, video: Video, *, language: Optional[str] = None) -> GeminiSummary:
        """Summarise a single video using Gemini."""

        instructions = (
            "You are a helpful assistant that summarises YouTube videos for busy viewers."
            " Provide a concise summary highlighting the key points, action items,"
            " and notable quotes if relevant. Assume you cannot watch the video and"
            " must rely on the title, description and general world knowledge."
        )
        prompt = (
            f"{instructions}\n\n"
            f"Video title: {video.title}\n"
            f"Channel: {video.channel_title}\n"
            f"Published at: {video.published_at.isoformat()}\n"
            f"Description: {video.description or 'No description provided.'}\n"
            f"Link: {video.url}\n\n"
            "Summarise the video in 3-5 bullet points."
        )
        if language:
            prompt += f" Provide the response in {language}."

        response = self._model.generate_content(prompt)
        text = response.text if hasattr(response, "text") else str(response)
        summary = text.strip()

        return GeminiSummary(video=video, summary=summary)


__all__ = ["GeminiSummarizer", "GeminiSummary"]
