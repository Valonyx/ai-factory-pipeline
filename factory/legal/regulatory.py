"""
AI Factory Pipeline v5.8 — Regulatory Body Resolution

Implements:
  - §2.8 REGULATORY_BODY_MAPPING (alias normalization)
  - KSA regulatory categories per app type
  - PDPL (Personal Data Protection Law) requirements
  - Data residency rules

Spec Authority: v5.6 §2.8
"""

from __future__ import annotations

import os
from typing import Optional


# ═══════════════════════════════════════════════════════════════════
# §2.8 Regulatory Body Mapping
# ═══════════════════════════════════════════════════════════════════

REGULATORY_BODY_MAPPING: dict[str, str] = {
    # CST (formerly CITC)
    "CITC": "CST",
    "COMMUNICATIONS AND INFORMATION TECHNOLOGY COMMISSION": "CST",
    "COMMUNICATIONS, SPACE & TECHNOLOGY COMMISSION": "CST",
    "CST": "CST",
    # SAMA (Saudi Central Bank)
    "SAMA": "SAMA",
    "SAUDI ARABIAN MONETARY AUTHORITY": "SAMA",
    "SAUDI CENTRAL BANK": "SAMA",
    # NDMO
    "NDMO": "NDMO",
    "NATIONAL DATA MANAGEMENT OFFICE": "NDMO",
    # NCA
    "NCA": "NCA",
    "NATIONAL CYBERSECURITY AUTHORITY": "NCA",
    # SDAIA
    "SDAIA": "SDAIA",
    "SAUDI DATA AND AI AUTHORITY": "SDAIA",
    "SAUDI DATA & AI AUTHORITY": "SDAIA",
    # Ministry of Commerce
    "MINISTRY OF COMMERCE": "MINISTRY_OF_COMMERCE",
    "MOC": "MINISTRY_OF_COMMERCE",
    "MINISTRY_OF_COMMERCE": "MINISTRY_OF_COMMERCE",
}


def resolve_regulatory_body(name: str) -> str:
    """Normalize regulatory body name to canonical identifier.

    Spec: §2.8

    Examples:
        "CITC" → "CST"
        "Saudi Central Bank" → "SAMA"
        "MOC" → "MINISTRY_OF_COMMERCE"
    """
    normalized = name.strip().upper()
    return REGULATORY_BODY_MAPPING.get(normalized, normalized)


# ═══════════════════════════════════════════════════════════════════
# KSA Regulatory Categories
# ═══════════════════════════════════════════════════════════════════

# Which regulators apply to which app categories
CATEGORY_REGULATORS: dict[str, list[str]] = {
    "e-commerce": ["MINISTRY_OF_COMMERCE", "CST"],
    "finance": ["SAMA", "CST", "NDMO"],
    "fintech": ["SAMA", "CST", "NDMO"],
    "health": ["MINISTRY_OF_COMMERCE", "NDMO", "NCA"],
    "education": ["MINISTRY_OF_COMMERCE"],
    "delivery": ["MINISTRY_OF_COMMERCE", "CST"],
    "social": ["CST", "NDMO"],
    "games": ["CST"],
    "productivity": ["CST"],
    "utility": ["CST"],
    "other": ["CST"],
}


def get_regulators_for_category(category: str) -> list[str]:
    """Get applicable regulatory bodies for an app category."""
    return CATEGORY_REGULATORS.get(
        category.lower(), CATEGORY_REGULATORS["other"]
    )


# ═══════════════════════════════════════════════════════════════════
# PDPL Requirements
# ═══════════════════════════════════════════════════════════════════

PDPL_REQUIREMENTS = {
    "consent_required": True,
    "data_residency": "KSA",
    "data_transfer_rules": (
        "Personal data may only be transferred outside KSA with "
        "explicit consent and adequate safeguards per PDPL Article 29."
    ),
    "retention_policy": (
        "Personal data must be deleted when no longer necessary "
        "for the purpose of collection per PDPL Article 18."
    ),
    "subject_rights": [
        "right_to_access",
        "right_to_correction",
        "right_to_deletion",
        "right_to_portability",
        "right_to_object",
        "right_to_withdraw_consent",
    ],
    "breach_notification_hours": 72,
    "dpo_required_threshold": "large_scale_processing",
}


# ═══════════════════════════════════════════════════════════════════
# Data Residency
# ═══════════════════════════════════════════════════════════════════

ALLOWED_DATA_REGIONS = [
    "me-central1",      # GCP Dammam
    "me-central2",      # GCP Doha (Gulf region)
    "me-south1",        # GCP Tel Aviv fallback
    "me-west1",         # GCP Milan fallback
]

PRIMARY_DATA_REGION = "me-central1"  # GCP Dammam — KSA resident


def is_ksa_compliant_region(region: str) -> bool:
    """Check if a cloud region is compliant with KSA data residency."""
    return region in ALLOWED_DATA_REGIONS


# ═══════════════════════════════════════════════════════════════════
# CST Deployment Restrictions
# ═══════════════════════════════════════════════════════════════════

# Configurable deployment time window (AST = UTC+3)
DEPLOY_WINDOW_START_HOUR = int(os.getenv("DEPLOY_WINDOW_START", "6"))
DEPLOY_WINDOW_END_HOUR = int(os.getenv("DEPLOY_WINDOW_END", "23"))


def is_within_deploy_window(hour_ast) -> bool:
    """Check if current AST hour is within allowed deploy window.

    Spec: §2.7.3 — cst_time_of_day_restrictions
    Default: 06:00–23:00 AST

    Args:
        hour_ast: Either an int (hour in 0-23) or a datetime object.
                  If datetime, the hour is extracted directly.
    """
    import datetime as _dt
    if isinstance(hour_ast, (_dt.datetime,)):
        hour = hour_ast.hour
    else:
        hour = int(hour_ast)
    return DEPLOY_WINDOW_START_HOUR <= hour < DEPLOY_WINDOW_END_HOUR


# ═══════════════════════════════════════════════════════════════════
# Prohibited SDKs
# ═══════════════════════════════════════════════════════════════════

PROHIBITED_SDKS = [
    "huawei-analytics",      # Sanctioned entity concerns
    "kaspersky-sdk",         # Sanctioned entity concerns
    "tiktok-sdk",            # Data sovereignty concerns
    "telegram-unofficial",   # Unofficial forks
    "facebook-analytics",    # Data sovereignty concerns
]


def check_prohibited_sdks(dependencies: list[str]) -> list[str]:
    """Check dependency list for prohibited SDKs.

    Spec: §2.7.3 — no_prohibited_sdks
    Returns list of prohibited dependencies found.
    """
    found = []
    for dep in dependencies:
        dep_lower = dep.lower().strip()
        for prohibited in PROHIBITED_SDKS:
            if prohibited in dep_lower:
                found.append(dep)
    return found

# KSA timezone (§2.7.3 deploy window checks)
try:
    from zoneinfo import ZoneInfo
    KSA_TIMEZONE = ZoneInfo("Asia/Riyadh")
except Exception:
    import datetime as _dt
    KSA_TIMEZONE = _dt.timezone(_dt.timedelta(hours=3))  # UTC+3 fallback
