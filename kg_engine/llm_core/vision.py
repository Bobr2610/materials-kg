"""Provider-neutral Vision-Language helpers for document parsing."""

from __future__ import annotations

import base64
from pathlib import Path  # noqa: TC003
from typing import Any

from pydantic import BaseModel
from pydantic import Field


class VisionRequest(BaseModel):
    """Single image/page analysis request for chat-completions VL models."""

    image_path: Path
    prompt: str
    mime_type: str = "image/png"
    metadata: dict[str, Any] = Field(default_factory=dict)


def build_vision_messages(
    request: VisionRequest,
) -> list[dict[str, Any]]:
    """Build a multimodal chat payload for compatible providers."""
    if request.image_path.suffix.lower() == ".pdf":
        msg = "Vision analysis expects a rendered page/image, not a PDF file."
        raise ValueError(msg)
    encoded = base64.b64encode(request.image_path.read_bytes()).decode("ascii")
    data_url = f"data:{request.mime_type};base64,{encoded}"
    return [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": request.prompt},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }
    ]


class VisionConductor:
    """Small conductor that sends one rendered page/image per VL request."""

    def __init__(
        self,
        provider: Any,
        *,
        model: str | None = None,
        max_tokens: int = 1200,
        temperature: float = 0.0,
    ) -> None:
        self.provider = provider
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

    def analyze_image(
        self,
        image_path: Path,
        *,
        prompt: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Analyze exactly one image/page and return a textual interpretation."""
        request = VisionRequest(
            image_path=image_path,
            prompt=prompt,
            metadata=metadata or {},
        )
        messages = build_vision_messages(request)
        return self.provider.chat(
            messages,  # type: ignore[arg-type]
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
