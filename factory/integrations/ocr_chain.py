"""
AI Factory Pipeline v5.8.16 — OCR Chain

Unified document OCR chain. Tries NVIDIA NIM OCR models in quality order.
Returns typed result — never raises on all-fail.

Provider roster (all free via NVIDIA NIM):
  1. nvidia/nemotron-ocr-v1        — full-page OCR, table-aware, highest accuracy
     Key: NVIDIA_NIM_MULTI_API_KEY
     Endpoint: https://ai.api.nvidia.com/v1/cv/nvidia/nemotron-ocr-v1
  2. nvidia/nemoretriever-ocr-v1   — retrieval-optimised OCR output
     Key: NVIDIA_NIM_MULTI_API_KEY
     Endpoint: https://ai.api.nvidia.com/v1/cv/nvidia/nemoretriever-ocr-v1

Use cases:
  - Legal document text extraction (S1 Legal stage)
  - PDF scan processing (Blueprint stage)
  - Image-to-text for document understanding

Configurable via OCR_PROVIDER_CHAIN env var.

Spec Authority: v5.8.16 §G-ocr
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("factory.integrations.ocr_chain")

_PROVIDER_CHAIN: list[str] = [
    p.strip()
    for p in os.getenv(
        "OCR_PROVIDER_CHAIN",
        "nvidia_nemotron_ocr,nvidia_nemoretriever_ocr",
    ).split(",")
    if p.strip()
]


# ── Public API ───────────────────────────────────────────────────────────────


async def ocr_image(
    image_bytes: bytes,
    extract_tables: bool = True,
    mode: str = "balanced",
) -> dict:
    """Extract text from an image using the OCR provider chain.

    Tries providers in priority order; stops at first success.
    On all-fail: returns typed degraded result (never raises).

    Args:
        image_bytes:    Raw PNG/JPEG/TIFF image bytes.
        extract_tables: Include structured table extraction if True.
        mode:           "basic" | "balanced" | "custom" | "turbo".

    Returns:
        {
          "text":     str   — extracted text content,
          "model":    str   — model used,
          "source":   str   — provider name,
          "degraded": bool  — True only on all-fail,
          "error":    str   — only when degraded=True,
        }
    """
    if os.getenv("AI_PROVIDER", "").lower() == "mock":
        return {
            "text": "[MOCK:ocr] extracted text content",
            "model": "mock",
            "source": "mock",
            "degraded": False,
        }

    if not image_bytes:
        return {"text": "", "model": "", "source": "none", "degraded": False}

    errors: list[str] = []
    for provider in _PROVIDER_CHAIN:
        try:
            text, model = await _call_ocr_provider(provider, image_bytes, extract_tables)
            _track_cost(provider)
            logger.info("[ocr_chain] %s succeeded — %d chars", provider, len(text))
            return {"text": text, "model": model, "source": provider, "degraded": False}
        except Exception as e:
            err = f"{provider}: {e}"
            errors.append(err)
            logger.warning("[ocr_chain] %s", err)

    logger.error("[ocr_chain] All providers failed: %s", "; ".join(errors))
    return {
        "text": "",
        "model": "",
        "source": "degraded",
        "degraded": True,
        "error": "; ".join(errors),
    }


async def ocr_pdf_page(
    page_image_bytes: bytes,
    page_number: int = 1,
) -> dict:
    """OCR a single PDF page (as image bytes).

    Convenience wrapper with page metadata in the result.
    """
    result = await ocr_image(page_image_bytes, extract_tables=True)
    result["page"] = page_number
    return result


# ── Provider dispatch ────────────────────────────────────────────────────────


async def _call_ocr_provider(
    provider: str,
    image_bytes: bytes,
    extract_tables: bool,
) -> tuple[str, str]:
    """Return (extracted_text, model_id) or raise."""
    if provider == "nvidia_nemotron_ocr":
        from factory.integrations.nvidia_nim_ocr import ocr_image as nim_ocr
        text = await nim_ocr(image_bytes, model="nvidia/nemotron-ocr-v1", extract_tables=extract_tables)
        return text, "nvidia/nemotron-ocr-v1"

    if provider == "nvidia_nemoretriever_ocr":
        from factory.integrations.nvidia_nim_ocr import ocr_image as nim_ocr
        text = await nim_ocr(image_bytes, model="nvidia/nemoretriever-ocr-v1", extract_tables=extract_tables)
        return text, "nvidia/nemoretriever-ocr-v1"

    raise ValueError(f"Unknown OCR provider: {provider}")


# ── Cost tracking ────────────────────────────────────────────────────────────

_PROVIDER_COST: dict[str, float] = {
    "nvidia_nemotron_ocr":      0.0,
    "nvidia_nemoretriever_ocr": 0.0,
}


def _track_cost(provider: str) -> None:
    try:
        from factory.core.quota_tracker import get_quota_tracker
        import asyncio
        qt = get_quota_tracker()
        asyncio.create_task(
            qt.record_usage(provider, tokens=0, calls=1,
                            cost_usd=_PROVIDER_COST.get(provider, 0.0))
        )
    except Exception:
        pass
