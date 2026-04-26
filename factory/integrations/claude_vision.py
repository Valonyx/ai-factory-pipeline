"""
AI Factory Pipeline v5.8.16 — Claude Vision Integration (G4/G5 closure)

Provides a real VLM call path via the Anthropic SDK for UI screenshot
analysis and design verification. Used as the final fallback in the
UI-parsing chain (G4) and as the mockup reviewer in vibe_check (G5).

Cost budget (declared per audit requirement):
  Model:    claude-haiku-4-5-20251001
  Rate:     $0.80/M input tokens + $4.00/M output tokens
  Per-call: ~$0.001–$0.003 (image ≈800 tok input + ≈200 tok output)
  Latency:  2–5 s

Mode gate: callers are responsible for not invoking this in BASIC mode.
Key gate:  raises ValueError if ANTHROPIC_API_KEY is absent.
"""
from __future__ import annotations

from factory.core.dry_run import is_mock_provider

import base64
import logging
import os

logger = logging.getLogger("factory.integrations.claude_vision")

CLAUDE_VISION_MODEL = "claude-haiku-4-5-20251001"
_COST_INPUT_PER_M:  float = 0.80
_COST_OUTPUT_PER_M: float = 4.00


async def call_claude_vision(
    image_bytes: bytes,
    prompt: str,
    model: str = CLAUDE_VISION_MODEL,
    max_tokens: int = 1024,
) -> tuple[str, float]:
    """Analyze an image with Claude Vision and return (text, cost_usd).

    Args:
        image_bytes: Raw PNG or JPEG bytes.
        prompt:      Analysis instruction.
        model:       Claude model id (default: haiku for cost efficiency).
        max_tokens:  Maximum response length.

    Returns:
        (response_text, cost_usd)

    Raises:
        ValueError: If ANTHROPIC_API_KEY is not set.
        Exception:  On network or API errors (caller should catch).
    """
    if is_mock_provider():
        return (f"[MOCK:claude_vision] {prompt[:60]}", 0.0001)

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not configured — cannot use Claude Vision")

    media_type = "image/jpeg" if image_bytes[:2] == b"\xff\xd8" else "image/png"
    b64_data = base64.b64encode(image_bytes).decode("utf-8")

    import anthropic
    client = anthropic.AsyncAnthropic(api_key=api_key)
    response = await client.messages.create(
        model=model,
        max_tokens=max_tokens,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": media_type,
                        "data": b64_data,
                    },
                },
                {"type": "text", "text": prompt},
            ],
        }],
    )

    text = next((b.text for b in response.content if b.type == "text"), "")
    cost = (
        response.usage.input_tokens / 1_000_000 * _COST_INPUT_PER_M
        + response.usage.output_tokens / 1_000_000 * _COST_OUTPUT_PER_M
    )
    logger.info("[claude_vision] %s: %d chars $%.5f", model, len(text), cost)
    return text, cost


def is_available() -> bool:
    """True when ANTHROPIC_API_KEY is present (or mock mode active)."""
    if is_mock_provider():
        return True
    return bool(os.getenv("ANTHROPIC_API_KEY", ""))
