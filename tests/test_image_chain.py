"""
Tests for FIX-IMG-CHAIN: 8-provider image generation catalog,
chain-by-mode policy, prompt enhancement, and candidate scoring.
"""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch

import pytest

os.environ.setdefault("AI_PROVIDER", "mock")
os.environ.setdefault("PIPELINE_ENV", "ci")
os.environ.setdefault("DRY_RUN", "true")


# ─── chain_for_mode ───────────────────────────────────────────────────────────

def test_basic_mode_excludes_fal_providers():
    """BASIC chain must not include fal_* (trial-credits, not free-tier)."""
    os.environ.pop("IMAGE_PROVIDER_CHAIN", None)
    # Temporarily remove FAL key to ensure clean test
    fal_key_backup = os.environ.pop("FAL_API_KEY", None)
    try:
        from factory.design.image_chain import chain_for_mode
        chain = chain_for_mode("basic")
        fal_providers = [p for p in chain if p.startswith("fal_")]
        assert not fal_providers, f"BASIC chain must not include fal providers: {fal_providers}"
    finally:
        if fal_key_backup:
            os.environ["FAL_API_KEY"] = fal_key_backup


def test_chain_drops_provider_without_key():
    """A provider with no API key must be absent from the returned chain."""
    os.environ.pop("IMAGE_PROVIDER_CHAIN", None)
    # Force ideogram key absent
    key_backup = os.environ.pop("IDEOGRAM_API_KEY", None)
    try:
        from importlib import reload
        import factory.design.image_chain as ic
        reload(ic)
        chain = ic.chain_for_mode("basic")
        assert "ideogram_v3" not in chain, "ideogram_v3 must be dropped when IDEOGRAM_API_KEY is absent"
    finally:
        if key_backup:
            os.environ["IDEOGRAM_API_KEY"] = key_backup


def test_pollinations_always_in_basic_chain():
    """Pollinations requires no key — must always be available in BASIC."""
    os.environ.pop("IMAGE_PROVIDER_CHAIN", None)
    from factory.design.image_chain import chain_for_mode
    chain = chain_for_mode("basic")
    assert "pollinations" in chain


def test_turbo_chain_starts_with_fal_when_key_present():
    """TURBO chain should prefer fal_flux2_pro when FAL_API_KEY is set."""
    os.environ.pop("IMAGE_PROVIDER_CHAIN", None)
    os.environ["FAL_API_KEY"] = "test-key"
    try:
        from importlib import reload
        import factory.design.image_chain as ic
        reload(ic)
        chain = ic.chain_for_mode("turbo")
        assert chain[0] == "fal_flux2_pro", f"TURBO head should be fal_flux2_pro, got {chain[0]}"
    finally:
        del os.environ["FAL_API_KEY"]


def test_env_override_takes_precedence():
    """IMAGE_PROVIDER_CHAIN env var must override mode-based chain (keyless providers)."""
    os.environ["IMAGE_PROVIDER_CHAIN"] = "pollinations"
    try:
        from importlib import reload
        import factory.design.image_chain as ic
        reload(ic)
        chain = ic.chain_for_mode("turbo")
        assert chain == ["pollinations"], f"Expected ['pollinations'], got {chain}"
    finally:
        del os.environ["IMAGE_PROVIDER_CHAIN"]


def test_all_modes_return_non_empty_chain():
    """Every named mode must produce a non-empty chain (Pollinations always available)."""
    from factory.design.image_chain import chain_for_mode
    for mode in ("basic", "balanced", "turbo", "custom"):
        chain = chain_for_mode(mode)
        assert chain, f"Mode {mode} returned empty chain"


# ─── Negative prompt routing ──────────────────────────────────────────────────

def test_negative_prompt_baked_for_flux_providers():
    """FLUX-based providers don't support separate negative_prompt — must bake."""
    from factory.design.image_chain import _prepare_prompt
    prompt = "App icon with letter P"
    neg = "watermark, blurry"
    for provider in ("pollinations", "cloudflare_flux_schnell", "together_flux_schnell"):
        main, negative_out = _prepare_prompt(prompt, neg, provider)
        assert negative_out == "", f"{provider} should not have separate negative"
        assert neg in main or "Avoid:" in main, f"{provider} should bake negatives into main prompt"


