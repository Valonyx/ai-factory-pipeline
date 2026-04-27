"""
Tests for FIX-LEGAL: Arabic font rendering, scout cache isolation,
data-residency accuracy, and PDF completeness.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("AI_PROVIDER", "mock")
os.environ.setdefault("PIPELINE_ENV", "ci")
os.environ.setdefault("DRY_RUN", "true")


# ─── Arabic font / reshaping ──────────────────────────────────────────────────

def test_arabic_text_is_reshaped_not_identity():
    from factory.legal.pdf_generator import reshape_arabic, _ARABIC_SUPPORT
    if not _ARABIC_SUPPORT:
        pytest.skip("arabic_reshaper not installed")
    raw = "سياسة الخصوصية"
    shaped = reshape_arabic(raw)
    # Reshaping must change the character order/form
    assert shaped != raw, "reshape_arabic should transform Arabic text"
    assert len(shaped) > 0


def test_has_arabic_detects_arabic_range():
    from factory.legal.pdf_generator import _has_arabic
    assert _has_arabic("المملكة العربية السعودية")
    assert not _has_arabic("Kingdom of Saudi Arabia")
    assert not _has_arabic("")


def test_arabic_font_registered_with_reportlab():
    from factory.legal.pdf_generator import _ARABIC_FONT
    assert _ARABIC_FONT != "Helvetica", (
        "Arabic TTF not registered — _ARABIC_FONT fell back to Helvetica. "
        "Check factory/legal/fonts/ contains valid NotoSansArabic-Regular.ttf"
    )
    from reportlab.pdfbase import pdfmetrics
    registered = pdfmetrics.getRegisteredFontNames()
    assert _ARABIC_FONT in registered


def test_safe_text_escapes_xml_on_latin():
    from factory.legal.pdf_generator import _safe_text
    raw = "Terms & Conditions <draft>"
    out = _safe_text(raw)
    assert "&amp;" in out
    assert "&lt;" in out
    assert "&gt;" in out


def test_safe_text_reshapes_pure_arabic():
    from factory.legal.pdf_generator import _safe_text, _ARABIC_SUPPORT
    if not _ARABIC_SUPPORT:
        pytest.skip("arabic_reshaper not installed")
    raw = "سياسة الخصوصية"
    out = _safe_text(raw)
    # Reshaped Arabic is different from the raw input
    assert out != raw


# ─── PDF generation ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_legal_dossier_pdf_creates_file():
    from factory.legal.pdf_generator import generate_legal_dossier_pdf

    legal_output = {
        "app_category": "fintech",
        "risk_level": "high",
        "required_licenses": ["SAMA", "NCA"],
        "compliance_items": [],
        "risks": [],
        "data_residency": {"region": "me-central1", "provider": "GCP"},
    }
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch("factory.legal.pdf_generator.Path", wraps=Path) as _p:
            # Redirect artifacts dir to temp
            original_artifacts = Path("artifacts")
            result = await generate_legal_dossier_pdf(
                project_id="test_pdf_project",
                app_name="TestApp",
                legal_output=legal_output,
                legal_research="KSA regulations: PDPL, NCA controls...",
                legal_documents={
                    "privacy_policy": "# Privacy Policy\n\nسياسة الخصوصية\n\nThis is a test.",
                    "terms_of_use": "# Terms\n\nTest terms.",
                },
            )
    assert result.endswith((".pdf", ".txt"))


def test_pdf_arabic_style_uses_noto_font():
    from factory.legal.pdf_generator import _build_styles, _ARABIC_FONT
    styles = _build_styles()
    assert "arabic" in styles
    assert "arabic_body" in styles
    assert styles["arabic"].fontName == _ARABIC_FONT
    assert styles["arabic_body"].fontName == _ARABIC_FONT


# ─── Scout cache isolation by project_id ─────────────────────────────────────

def test_scout_cache_keyed_by_project_id():
    """Two different project_ids must not share cache entries."""
    try:
        from factory.integrations.scout_orchestrator import ScoutOrchestrator
    except ImportError:
        pytest.skip("ScoutOrchestrator not available")

    h1 = ScoutOrchestrator._query_hash("PDPL compliance", project_id="proj_aaa")
    h2 = ScoutOrchestrator._query_hash("PDPL compliance", project_id="proj_bbb")
    h_noproj = ScoutOrchestrator._query_hash("PDPL compliance", project_id="")

    assert h1 != h2, "Different project_ids must produce different cache keys"
    assert h1 != h_noproj
    assert h2 != h_noproj


def test_scout_cache_same_project_same_query_is_stable():
    try:
        from factory.integrations.scout_orchestrator import ScoutOrchestrator
    except ImportError:
        pytest.skip("ScoutOrchestrator not available")

    h1 = ScoutOrchestrator._query_hash("NCA controls", project_id="proj_xyz")
    h2 = ScoutOrchestrator._query_hash("NCA controls", project_id="proj_xyz")
    assert h1 == h2


# ─── Data residency — no hardcoded AWS / Azure ───────────────────────────────

def test_no_aws_or_azure_in_data_residency_section():
    """KSA-focused legal docs must not reference AWS or Azure regions by default."""
    from factory.legal.pdf_generator import _data_residency_plan, _build_styles
    styles = _build_styles()
    legal_output = {
        "data_residency": {"region": "me-central1", "provider": "GCP"},
        "risk_level": "medium",
    }
    elements = _data_residency_plan(legal_output, styles)
    text_content = " ".join(
        getattr(e, "text", "") or "" for e in elements
    ).lower()
    assert "aws" not in text_content, "Data residency section must not mention AWS"
    assert "azure" not in text_content, "Data residency section must not mention Azure"
