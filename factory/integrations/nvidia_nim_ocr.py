"""
AI Factory Pipeline v5.8.12 — NVIDIA NIM OCR Provider

Document OCR using NVIDIA NIM models.
Wired into: S1 Legal (extract text from PDF images), legal document analysis.

Models:
  nvidia/nemotron-ocr-v1       — full-page OCR, table-aware
  nvidia/nemoretriever-ocr-v1  — retrieval-optimized OCR output

Endpoint: https://integrate.api.nvidia.com/v1/chat/completions (vision path)

Required env var:
  NVIDIA_NIM_MULTI_API_KEY — covers both OCR models
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Optional

logger = logging.getLogger("factory.integrations.nvidia_nim_ocr")

NVIDIA_OCR_ENDPOINT = "https://integrate.api.nvidia.com/v1/chat/completions"

_OCR_MODELS = [
    "nvidia/nemotron-ocr-v1",
    "nvidia/nemoretriever-ocr-v1",
]


def _get_api_key() -> str:
    return os.getenv("NVIDIA_NIM_MULTI_API_KEY", "") or os.getenv("NVIDIA_NIM_API_KEY", "")


async def ocr_image(
    image_bytes: bytes,
    model: Optional[str] = None,
    extract_tables: bool = True,
) -> str:
    """Extract text from an image using NVIDIA NIM OCR.

    Args:
        image_bytes: Raw PNG/JPEG/TIFF image bytes.
        model: Model to use (None = nemotron-ocr-v1 first).
        extract_tables: Include structured table extraction if True.

    Returns:
        Extracted text content.
    """
    if os.getenv("AI_PROVIDER", "").lower() == "mock":
        return "[MOCK:ocr] extracted text"

    api_key = _get_api_key()
    if not api_key:
        raise ValueError("NVIDIA_NIM_MULTI_API_KEY not configured — cannot use OCR")

    b64_image = base64.b64encode(image_bytes).decode("utf-8")
    img_type = "jpeg" if image_bytes[:2] == b"\xff\xd8" else "png"

    table_note = " Extract and format any tables as structured text." if extract_tables else ""
    prompt = (
        "Extract all text from this document image accurately. "
        "Preserve the original structure (headers, paragraphs, lists)."
        f"{table_note} Return only the extracted text."
    )

    models_to_try = [model] if model else _OCR_MODELS

    for model_id in models_to_try:
        try:
            result = await _call_ocr(b64_image, img_type, prompt, model_id, api_key)
            return result
        except Exception as e:
            logger.warning(f"[nvidia_nim_ocr] {model_id} failed: {e}")

    raise ValueError("All NVIDIA NIM OCR models failed")


async def _call_ocr(
    b64_image: str,
    img_type: str,
    prompt: str,
    model: str,
    api_key: str,
) -> str:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/{img_type};base64,{b64_image}"},
                    },
                    {"type": "text", "text": prompt},
                ],
            }
        ],
        "max_tokens": 4096,
        "temperature": 0.0,
        "stream": False,
    }

    logger.debug(f"[nvidia_nim_ocr] calling {model}")

    import httpx
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.post(NVIDIA_OCR_ENDPOINT, headers=headers, json=payload)

    if response.status_code == 429:
        raise Exception(f"429 Rate Limited — {model}")
    if response.status_code in (401, 403):
        raise Exception(f"{response.status_code} Unauthorized")
    response.raise_for_status()

    data = response.json()
    return data["choices"][0]["message"]["content"] or ""


async def ocr_pdf_page_image(image_bytes: bytes) -> str:
    """Convenience wrapper for legal document PDF page images."""
    return await ocr_image(image_bytes, extract_tables=True)
