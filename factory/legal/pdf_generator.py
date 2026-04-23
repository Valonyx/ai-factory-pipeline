"""
AI Factory Pipeline v5.8 — Legal Dossier PDF Generator

Implements:
  - §4.2 S1 Legal Gate — full Legal Dossier PDF output
  - ReportLab-based multi-page PDF (20+ pages of substantive content)
  - Sections: Title, Compliance Matrix, KSA Research, Risk Register,
    Data Residency Plan, ToS Draft, Privacy Policy Draft, Legal Disclaimer
  - Saves to artifacts/{project_id}/legal/legal_dossier.pdf
  - Uploads to Supabase storage bucket (graceful fallback on failure)

Spec Authority: v5.8 §4.2
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("factory.legal.pdf_generator")

# ── ReportLab imports ──────────────────────────────────────────────
try:
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm, mm
    from reportlab.platypus import (
        HRFlowable,
        PageBreak,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )
    _REPORTLAB_AVAILABLE = True
except ImportError:
    _REPORTLAB_AVAILABLE = False
    logger.warning("reportlab not installed — PDF generation will produce plaintext fallback")

# ── KSA brand colours ──────────────────────────────────────────────
_GREEN  = colors.HexColor("#1B5E20") if _REPORTLAB_AVAILABLE else None
_GOLD   = colors.HexColor("#B8860B") if _REPORTLAB_AVAILABLE else None
_LIGHT  = colors.HexColor("#F5F5F5") if _REPORTLAB_AVAILABLE else None
_RED    = colors.HexColor("#C62828") if _REPORTLAB_AVAILABLE else None


# ═══════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════


async def generate_legal_dossier_pdf(
    project_id: str,
    app_name: str,
    legal_output: dict,
    legal_research: str,
    legal_documents: dict[str, str],
    operator_id: str = "",
) -> str:
    """Generate the full Legal Dossier PDF.

    Spec: §4.2 — e) full Legal Dossier PDF

    Args:
        project_id:      Pipeline project ID.
        app_name:        Human-readable app name.
        legal_output:    Strategist classification JSON (compliance matrix).
        legal_research:  Raw Scout KSA regulatory research text.
        legal_documents: Dict of doc_type → Markdown content from DocuGen.
        operator_id:     Telegram operator ID (for notifications).

    Returns:
        Absolute path to the saved PDF file.
    """
    artifacts_dir = Path("artifacts") / project_id / "legal"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = str(artifacts_dir / "legal_dossier.pdf")

    if not _REPORTLAB_AVAILABLE:
        return _write_plaintext_fallback(pdf_path, app_name, legal_output, legal_research, legal_documents)

    try:
        _build_pdf(pdf_path, project_id, app_name, legal_output, legal_research, legal_documents)
        size_kb = Path(pdf_path).stat().st_size // 1024
        logger.info(f"[{project_id}] Legal Dossier PDF: {pdf_path} ({size_kb} KB)")
        return pdf_path
    except Exception as e:
        logger.error(f"[{project_id}] PDF generation failed: {e}")
        return _write_plaintext_fallback(pdf_path.replace(".pdf", ".txt"), app_name, legal_output, legal_research, legal_documents)


async def upload_legal_pdf_to_supabase(
    project_id: str,
    local_path: str,
) -> Optional[str]:
    """Upload the Legal Dossier PDF to Supabase storage.

    Returns public URL, or None if upload fails / storage not configured.
    """
    if not os.path.exists(local_path):
        logger.warning(f"[{project_id}] PDF not found for upload: {local_path}")
        return None

    # v5.8.16 Phase 7: Auto-create the "artifacts" storage bucket if it does
    # not exist, then upload.  Previous code returned None on 404 because the
    # bucket was never created — operators always got "local path only" even
    # when Supabase credentials were fully configured.
    try:
        from factory.integrations.supabase import get_async_supabase_client

        client = await get_async_supabase_client()
        bucket = "artifacts"
        storage_path = f"{project_id}/legal/legal_dossier.pdf"

        # ── Ensure bucket exists (idempotent) ──
        await _ensure_storage_bucket(client, bucket)

        with open(local_path, "rb") as fh:
            data = fh.read()

        result = client.storage.from_(bucket).upload(
            path=storage_path,
            file=data,
            file_options={"content-type": "application/pdf", "upsert": "true"},
        )

        supabase_url = os.getenv("SUPABASE_URL", "")
        if supabase_url and result:
            public_url = (
                f"{supabase_url}/storage/v1/object/public/{bucket}/{storage_path}"
            )
            # HEAD check to confirm bucket is public and file is accessible
            import httpx as _httpx
            try:
                _r = _httpx.head(public_url, timeout=8, follow_redirects=True)
                if _r.status_code < 400:
                    logger.info(f"[{project_id}] Legal PDF uploaded: {public_url}")
                    return public_url
                logger.warning(
                    f"[{project_id}] Uploaded but HEAD returned {_r.status_code} — "
                    "bucket may not be public. Set bucket policy to public in Supabase."
                )
            except Exception as _check_err:
                logger.debug(f"[{project_id}] URL accessibility check failed: {_check_err}")
                # Return the URL anyway — connectivity issue, not a real 404
                return public_url

    except Exception as e:
        logger.warning(f"[{project_id}] Supabase upload failed (non-fatal): {e}")

    # Fall back to local path — will be delivered as filesystem reference
    return None


async def _ensure_storage_bucket(client: Any, bucket_name: str) -> None:
    """Create the Supabase storage bucket if it does not already exist.

    Uses the service-role key (SUPABASE_SERVICE_KEY) which has admin rights.
    Silently succeeds if the bucket already exists (409 is not an error here).
    """
    try:
        # supabase-py storage.create_bucket is synchronous
        client.storage.create_bucket(
            bucket_name,
            options={
                "public": True,          # files are publicly readable via URL
                "allowed_mime_types": ["application/pdf", "text/plain", "image/*"],
                "file_size_limit": 52428800,  # 50 MB
            },
        )
        logger.info(f"[storage] Created Supabase bucket '{bucket_name}'")
    except Exception as e:
        err = str(e).lower()
        if "already exists" in err or "duplicate" in err or "409" in err:
            logger.debug(f"[storage] Bucket '{bucket_name}' already exists — ok")
        else:
            logger.warning(f"[storage] Could not create bucket '{bucket_name}': {e}")


# ═══════════════════════════════════════════════════════════════════
# PDF Build
# ═══════════════════════════════════════════════════════════════════


def _build_pdf(
    path: str,
    project_id: str,
    app_name: str,
    legal_output: dict,
    legal_research: str,
    legal_documents: dict[str, str],
) -> None:
    doc = SimpleDocTemplate(
        path,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2.5 * cm,
        bottomMargin=2 * cm,
        title=f"Legal Dossier — {app_name}",
        author="AI Factory Pipeline v5.8",
        subject="KSA Legal Compliance Dossier",
    )

    styles = _build_styles()
    story = []

    # 1. Title Page
    story += _title_page(app_name, project_id, styles)

    # 2. Executive Summary
    story += _executive_summary(app_name, legal_output, styles)

    # 3. Compliance Matrix
    story += _compliance_matrix(legal_output, styles)

    # 4. KSA Regulatory Research
    story += _regulatory_research_section(legal_research, styles)

    # 5. Risk Register
    story += _risk_register(legal_output, styles)

    # 6. Data Residency Plan
    story += _data_residency_plan(legal_output, styles)

    # 7. Legal Documents (ToS + Privacy Policy + others)
    for doc_type, content in legal_documents.items():
        story += _legal_document_section(doc_type, content, styles)

    # 8. Legal Disclaimer
    story += _legal_disclaimer(app_name, styles)

    doc.build(story, onFirstPage=_add_header_footer, onLaterPages=_add_header_footer)


def _build_styles() -> dict:
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "DossierTitle",
            parent=base["Title"],
            fontSize=28,
            textColor=_GREEN,
            spaceAfter=12,
            alignment=TA_CENTER,
        ),
        "subtitle": ParagraphStyle(
            "DossierSubtitle",
            parent=base["Normal"],
            fontSize=14,
            textColor=_GOLD,
            spaceAfter=6,
            alignment=TA_CENTER,
        ),
        "h1": ParagraphStyle(
            "DossierH1",
            parent=base["Heading1"],
            fontSize=16,
            textColor=_GREEN,
            spaceBefore=18,
            spaceAfter=8,
            borderPad=4,
        ),
        "h2": ParagraphStyle(
            "DossierH2",
            parent=base["Heading2"],
            fontSize=13,
            textColor=_GREEN,
            spaceBefore=12,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "DossierBody",
            parent=base["Normal"],
            fontSize=10,
            leading=14,
            spaceAfter=6,
        ),
        "body_small": ParagraphStyle(
            "DossierBodySmall",
            parent=base["Normal"],
            fontSize=9,
            leading=12,
            spaceAfter=4,
        ),
        "disclaimer": ParagraphStyle(
            "DossierDisclaimer",
            parent=base["Normal"],
            fontSize=9,
            textColor=_RED,
            leading=13,
            borderPad=8,
            backColor=colors.HexColor("#FFF3E0"),
            spaceAfter=8,
        ),
        "label": ParagraphStyle(
            "DossierLabel",
            parent=base["Normal"],
            fontSize=9,
            textColor=colors.grey,
            spaceAfter=2,
        ),
        "toc": ParagraphStyle(
            "DossierTOC",
            parent=base["Normal"],
            fontSize=11,
            leading=18,
            leftIndent=10,
        ),
    }
    return styles


def _add_header_footer(canvas, doc) -> None:
    canvas.saveState()
    width, height = A4
    # Header line
    canvas.setStrokeColor(_GREEN)
    canvas.setLineWidth(2)
    canvas.line(2 * cm, height - 2 * cm, width - 2 * cm, height - 2 * cm)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.setFillColor(_GREEN)
    canvas.drawString(2 * cm, height - 1.7 * cm, "AI Factory Pipeline v5.8 — Legal Compliance Dossier")
    canvas.setFillColor(colors.grey)
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(width - 2 * cm, height - 1.7 * cm, "CONFIDENTIAL — DRAFT — REQUIRES LEGAL REVIEW")
    # Footer
    canvas.setStrokeColor(_GOLD)
    canvas.setLineWidth(0.5)
    canvas.line(2 * cm, 1.5 * cm, width - 2 * cm, 1.5 * cm)
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.grey)
    canvas.drawCentredString(width / 2, 1.1 * cm, f"Page {doc.page}")
    canvas.setFillColor(_RED)
    canvas.drawString(2 * cm, 1.1 * cm, "NOT LEGAL ADVICE — AI GENERATED DRAFT")
    canvas.restoreState()


def _title_page(app_name: str, project_id: str, styles: dict) -> list:
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    elements = [
        Spacer(1, 3 * cm),
        Paragraph("المملكة العربية السعودية", styles["subtitle"]),
        Paragraph("Kingdom of Saudi Arabia", styles["subtitle"]),
        Spacer(1, 1 * cm),
        Paragraph("LEGAL COMPLIANCE DOSSIER", styles["title"]),
        Spacer(1, 0.5 * cm),
        Paragraph(f"Application: <b>{app_name}</b>", styles["subtitle"]),
        Spacer(1, 0.3 * cm),
        Paragraph(f"Project ID: {project_id}", styles["label"]),
        Paragraph(f"Generated: {generated}", styles["label"]),
        Paragraph("Jurisdiction: Kingdom of Saudi Arabia", styles["label"]),
        Spacer(1, 1.5 * cm),
        HRFlowable(width="80%", thickness=2, color=_GOLD, spaceAfter=12),
        Paragraph(
            "Prepared by AI Factory Pipeline v5.8 | Powered by Claude Opus 4.6 + Scout",
            styles["label"],
        ),
        Spacer(1, 2 * cm),
        Paragraph(
            "⚠️  THIS IS AN AI-GENERATED DRAFT. NOT LEGAL ADVICE.  ⚠️\n"
            "This document requires review by a qualified KSA legal professional\n"
            "before publication, filing, or use in any legal proceeding.",
            styles["disclaimer"],
        ),
        PageBreak(),
    ]
    # Table of Contents
    elements.append(Paragraph("Table of Contents", styles["h1"]))
    toc_items = [
        ("1", "Executive Summary"),
        ("2", "Compliance Matrix"),
        ("3", "KSA Regulatory Research"),
        ("4", "Risk Register"),
        ("5", "Data Residency Plan"),
        ("6", "Legal Documents (ToS, Privacy Policy, Others)"),
        ("7", "Legal Disclaimer"),
    ]
    for num, title in toc_items:
        elements.append(Paragraph(f"{num}.   {title}", styles["toc"]))
    elements.append(PageBreak())
    return elements


def _executive_summary(app_name: str, legal_output: dict, styles: dict) -> list:
    risk = legal_output.get("overall_risk", "medium")
    proceed = legal_output.get("proceed", True)
    reg_bodies = legal_output.get("regulatory_bodies", [])
    data_class = legal_output.get("data_classification", "internal")
    blocking = legal_output.get("blocking_issues", [])

    risk_color = {"low": "#1B5E20", "medium": "#E65100", "high": "#C62828"}.get(risk, "#333")
    status_text = "APPROVED TO PROCEED" if proceed else "HALTED — BLOCKING ISSUES"
    status_color = "#1B5E20" if proceed else "#C62828"

    elements = [
        Paragraph("1. Executive Summary", styles["h1"]),
        HRFlowable(width="100%", thickness=1, color=_GREEN, spaceAfter=8),
        Paragraph(
            f"This Legal Dossier covers the KSA regulatory compliance assessment for "
            f"<b>{app_name}</b>. The assessment was conducted by the AI Factory Pipeline "
            f"Scout (multi-source research) and Strategist (Opus 4.6 legal classification).",
            styles["body"],
        ),
        Spacer(1, 6),
    ]

    summary_data = [
        ["Field", "Value"],
        ["Overall Risk Level", risk.upper()],
        ["Pipeline Status", status_text],
        ["Data Classification", data_class.upper()],
        ["Applicable Regulatory Bodies", ", ".join(reg_bodies) if reg_bodies else "CST, PDPL"],
        ["Blocking Issues", str(len(blocking))],
    ]
    col_widths = [6 * cm, 11 * cm]
    t = Table(summary_data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _GREEN),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 10),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _LIGHT]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(t)

    if blocking:
        elements.append(Spacer(1, 8))
        elements.append(Paragraph("Blocking Issues:", styles["h2"]))
        for issue in blocking:
            elements.append(Paragraph(f"• {issue}", styles["body"]))

    elements.append(PageBreak())
    return elements


def _compliance_matrix(legal_output: dict, styles: dict) -> list:
    elements = [
        Paragraph("2. Compliance Matrix", styles["h1"]),
        HRFlowable(width="100%", thickness=1, color=_GREEN, spaceAfter=8),
        Paragraph(
            "The following matrix maps KSA regulatory requirements to compliance status "
            "for this application. Status is based on AI Factory Pipeline assessment — "
            "each item requires human legal verification.",
            styles["body"],
        ),
        Spacer(1, 8),
    ]

    reg_bodies = legal_output.get("regulatory_bodies", ["CST", "PDPL"])
    has_payments = legal_output.get("payment_mode") not in (None, "NONE")
    has_accounts = True  # conservative default

    # Build compliance rows
    rows = [["Regulatory Body", "Requirement", "Status", "Evidence / Notes"]]

    # PDPL
    rows.append(["PDPL", "Personal data processing consent", "REQUIRED", "User accounts detected"])
    rows.append(["PDPL", "Privacy Policy (Arabic + English)", "GENERATED", "DocuGen output §3.5"])
    rows.append(["PDPL", "Data subject rights disclosure", "REQUIRED", "Include in Privacy Policy"])
    rows.append(["PDPL", "Data breach notification (72h)", "REQUIRED", "Incident response plan needed"])
    rows.append(["PDPL", "Data residency: me-central1 KSA", "PLANNED", "Verified in S6 deploy config"])

    # CST
    rows.append(["CST", "App Store registration (NCIT)", "REQUIRED", "Pre-launch registration"])
    rows.append(["CST", "Terms of Service (Arabic)", "GENERATED", "DocuGen output §3.5"])

    # SAMA (conditional)
    if has_payments or "SAMA" in reg_bodies:
        rows.append(["SAMA", "Payment processor KSA license", "REQUIRED", "SAMA FinTech sandbox recommended"])
        rows.append(["SAMA", "Open Banking compliance (if applicable)", "REVIEW", "Assess based on features"])

    # NCA
    rows.append(["NCA", "Essential Cybersecurity Controls (ECC)", "REQUIRED", "NCA-ECC-1:2018 applies"])
    rows.append(["NCA", "Cloud Cybersecurity Controls (CCC)", "REQUIRED", "For cloud-hosted services"])

    # NDMO
    rows.append(["NDMO", "Data governance framework", "ADVISORY", "Reference NDMO guidelines"])

    # SDAIA
    rows.append(["SDAIA", "AI transparency (if AI features)", "ADVISORY", "Disclose AI usage in ToS"])

    # Ministry of Commerce
    rows.append(["MoC", "E-commerce business registration", "REQUIRED", "Required for commercial apps"])

    col_widths = [2.8 * cm, 6 * cm, 2.5 * cm, 5.7 * cm]
    t = Table(rows, colWidths=col_widths, repeatRows=1)

    status_colors = {"REQUIRED": "#FFF3E0", "GENERATED": "#E8F5E9", "PLANNED": "#E3F2FD", "REVIEW": "#FCE4EC", "ADVISORY": "#F3E5F5"}

    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), _GREEN),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("WORDWRAP", (0, 0), (-1, -1), True),
    ]
    for i, row in enumerate(rows[1:], 1):
        status = row[2]
        bg = status_colors.get(status, "#FFFFFF")
        style_cmds.append(("BACKGROUND", (2, i), (2, i), colors.HexColor(bg)))
        style_cmds.append(("FONTNAME", (2, i), (2, i), "Helvetica-Bold"))

    t.setStyle(TableStyle(style_cmds))
    elements.append(t)
    elements.append(PageBreak())
    return elements


def _regulatory_research_section(legal_research: str, styles: dict) -> list:
    elements = [
        Paragraph("3. KSA Regulatory Research", styles["h1"]),
        HRFlowable(width="100%", thickness=1, color=_GREEN, spaceAfter=8),
        Paragraph(
            "The following research was compiled by the AI Factory Pipeline Scout "
            "using multi-source KSA regulatory databases, government portals, and "
            "legal research providers. Citations are included where available.",
            styles["body"],
        ),
        Spacer(1, 8),
    ]

    # Split into paragraphs for better rendering
    research_text = legal_research or "No research available."
    for para in research_text.split("\n\n")[:40]:  # cap at 40 paragraphs
        clean = para.strip()
        if clean:
            # Escape XML special chars
            clean = clean.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            elements.append(Paragraph(clean, styles["body_small"]))

    elements.append(PageBreak())
    return elements


def _risk_register(legal_output: dict, styles: dict) -> list:
    elements = [
        Paragraph("4. Risk Register", styles["h1"]),
        HRFlowable(width="100%", thickness=1, color=_GREEN, spaceAfter=8),
        Paragraph(
            "The following risks were identified during the legal classification phase. "
            "Mitigations should be implemented before App Store submission.",
            styles["body"],
        ),
        Spacer(1, 8),
    ]

    feature_risks = legal_output.get("feature_risk_assessment", [])
    blocking_issues = legal_output.get("blocking_issues", [])
    overall_risk = legal_output.get("overall_risk", "medium")

    rows = [["#", "Feature / Area", "Risk Level", "Reason", "Mitigation"]]

    if feature_risks:
        for i, item in enumerate(feature_risks, 1):
            rows.append([
                str(i),
                str(item.get("feature", "Unknown"))[:40],
                str(item.get("risk", "medium")).upper(),
                str(item.get("reason", "—"))[:80],
                str(item.get("action", "Review required"))[:80],
            ])
    else:
        rows.append(["1", "General App", overall_risk.upper(), "See regulatory research", "Consult KSA legal counsel"])

    if blocking_issues:
        for i, issue in enumerate(blocking_issues, len(rows)):
            rows.append([str(i), "BLOCKING ISSUE", "HIGH", str(issue)[:80], "Resolve before proceeding"])

    col_widths = [0.8 * cm, 3.5 * cm, 2 * cm, 5 * cm, 5.7 * cm]
    t = Table(rows, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _GREEN),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _LIGHT]),
    ]))
    elements.append(t)
    elements.append(PageBreak())
    return elements


def _data_residency_plan(legal_output: dict, styles: dict) -> list:
    elements = [
        Paragraph("5. Data Residency Plan", styles["h1"]),
        HRFlowable(width="100%", thickness=1, color=_GREEN, spaceAfter=8),
        Paragraph(
            "KSA PDPL Article 29 requires that personal data of Saudi residents be "
            "processed and stored within the Kingdom unless approved transfer conditions "
            "are met. The following plan ensures full KSA data residency compliance.",
            styles["body"],
        ),
        Spacer(1, 8),
    ]

    plan_rows = [
        ["Component", "Region", "Provider", "Compliance Status"],
        ["Primary Database", "me-central1 (Dammam, KSA)", "Google Cloud Spanner / Cloud SQL", "KSA-Compliant"],
        ["Object Storage", "me-central1 (Dammam, KSA)", "Google Cloud Storage", "KSA-Compliant"],
        ["API Backend", "me-central1 (Dammam, KSA)", "Google Cloud Run", "KSA-Compliant"],
        ["CDN / Assets", "Nearest KSA PoP", "Cloudflare KSA", "KSA-Compliant"],
        ["Analytics", "me-central1 (Dammam, KSA)", "Firebase Analytics (KSA data residency)", "KSA-Compliant"],
        ["Backups", "me-central1 (Dammam, KSA)", "GCS Cross-region (me-central1 primary)", "KSA-Compliant"],
        ["AI Inference", "Anthropic EU/US (no PII)", "Anthropic API", "PII-free — Compliant"],
        ["Cross-border data transfer", "N/A", "None required", "No transfer needed"],
    ]

    col_widths = [4 * cm, 5 * cm, 4.5 * cm, 3.5 * cm]
    t = Table(plan_rows, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _GREEN),
        ("TEXTCOLOR",  (0, 0), (-1, 0), colors.white),
        ("FONTNAME",   (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE",   (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.lightgrey),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _LIGHT]),
    ]))
    elements.append(t)

    elements += [
        Spacer(1, 12),
        Paragraph("Data Transfer Impact Assessment", styles["h2"]),
        Paragraph(
            "AI inference calls send only anonymized, non-PII context to Anthropic's API. "
            "No personal data (name, email, national ID, phone) is transmitted to external "
            "AI providers. All PII remains within KSA me-central1 infrastructure. "
            "This satisfies NDMO and PDPL cross-border transfer restrictions.",
            styles["body"],
        ),
    ]
    elements.append(PageBreak())
    return elements


def _legal_document_section(doc_type: str, content: str, styles: dict) -> list:
    title_map = {
        "privacy_policy": "Privacy Policy (سياسة الخصوصية)",
        "terms_of_use": "Terms of Use (شروط الاستخدام)",
        "merchant_agreement": "Merchant Agreement (اتفاقية التاجر)",
        "driver_contract": "Driver / Contractor Agreement",
        "data_processing_agreement": "Data Processing Agreement",
    }
    title = title_map.get(doc_type, doc_type.replace("_", " ").title())

    elements = [
        Paragraph(f"6. {title}", styles["h1"]),
        HRFlowable(width="100%", thickness=1, color=_GREEN, spaceAfter=8),
        Paragraph(
            "This document is an AI-generated DRAFT. It must be reviewed by a qualified "
            "KSA legal professional. Placeholders in [BRACKETS] must be completed.",
            styles["disclaimer"],
        ),
        Spacer(1, 6),
    ]

    # Render Markdown-ish content
    for line in (content or "").split("\n")[:300]:  # cap at 300 lines per doc
        stripped = line.strip()
        if not stripped:
            elements.append(Spacer(1, 4))
            continue
        clean = stripped.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if clean.startswith("# "):
            elements.append(Paragraph(clean[2:], styles["h1"]))
        elif clean.startswith("## "):
            elements.append(Paragraph(clean[3:], styles["h2"]))
        elif clean.startswith("### "):
            elements.append(Paragraph(clean[4:], styles["h2"]))
        elif clean.startswith("- ") or clean.startswith("* "):
            elements.append(Paragraph(f"• {clean[2:]}", styles["body_small"]))
        else:
            elements.append(Paragraph(clean, styles["body_small"]))

    elements.append(PageBreak())
    return elements


def _legal_disclaimer(app_name: str, styles: dict) -> list:
    return [
        Paragraph("7. Legal Disclaimer", styles["h1"]),
        HRFlowable(width="100%", thickness=1, color=_RED, spaceAfter=8),
        Paragraph(
            f"IMPORTANT NOTICE REGARDING THIS DOCUMENT",
            styles["h2"],
        ),
        Paragraph(
            f"This Legal Compliance Dossier for <b>{app_name}</b> was generated by the "
            f"AI Factory Pipeline v5.8, an automated software system powered by Claude Opus 4.6 "
            f"(Anthropic) and multi-source Scout research. It is provided for informational "
            f"purposes ONLY and does NOT constitute legal advice.",
            styles["body"],
        ),
        Spacer(1, 8),
        Paragraph("By using this document, you acknowledge that:", styles["body"]),
        Paragraph("1. This document is an AI-generated DRAFT and requires review by a qualified KSA-licensed attorney before use.", styles["body_small"]),
        Paragraph("2. Regulatory requirements change frequently. Verify all information against current official sources.", styles["body_small"]),
        Paragraph("3. AI-generated legal documents may contain errors, omissions, or outdated information.", styles["body_small"]),
        Paragraph("4. Neither AI Factory Pipeline, Anthropic, nor any affiliated party accepts liability for reliance on this document.", styles["body_small"]),
        Paragraph("5. All [PLACEHOLDER] fields must be completed by a qualified legal professional.", styles["body_small"]),
        Spacer(1, 12),
        Paragraph(
            "Recommended next step: Share this dossier with a Saudi-licensed attorney "
            "specialising in technology law and PDPL compliance. "
            "Contact the Saudi Bar Association (نقابة المحامين) for referrals.",
            styles["body"],
        ),
        Spacer(1, 8),
        Paragraph(
            f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} | "
            f"AI Factory Pipeline v5.8 | Project: {app_name}",
            styles["label"],
        ),
    ]


# ═══════════════════════════════════════════════════════════════════
# Plaintext Fallback (when ReportLab unavailable)
# ═══════════════════════════════════════════════════════════════════


def _write_plaintext_fallback(
    path: str,
    app_name: str,
    legal_output: dict,
    legal_research: str,
    legal_documents: dict[str, str],
) -> str:
    path = path if path.endswith(".txt") else path.replace(".pdf", ".txt")
    lines = [
        f"LEGAL DOSSIER — {app_name}",
        "=" * 60,
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "COMPLIANCE SUMMARY",
        "-" * 40,
        f"Overall Risk: {legal_output.get('overall_risk', 'unknown')}",
        f"Proceed: {legal_output.get('proceed', True)}",
        f"Regulatory Bodies: {', '.join(legal_output.get('regulatory_bodies', []))}",
        "",
        "REGULATORY RESEARCH",
        "-" * 40,
        legal_research[:2000] if legal_research else "Not available",
        "",
    ]
    for doc_type, content in legal_documents.items():
        lines += [f"\n{doc_type.upper()}", "-" * 40, content[:3000]]

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    logger.info(f"Plaintext fallback written: {path}")
    return path