def test_negative_prompt_passed_separately_for_ideogram():
    """Ideogram supports separate negative_prompt — must NOT bake into main."""
    from factory.design.image_chain import _prepare_prompt
    prompt = "App icon with letter P"
    neg = "watermark, blurry"
    main, negative_out = _prepare_prompt(prompt, neg, "ideogram_v3")
    assert negative_out == neg
    assert "watermark" not in main


# ─── Candidate scoring ────────────────────────────────────────────────────────

def test_score_candidate_zero_for_tiny_data():
    from factory.design.image_chain import _score_candidate
    score = _score_candidate(b"tiny", "pollinations")
    assert score < 0.5


def test_score_candidate_higher_for_large_data():
    from factory.design.image_chain import _score_candidate
    large = b"x" * 300_000
    small = b"x" * 3_000
    assert _score_candidate(large, "pollinations") > _score_candidate(small, "pollinations")


def test_ideogram_scores_higher_than_pollinations_same_size():
    """Provider quality weight should make ideogram score higher at equal size."""
    from factory.design.image_chain import _score_candidate
    data = b"x" * 200_000
    assert _score_candidate(data, "ideogram_v3") > _score_candidate(data, "pollinations")


# ─── Dry-run generate functions ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_image_returns_mock_in_dry_run():
    from factory.design.image_chain import generate_image
    result = await generate_image("logo of letter P", master_mode="basic")
    assert result == b"MOCK_IMAGE_BYTES"


@pytest.mark.asyncio
async def test_generate_image_best_of_returns_list_in_dry_run():
    from factory.design.image_chain import generate_image_best_of
    results = await generate_image_best_of("logo of letter P", master_mode="basic")
    assert isinstance(results, list)
    assert len(results) >= 1
    assert results[0]["provider"] == "mock"


# ─── Pollinations dispatch (real HTTP, no key needed) ────────────────────────

@pytest.mark.asyncio
async def test_pollinations_dispatch_with_mock_http():
    """Pollinations dispatch should work with mocked HTTP."""
    from factory.design.image_chain import generate_via_pollinations

    fake_bytes = b"\x89PNG\r\n" + b"x" * 1000

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_response = AsyncMock()
        mock_response.content = fake_bytes
        mock_response.raise_for_status = lambda: None
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=AsyncMock(
            get=AsyncMock(return_value=mock_response)
        ))
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        # Remove DRY_RUN for this test to actually call dispatch
        old = os.environ.pop("DRY_RUN", None)
        try:
            result = await generate_via_pollinations("test logo")
        finally:
            if old:
                os.environ["DRY_RUN"] = old


# ─── Enhance prompt (dry-run fast path) ──────────────────────────────────────

@pytest.mark.asyncio
async def test_enhance_logo_prompt_returns_raw_in_dry_run():
    """In dry-run / mock mode, enhance_logo_prompt must return raw prompt + default negative."""
    from factory.design.image_chain import enhance_logo_prompt, _DEFAULT_LOGO_NEGATIVE
    enhanced, negative = await enhance_logo_prompt("P ❤️", app_name="TestApp")
    assert enhanced == "P ❤️"
    assert negative == _DEFAULT_LOGO_NEGATIVE


# ─── has_key helper ───────────────────────────────────────────────────────────

def test_has_key_pollinations_always_true():
    from factory.design.image_chain import _has_key
    assert _has_key("pollinations") is True


def test_has_key_ideogram_false_when_no_env():
    backup = os.environ.pop("IDEOGRAM_API_KEY", None)
    try:
        from importlib import reload
        import factory.design.image_chain as ic
        reload(ic)
        assert ic._has_key("ideogram_v3") is False
    finally:
        if backup:
            os.environ["IDEOGRAM_API_KEY"] = backup
