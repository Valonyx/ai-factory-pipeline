"""
AI Factory Pipeline v5.8.12 — OmniParser v2 Integration

OmniParser converts UI screenshots into structured element maps that LLMs can
reason about. Developed by Microsoft Research.

GitHub: https://github.com/microsoft/OmniParser/tree/master

Setup (local, one-time):
  1. git clone https://github.com/microsoft/OmniParser
  2. cd OmniParser && pip install -r requirements.txt
  3. Download model weights from HuggingFace:
     huggingface-cli download microsoft/OmniParser-v2.0 --local-dir weights/
  4. Set OMNIPARSER_WEIGHTS_DIR=/path/to/weights in .env
  5. Set OMNIPARSER_ENABLED=true in .env

Optional env vars:
  OMNIPARSER_ENABLED     — "true" to enable (default: false, local model required)
  OMNIPARSER_WEIGHTS_DIR — path to downloaded model weights
  OMNIPARSER_ENDPOINT    — HTTP endpoint if running as a server (alternative to local)

When not available, falls back to NVIDIA NIM vision models for basic UI analysis.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

logger = logging.getLogger("factory.integrations.omniparser")


def is_available() -> bool:
    """Check if OmniParser is configured and ready."""
    if os.getenv("OMNIPARSER_ENABLED", "").lower() not in ("true", "1", "yes"):
        return False
    endpoint = os.getenv("OMNIPARSER_ENDPOINT", "")
    if endpoint:
        return True
    weights_dir = os.getenv("OMNIPARSER_WEIGHTS_DIR", "")
    if not weights_dir or not os.path.isdir(weights_dir):
        return False
    try:
        import torch  # noqa: F401
        return True
    except ImportError:
        return False


async def parse_screenshot(
    image_bytes: bytes,
    task_description: str = "identify all interactive UI elements",
    mode: str = "balanced",
) -> dict:
    """Parse a UI screenshot into structured element data.

    Args:
        image_bytes: Raw PNG/JPEG screenshot bytes.
        task_description: What the agent is trying to do.
        mode: Master execution mode ("basic"|"balanced"|"custom"|"turbo").
              BASIC mode skips paid Claude Vision fallback.

    Returns:
        Dict with:
          - "elements": list of UI element dicts (label, bbox, type, text)
          - "structured_text": flat text representation of the UI
          - "source": "omniparser" | "nim_vision_fallback" |
                      "claude_vision_fallback" | "degraded" | "mock"
          - "degraded": True only when all real providers failed

    Falls back through NIM vision → Claude Vision. Returns a typed
    degraded result (never fakes success) when all options are exhausted.
    """
    if os.getenv("AI_PROVIDER", "").lower() == "mock":
        return {
            "elements": [{"label": "button", "text": "Submit", "bbox": [0, 0, 100, 40], "type": "button"}],
            "structured_text": "Button: Submit",
            "source": "mock",
        }

    if is_available():
        try:
            return await _parse_with_omniparser(image_bytes, task_description)
        except Exception as e:
            logger.warning(f"[omniparser] OmniParser failed ({e}), falling back to vision chain")

    return await _parse_with_vision_fallback(image_bytes, task_description, mode)


async def _parse_with_omniparser(image_bytes: bytes, task: str) -> dict:
    """Call OmniParser via HTTP endpoint or local model."""
    endpoint = os.getenv("OMNIPARSER_ENDPOINT", "")
    if endpoint:
        import httpx
        async with httpx.AsyncClient(timeout=60) as client:
            import base64
            b64 = base64.b64encode(image_bytes).decode()
            response = await client.post(
                f"{endpoint.rstrip('/')}/parse",
                json={"image_base64": b64, "task": task},
            )
            response.raise_for_status()
            return response.json()

    # ── Local model path (OmniParser v2 API: util/omniparser.py) ──────
    import sys, base64, io

    # Locate vendor clone or OMNIPARSER_DIR override
    _script_dir = os.path.dirname(os.path.abspath(__file__))
    _project_root = os.path.dirname(os.path.dirname(_script_dir))
    _vendor_default = os.path.join(_project_root, "vendor", "omniparser")
    omniparser_root = os.getenv("OMNIPARSER_DIR", _vendor_default)
    weights_dir = os.getenv(
        "OMNIPARSER_WEIGHTS_DIR",
        os.path.join(omniparser_root, "weights"),
    )

    if omniparser_root and omniparser_root not in sys.path:
        sys.path.insert(0, omniparser_root)

    # OmniParser v2: use Omniparser class from util/omniparser.py
    try:
        from util.omniparser import Omniparser as OmniparserV2
        config = {
            "som_model_path": os.path.join(weights_dir, "icon_detect", "model.pt"),
            "caption_model_name": "florence2",
            "caption_model_path": os.path.join(weights_dir, "icon_caption_florence"),
            "BOX_TRESHOLD": 0.05,
        }
        parser = OmniparserV2(config)
        b64_img = base64.b64encode(image_bytes).decode("utf-8")
        _annotated_b64, parsed_content_list = parser.parse(b64_img)

        elements = []
        for i, item in enumerate(parsed_content_list):
            elements.append({
                "label": item.get("label", f"element_{i}"),
                "text": item.get("content", item.get("text", "")),
                "bbox": item.get("bbox", [0, 0, 0, 0]),
                "type": item.get("type", "unknown"),
            })

        structured = "\n".join(
            f"{e['type'].title()}: {e['text'] or e['label']}"
            for e in elements
        )
        return {"elements": elements, "structured_text": structured, "source": "omniparser_v2"}

    except ImportError:
        # v2 not available — try legacy v1 API (util/utils.py)
        from PIL import Image as _Image
        image = _Image.open(io.BytesIO(image_bytes))
        model_path = os.path.join(weights_dir, "icon_detect")
        caption_model_path = os.path.join(weights_dir, "icon_caption_florence")
        from utils import get_som_labeled_img, get_caption_model_processor, get_yolo_model
        yolo_model = get_yolo_model(model_path)
        caption_processor, caption_model = get_caption_model_processor(caption_model_path)
        dino_labeled_img, label_coordinates, parsed_content = get_som_labeled_img(
            image, yolo_model, BOX_TRESHOLD=0.03, output_coord_in_ratio=True,
            ocr_bbox=None, draw_bbox_config={},
            caption_model_processor=(caption_processor, caption_model),
            ocr_text=[], use_local_semantics=True, iou_threshold=0.1,
        )
        elements = [
            {
                "label": item.get("label", f"element_{i}"),
                "text": item.get("text", ""),
                "bbox": label_coordinates.get(str(i), [0, 0, 0, 0]),
                "type": item.get("type", "unknown"),
            }
            for i, item in enumerate(parsed_content)
        ]
        structured = "\n".join(
            f"{e['type'].title()}: {e['text'] or e['label']}" for e in elements
        )
        return {"elements": elements, "structured_text": structured, "source": "omniparser_v1"}


async def _parse_with_vision_fallback(image_bytes: bytes, task: str, mode: str) -> dict:
    """Fallback vision chain: NIM → Claude Vision → typed degraded result.

    Tries NIM vision first (free-tier eligible), then Claude Vision when
    the key is present and mode is not 'basic'. Never returns fake success:
    if all providers fail the result carries degraded=True so callers can
    surface the gap instead of silently proceeding with empty data.
    """
    # ── Tier 1: NIM vision (free when NVIDIA_NIM_VISION_API_KEY is set) ──
    nim_error: str = ""
    try:
        from factory.integrations.nvidia_nim_vision import analyze_ui_screenshot
        description = await analyze_ui_screenshot(image_bytes)
        return {
            "elements": [],
            "structured_text": description,
            "source": "nim_vision_fallback",
        }
    except Exception as e:
        nim_error = str(e)
        logger.warning(f"[omniparser] NIM vision failed: {e}")

    # ── Tier 2: Claude Vision (paid — skip in BASIC mode) ──
    if mode.lower() == "basic":
        logger.info("[omniparser] BASIC mode — skipping paid Claude Vision fallback")
        return {
            "elements": [],
            "structured_text": "",
            "source": "degraded",
            "degraded": True,
            "error": f"NIM vision failed ({nim_error}); Claude Vision skipped in BASIC mode",
        }

    try:
        from factory.integrations.claude_vision import call_claude_vision
        prompt = (
            f"Task: {task}\n\n"
            "Analyze this UI screenshot. Identify all interactive elements "
            "(buttons, inputs, links, icons) and describe the layout. "
            "Return a plain-text structured list: one element per line, "
            "format: <type>: <text or description>"
        )
        description, _cost = await call_claude_vision(image_bytes, prompt)
        return {
            "elements": [],
            "structured_text": description,
            "source": "claude_vision_fallback",
        }
    except ValueError as e:
        # Key missing — degraded, not a halt
        logger.warning(f"[omniparser] Claude Vision skipped: {e}")
        return {
            "elements": [],
            "structured_text": "",
            "source": "degraded",
            "degraded": True,
            "error": f"NIM vision failed ({nim_error}); {e}",
        }
    except Exception as e:
        logger.warning(f"[omniparser] Claude Vision also failed: {e}")
        return {
            "elements": [],
            "structured_text": "",
            "source": "degraded",
            "degraded": True,
            "error": f"NIM vision: {nim_error}; Claude Vision: {e}",
        }
