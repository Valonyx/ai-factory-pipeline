"""
AI Factory Pipeline v5.6 — Screen Parser (OmniParser V2 + Free Fallback)

Parses screenshots to detect UI elements for automated GUI builds.

Provider cascade:
  1. OmniParser V2 (Microsoft) — best accuracy, requires GPU download (~500MB)
     Set: OMNIPARSER_ENABLED=true, model downloads automatically
  2. pytesseract + OpenCV (free, no GPU) — OCR-based text element detection
     Requires: pip install pytesseract opencv-python + Tesseract binary
  3. Coordinates-only mode — returns fixed coordinates for known UI patterns
     No dependencies, always works (reduced accuracy)

Force provider: SCREEN_PARSER_PROVIDER=omniparser|tesseract|coordinates

Spec Authority: v5.6 §2.4.2 (NB4 Part 6)
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("factory.automation.omniparser")


@dataclass
class UIElement:
    label: str
    element_type: str       # button | text_field | label | icon | checkbox | tab
    x: int                  # center X pixel coordinate
    y: int                  # center Y pixel coordinate
    width: int = 0
    height: int = 0
    confidence: float = 1.0
    text_content: str = ""

    @property
    def center(self) -> tuple[int, int]:
        return (self.x, self.y)

    @property
    def bounds(self) -> tuple[int, int, int, int]:
        """(left, top, right, bottom)"""
        hw, hh = self.width // 2, self.height // 2
        return (self.x - hw, self.y - hh, self.x + hw, self.y + hh)


class ScreenParser:
    """Parse UI elements from screenshots using best available provider."""

    def __init__(self) -> None:
        self._provider = os.getenv("SCREEN_PARSER_PROVIDER", "auto").lower()
        self._omniparser_model = None

    async def detect_elements(self, screenshot_path: str) -> list[UIElement]:
        """Detect UI elements in a screenshot.

        Returns list of UIElement with coordinates.
        """
        provider = self._provider if self._provider != "auto" else await self._detect_best_provider()

        if provider == "omniparser":
            return await self._parse_with_omniparser(screenshot_path)
        if provider == "tesseract":
            return await self._parse_with_tesseract(screenshot_path)
        return self._parse_with_coordinates(screenshot_path)

    async def _detect_best_provider(self) -> str:
        """Auto-detect the best available provider."""
        if os.getenv("OMNIPARSER_ENABLED", "false").lower() == "true":
            try:
                import torch
                return "omniparser"
            except ImportError:
                pass
        try:
            import pytesseract
            import cv2
            return "tesseract"
        except ImportError:
            pass
        return "coordinates"

    # ── OmniParser V2 ────────────────────────────────────────────────

    async def _parse_with_omniparser(self, screenshot_path: str) -> list[UIElement]:
        """Use OmniParser V2 (Microsoft) for accurate element detection."""
        try:
            from PIL import Image
            import torch

            if self._omniparser_model is None:
                from transformers import AutoModelForObjectDetection, AutoProcessor
                model_name = os.getenv("OMNIPARSER_MODEL", "microsoft/OmniParser-v2")
                logger.info(f"[omniparser] Loading model: {model_name}")
                self._omniparser_model = {
                    "processor": AutoProcessor.from_pretrained(model_name),
                    "model": AutoModelForObjectDetection.from_pretrained(model_name),
                }
                logger.info("[omniparser] Model loaded")

            image = Image.open(screenshot_path).convert("RGB")
            processor = self._omniparser_model["processor"]
            model     = self._omniparser_model["model"]

            inputs = processor(images=image, return_tensors="pt")
            with torch.no_grad():
                outputs = model(**inputs)

            target_sizes = torch.tensor([image.size[::-1]])
            results = processor.post_process_object_detection(
                outputs, threshold=0.7, target_sizes=target_sizes,
            )[0]

            elements: list[UIElement] = []
            for score, label_id, box in zip(
                results["scores"], results["labels"], results["boxes"]
            ):
                x1, y1, x2, y2 = box.tolist()
                cx = int((x1 + x2) / 2)
                cy = int((y1 + y2) / 2)
                label_name = model.config.id2label.get(label_id.item(), "element")
                elements.append(UIElement(
                    label=label_name,
                    element_type=_classify_element_type(label_name),
                    x=cx, y=cy,
                    width=int(x2 - x1), height=int(y2 - y1),
                    confidence=float(score),
                ))
            logger.info(f"[omniparser] Detected {len(elements)} elements")
            return elements

        except Exception as e:
            logger.warning(f"[omniparser] Failed: {e} — falling back to tesseract")
            return await self._parse_with_tesseract(screenshot_path)

    # ── Tesseract + OpenCV (free) ────────────────────────────────────

    async def _parse_with_tesseract(self, screenshot_path: str) -> list[UIElement]:
        """Use pytesseract + OpenCV for text and region detection."""
        try:
            import cv2
            import pytesseract
            import numpy as np

            image = cv2.imread(screenshot_path)
            if image is None:
                return []

            h, w = image.shape[:2]
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

            # Get text regions with bounding boxes
            data = pytesseract.image_to_data(
                gray, output_type=pytesseract.Output.DICT, lang="eng+ara",
            )

            elements: list[UIElement] = []
            for i, text in enumerate(data["text"]):
                text = text.strip()
                if not text or int(data["conf"][i]) < 30:
                    continue
                cx = data["left"][i] + data["width"][i] // 2
                cy = data["top"][i] + data["height"][i] // 2
                elements.append(UIElement(
                    label=text[:50],
                    element_type=_classify_text_element(text),
                    x=cx, y=cy,
                    width=data["width"][i],
                    height=data["height"][i],
                    confidence=float(data["conf"][i]) / 100,
                    text_content=text,
                ))

            # Detect rectangular regions (likely buttons)
            edges = cv2.Canny(gray, 50, 150)
            contours, _ = cv2.findContours(
                edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE,
            )
            for cnt in contours:
                x, y, rw, rh = cv2.boundingRect(cnt)
                if rw < 30 or rh < 15 or rw > w * 0.8:
                    continue
                aspect = rw / rh
                if 1.5 < aspect < 6:   # button-like aspect ratio
                    elements.append(UIElement(
                        label="button_region",
                        element_type="button",
                        x=x + rw // 2, y=y + rh // 2,
                        width=rw, height=rh,
                        confidence=0.6,
                    ))

            logger.info(f"[tesseract] Detected {len(elements)} elements")
            return elements

        except Exception as e:
            logger.warning(f"[tesseract] Failed: {e} — using coordinate fallback")
            return self._parse_with_coordinates(screenshot_path)

    # ── Coordinates-only fallback ─────────────────────────────────────

    def _parse_with_coordinates(self, screenshot_path: str) -> list[UIElement]:
        """Return best-guess coordinates for common UI patterns.

        Used when no vision library is available.
        Assumes standard macOS/iOS app layout.
        """
        logger.info("[screen-parser] Using coordinate-only mode")
        # Standard UI positions for a typical Mac app (1440x900 reference)
        return [
            UIElement("Menu Bar",     "label",      720, 22,  1440, 22),
            UIElement("Main Toolbar", "label",      720, 60,  1440, 40),
            UIElement("Content Area", "label",      720, 450, 1440, 700),
            UIElement("Save Button",  "button",     100, 60,  80,  30),
            UIElement("Build Button", "button",     200, 60,  80,  30),
        ]


# ── Helpers ──────────────────────────────────────────────────────────

def _classify_element_type(label: str) -> str:
    label = label.lower()
    if any(kw in label for kw in ["button", "btn", "click"]):
        return "button"
    if any(kw in label for kw in ["input", "field", "text box", "entry"]):
        return "text_field"
    if any(kw in label for kw in ["checkbox", "check", "radio"]):
        return "checkbox"
    if any(kw in label for kw in ["tab", "menu"]):
        return "tab"
    if any(kw in label for kw in ["icon", "image", "img"]):
        return "icon"
    return "label"


def _classify_text_element(text: str) -> str:
    low = text.lower()
    if any(kw in low for kw in ["save", "build", "run", "export", "upload", "ok", "cancel", "confirm", "submit"]):
        return "button"
    if len(text) < 3 and text.isupper():
        return "icon"
    return "label"
