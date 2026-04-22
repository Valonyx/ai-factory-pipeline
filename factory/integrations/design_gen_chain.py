"""
AI Factory Pipeline v5.8.16 — Design Generation Chain (Figma-AI-like, 4 Free Providers)

Generates UI/UX design assets and prototypes programmatically:
  - Screen mockup images  (PNG from diffusion models)
  - UI component code     (Flutter / React / Tailwind via LLM)
  - SVG icon assets       (generated code, vector-ready)
  - Interactive HTML prototypes
  - Design token JSON     (colors, typography, spacing)

Provider roster (all free-tier):
  1. Google Gemini — code & spec generation (component code, SVG, tokens, prototypes)
     Key: GEMINI_API_KEY
     Register: https://aistudio.google.com
     — Best at structured code output; handles all non-image asset types.

  2. Pollinations.ai — screen mockup images (COMPLETELY FREE, no key)
     Website: https://pollinations.ai
     — Zero configuration. Uses FLUX for high-quality UI mockup images.

  3. HuggingFace FLUX.1-schnell — higher-quality design images
     Key: HUGGINGFACE_API_KEY
     Register: https://huggingface.co/settings/tokens (free account)
     — Black Forest Labs FLUX model, 4-step inference, excellent for UI.

  4. Together AI FLUX.1-schnell-Free — fast diffusion, UI & icon images
     Key: TOGETHER_API_KEY
     Register: https://api.together.xyz (free tier available)
     — Parallel image generation, good for batch asset creation.

Asset type routing:
  "mockup_image"     → Pollinations → HuggingFace → Together
  "component_code"   → Gemini → (OpenRouter free LLMs fallback)
  "svg_icon"         → Gemini → (OpenRouter free LLMs fallback)
  "html_prototype"   → Gemini
  "design_tokens"    → Gemini
  "splash_image"     → Pollinations → HuggingFace → Together

Spec Authority: v5.8.16 §G5-design (Figma-AI-like chain)
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

logger = logging.getLogger("factory.integrations.design_gen_chain")

# ── Asset types ──────────────────────────────────────────────────────────────

ASSET_TYPES = frozenset({
    "mockup_image",    # PNG screen mockup
    "splash_image",    # PNG splash / hero illustration
    "component_code",  # Flutter / React component source
    "svg_icon",        # SVG icon markup
    "html_prototype",  # Interactive HTML/CSS/JS prototype
    "design_tokens",   # JSON design tokens
})


# ── Public API ───────────────────────────────────────────────────────────────


async def generate_design_asset(
    asset_type: str,
    prompt: str,
    design_spec: Optional[dict] = None,
    app_name: str = "",
    width: int = 390,
    height: int = 844,
    mode: str = "balanced",
) -> dict:
    """Generate a UI/UX design asset using the free provider chain.

    Args:
        asset_type:  One of ASSET_TYPES.
        prompt:      Natural-language description of what to generate.
        design_spec: Design DNA dict (color_palette, typography, etc.)
                     used to steer generation.
        app_name:    App name for context.
        width:       Output width in px (for image assets).
        height:      Output height in px (for image assets).
        mode:        MasterMode name — all providers are free so mode
                     affects quality selection, not provider eligibility.

    Returns:
        {
          "asset_type": str,
          "content":    bytes (images) | str (code/SVG/JSON/HTML),
          "format":     "png" | "svg" | "flutter" | "react" | "html" | "json",
          "source":     provider name,
          "degraded":   True only when all providers failed,
          "error":      error summary (only when degraded),
        }
    """
    if os.getenv("AI_PROVIDER", "").lower() == "mock":
        is_image = asset_type in ("mockup_image", "splash_image")
        return {
            "asset_type": asset_type,
            "content": b"MOCKPNG" if is_image else f"/* MOCK {asset_type} */",
            "format": "png" if is_image else "text",
            "source": "mock",
            "degraded": False,
        }

    if asset_type not in ASSET_TYPES:
        return {
            "asset_type": asset_type,
            "content": "",
            "format": "unknown",
            "source": "degraded",
            "degraded": True,
            "error": f"Unknown asset_type '{asset_type}'. Valid: {sorted(ASSET_TYPES)}",
        }

    # Route to the right provider chain
    if asset_type in ("mockup_image", "splash_image"):
        return await _generate_image_asset(
            asset_type, prompt, design_spec, app_name, width, height
        )
    else:
        return await _generate_code_asset(
            asset_type, prompt, design_spec, app_name
        )


async def generate_screen_mockup(
    app_name: str,
    screen_name: str,
    design_spec: dict,
    width: int = 390,
    height: int = 844,
) -> dict:
    """Convenience wrapper: generate a specific app screen mockup."""
    palette = design_spec.get("color_palette", {})
    style = design_spec.get("visual_style", "minimal")
    patterns = design_spec.get("layout_patterns", [])

    prompt = (
        f"Mobile app screen for '{app_name}', screen: {screen_name}. "
        f"Style: {style}, {', '.join(patterns)}. "
        f"Primary color: {palette.get('primary', '#6366f1')}. "
        f"Clean, professional mobile UI, white/light background, "
        f"no real text content, placeholder elements, high detail."
    )
    return await generate_design_asset(
        "mockup_image", prompt, design_spec, app_name, width, height
    )


async def generate_component_code(
    component_name: str,
    description: str,
    design_spec: dict,
    framework: str = "flutter",
) -> dict:
    """Generate a UI component in Flutter or React."""
    palette = design_spec.get("color_palette", {})
    typ = design_spec.get("typography", {})

    prompt = (
        f"Generate a complete {framework} UI component named {component_name}.\n"
        f"Description: {description}\n"
        f"Design system:\n"
        f"  Primary color: {palette.get('primary', '#6366f1')}\n"
        f"  Background: {palette.get('background', '#FFFFFF')}\n"
        f"  Heading font: {typ.get('heading_font', 'Inter')}\n"
        f"  Body font: {typ.get('body_font', 'Inter')}\n"
        f"Requirements: production-ready, WCAG AA contrast, responsive/adaptive, "
        f"no external dependencies beyond the framework's standard library.\n"
        f"Output ONLY the component code, no explanations."
    )
    return await generate_design_asset(
        "component_code", prompt, design_spec, component_name
    )


async def generate_icon_set(
    icon_names: list[str],
    style: str = "outline",
    primary_color: str = "#6366f1",
) -> list[dict]:
    """Generate a set of SVG icons."""
    results: list[dict] = []
    for name in icon_names:
        prompt = (
            f"Create a clean {style} SVG icon for '{name}'. "
            f"Color: {primary_color}. 24×24 viewBox. No fills other than the stroke "
            f"or specified color. Minimal, professional, geometric. "
            f"Output ONLY the complete SVG markup."
        )
        result = await generate_design_asset("svg_icon", prompt)
        result["icon_name"] = name
        results.append(result)
    return results


# ── Image asset generation (mockup_image, splash_image) ─────────────────────


async def _generate_image_asset(
    asset_type: str,
    prompt: str,
    design_spec: Optional[dict],
    app_name: str,
    width: int,
    height: int,
) -> dict:
    """Try image providers in quality order."""
    enhanced = _enhance_image_prompt(prompt, design_spec, asset_type)
    errors: list[str] = []

    # Provider 1: HuggingFace FLUX.1-schnell (highest quality)
    hf_key = os.getenv("HUGGINGFACE_API_KEY", "")
    if hf_key:
        try:
            from factory.integrations.image_gen import _call_huggingface
            data = await _call_huggingface(enhanced, width, height)
            if data:
                logger.info("[design_gen] huggingface succeeded (%d bytes)", len(data))
                _track_cost("huggingface", 0.0)
                return _image_result(asset_type, data, "huggingface")
        except Exception as e:
            errors.append(f"huggingface: {e}")
            logger.warning("[design_gen] huggingface: %s", e)

    # Provider 2: Together AI FLUX.1-schnell-Free
    together_key = os.getenv("TOGETHER_API_KEY", "")
    if together_key:
        try:
            from factory.integrations.image_gen import _call_together_image
            data = await _call_together_image(enhanced, width, height)
            if data:
                logger.info("[design_gen] together succeeded (%d bytes)", len(data))
                _track_cost("together", 0.0)
                return _image_result(asset_type, data, "together")
        except Exception as e:
            errors.append(f"together: {e}")
            logger.warning("[design_gen] together: %s", e)

    # Provider 3: Pollinations.ai (zero config, always available)
    import time as _time
    try:
        from factory.integrations.image_gen import _call_pollinations
        seed = int(_time.time()) % 999_999
        data = await _call_pollinations(enhanced, width, height, seed)
        if data:
            logger.info("[design_gen] pollinations succeeded (%d bytes)", len(data))
            _track_cost("pollinations", 0.0)
            return _image_result(asset_type, data, "pollinations")
    except Exception as e:
        errors.append(f"pollinations: {e}")
        logger.warning("[design_gen] pollinations: %s", e)

    return {
        "asset_type": asset_type,
        "content": b"",
        "format": "png",
        "source": "degraded",
        "degraded": True,
        "error": "; ".join(errors),
    }


def _enhance_image_prompt(prompt: str, design_spec: Optional[dict], asset_type: str) -> str:
    """Add design-system context and quality modifiers to the image prompt."""
    quality = (
        "high quality, professional UI design, clean, modern, "
        "8K resolution, detailed, sharp, photorealistic render"
    )
    if design_spec:
        palette = design_spec.get("color_palette", {})
        primary = palette.get("primary", "")
        style = design_spec.get("visual_style", "minimal")
        if primary:
            quality += f", dominant color {primary}"
        quality += f", {style} style"

    if asset_type == "splash_image":
        quality += ", hero illustration, gradient background, no text"
    else:
        quality += ", mobile UI mockup, device frame, placeholder content"

    return f"{prompt}. {quality}"


def _image_result(asset_type: str, data: bytes, source: str) -> dict:
    return {
        "asset_type": asset_type,
        "content": data,
        "format": "png",
        "source": source,
        "degraded": False,
    }


# ── Code / spec asset generation (component_code, svg_icon, etc.) ───────────


async def _generate_code_asset(
    asset_type: str,
    prompt: str,
    design_spec: Optional[dict],
    app_name: str,
) -> dict:
    """Generate design code/spec assets using LLM providers."""
    format_map = {
        "component_code": "flutter",
        "svg_icon":       "svg",
        "html_prototype": "html",
        "design_tokens":  "json",
    }
    fmt = format_map.get(asset_type, "text")
    errors: list[str] = []

    # Provider 1: Gemini (best free code-gen quality)
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if gemini_key:
        try:
            text = await _gemini_generate_code(prompt)
            logger.info("[design_gen] gemini code succeeded (%d chars)", len(text))
            _track_cost("gemini", 0.0001)
            return {
                "asset_type": asset_type,
                "content": text,
                "format": fmt,
                "source": "gemini",
                "degraded": False,
            }
        except Exception as e:
            errors.append(f"gemini: {e}")
            logger.warning("[design_gen] gemini: %s", e)

    # Provider 2: OpenRouter free LLM (DeepSeek / Qwen code model)
    or_key = os.getenv("OPENROUTER_API_KEY", "")
    if or_key:
        try:
            text = await _openrouter_generate_code(prompt)
            logger.info("[design_gen] openrouter code succeeded (%d chars)", len(text))
            _track_cost("openrouter", 0.0)
            return {
                "asset_type": asset_type,
                "content": text,
                "format": fmt,
                "source": "openrouter",
                "degraded": False,
            }
        except Exception as e:
            errors.append(f"openrouter: {e}")
            logger.warning("[design_gen] openrouter: %s", e)

    # Provider 3: Groq (fast free inference)
    groq_key = os.getenv("GROQ_API_KEY", "")
    if groq_key:
        try:
            text = await _groq_generate_code(prompt)
            logger.info("[design_gen] groq code succeeded (%d chars)", len(text))
            _track_cost("groq", 0.0)
            return {
                "asset_type": asset_type,
                "content": text,
                "format": fmt,
                "source": "groq",
                "degraded": False,
            }
        except Exception as e:
            errors.append(f"groq: {e}")
            logger.warning("[design_gen] groq: %s", e)

    return {
        "asset_type": asset_type,
        "content": "",
        "format": fmt,
        "source": "degraded",
        "degraded": True,
        "error": "; ".join(errors),
    }


async def _gemini_generate_code(prompt: str) -> str:
    """Call Gemini REST API for code/spec generation (text-only mode)."""
    api_key = os.getenv("GEMINI_API_KEY", "")
    model = "gemini-2.0-flash"
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 4096, "temperature": 0.2},
    }
    import httpx
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(url, json=payload)
    resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


async def _openrouter_generate_code(prompt: str) -> str:
    """OpenRouter free code model (DeepSeek Coder / Qwen2.5-Coder)."""
    api_key = os.getenv("OPENROUTER_API_KEY", "")
    model = os.getenv(
        "DESIGN_CODE_MODEL_OR",
        "deepseek/deepseek-r1-0528:free",
    )
    import httpx
    async with httpx.AsyncClient(timeout=90) as client:
        resp = await client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://github.com/ai-factory-pipeline",
            },
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 4096,
                "temperature": 0.2,
            },
        )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


async def _groq_generate_code(prompt: str) -> str:
    """Groq free fast inference for code generation."""
    api_key = os.getenv("GROQ_API_KEY", "")
    model = "llama-3.3-70b-versatile"
    import httpx
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 4096,
                "temperature": 0.2,
            },
        )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


# ── Cost tracking ────────────────────────────────────────────────────────────


def _track_cost(provider: str, cost: float) -> None:
    try:
        from factory.core.quota_tracker import get_quota_tracker
        import asyncio
        qt = get_quota_tracker()
        asyncio.create_task(
            qt.record_usage(provider, tokens=0, calls=1, cost_usd=cost)
        )
    except Exception:
        pass


# ── Design token preset generator ───────────────────────────────────────────


async def generate_design_tokens_from_spec(design_spec: dict, app_name: str = "") -> dict:
    """Convert a design DNA dict into a full design token JSON.

    Suitable for import into Figma Tokens, Style Dictionary, or Flutter ThemeData.
    """
    if os.getenv("AI_PROVIDER", "").lower() == "mock":
        return {
            "asset_type": "design_tokens",
            "content": json.dumps({"color": {"primary": "#6366f1"}, "font": {"family": "Inter"}}),
            "format": "json",
            "source": "mock",
            "degraded": False,
        }

    palette = design_spec.get("color_palette", {})
    typ = design_spec.get("typography", {})
    spacing = design_spec.get("spacing", {})

    prompt = (
        f"Convert this design specification into a complete Style Dictionary / "
        f"Figma Tokens compatible JSON.\n"
        f"App: {app_name or 'Mobile App'}\n"
        f"Design spec:\n{json.dumps(design_spec, indent=2)}\n\n"
        f"Output a complete JSON with token groups: color, typography, spacing, "
        f"radius, shadow, animation. Follow the Style Dictionary nested format. "
        f"Output ONLY the JSON, no markdown fences."
    )
    result = await _generate_code_asset("design_tokens", prompt, design_spec, app_name)
    if result.get("degraded"):
        return result

    raw = result["content"]
    # Try to parse and re-emit clean JSON
    try:
        import re
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            tokens = json.loads(match.group())
            result["content"] = json.dumps(tokens, indent=2)
    except (json.JSONDecodeError, ValueError):
        pass  # return raw string if not parseable

    return result
