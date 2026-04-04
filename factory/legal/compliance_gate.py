"""
AI Factory Pipeline v5.6 — Store Compliance Preflight Gate

Implements:
  - §7.6.0b ComplianceGateResult (Pydantic model)
  - §7.6.0b STRICT_STORE_COMPLIANCE flag
  - Store preflight check (iOS App Store + Google Play)
  - StorePolicyEvent integration (Mother Memory)

ADVISORY ONLY: All preflight checks surface risks.
They do NOT guarantee Apple/Google approval.

Spec Authority: v5.6 §7.6.0b, FIX-09
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from pydantic import BaseModel, Field

from factory.core.state import AIRole, PipelineState
from factory.core.roles import call_ai

logger = logging.getLogger("factory.legal.compliance_gate")


# ═══════════════════════════════════════════════════════════════════
# §7.6.0b Configuration
# ═══════════════════════════════════════════════════════════════════

STRICT_STORE_COMPLIANCE = os.getenv(
    "STRICT_STORE_COMPLIANCE", "false"
).lower() == "true"


# ═══════════════════════════════════════════════════════════════════
# §7.6.0b ComplianceGateResult
# ═══════════════════════════════════════════════════════════════════


class ComplianceGateResult(BaseModel):
    """Structured output from S1 App Store compliance preflight.

    Spec: §7.6.0b [H2]
    """
    platform: str                                   # "ios" | "android" | "both"
    overall_pass: bool                              # True if no blockers found
    blockers: list[dict] = Field(default_factory=list)
    warnings: list[dict] = Field(default_factory=list)
    guidelines_version: str = ""
    confidence: float = 0.0                         # 0.0–1.0
    source_ids: list[str] = Field(default_factory=list)

    def should_block(self) -> bool:
        """Block only if STRICT mode AND blockers AND confidence > 0.7.

        Spec: §7.6.0b
        """
        return (
            STRICT_STORE_COMPLIANCE
            and len(self.blockers) > 0
            and self.confidence > 0.7
        )


# ═══════════════════════════════════════════════════════════════════
# Store Preflight Check
# ═══════════════════════════════════════════════════════════════════


async def run_store_preflight(
    state: PipelineState,
    requirements: dict,
    platforms: list[str],
) -> list[ComplianceGateResult]:
    """Run App Store / Play Store compliance preflight.

    Spec: §7.6.0b

    Uses Scout to research current store guidelines.
    Returns ComplianceGateResult per platform.
    All results are ADVISORY.
    """
    results: list[ComplianceGateResult] = []

    for platform in platforms:
        if platform not in ("ios", "android", "web"):
            continue
        if platform == "web":
            continue  # No store compliance for web

        result = await _check_platform(state, requirements, platform)
        results.append(result)

    return results


async def _check_platform(
    state: PipelineState,
    requirements: dict,
    platform: str,
) -> ComplianceGateResult:
    """Check compliance for a single platform.

    Spec: §7.6.0b
    """
    store_name = (
        "Apple App Store" if platform == "ios" else "Google Play Store"
    )
    category = requirements.get("app_category", "general")
    features = requirements.get("features_must", [])

    # ── Query Mother Memory for past rejections ──
    past_events = await _query_store_events(platform, category)

    past_context = ""
    if past_events:
        past_context = (
            f"\n\nPast rejection history ({len(past_events)} events):\n"
            + "\n".join(
                f"- {e.get('guideline', 'unknown')}: {e.get('reason', '')}"
                for e in past_events[:5]
            )
        )

    # ── Scout researches current guidelines ──
    research = await call_ai(
        role=AIRole.SCOUT,
        prompt=(
            f"Check {store_name} compliance risks for a {category} app "
            f"with features: {features[:10]}.\n"
            f"Focus on: content policy, payment rules, data collection, "
            f"KSA-specific restrictions.\n"
            f"Return JSON: {{\"blockers\": [{{\"guideline\": ..., "
            f"\"section\": ..., \"risk\": ..., \"suggestion\": ...}}], "
            f"\"warnings\": [...], \"guidelines_version\": \"...\", "
            f"\"confidence\": 0.0-1.0}}"
            f"{past_context}"
        ),
        state=state,
        action="general",
    )

    # Parse response
    return _parse_compliance_result(research, platform)


def _parse_compliance_result(
    raw: str, platform: str,
) -> ComplianceGateResult:
    """Parse Scout's compliance research into structured result."""
    import json

    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(raw[start:end])
            blockers = data.get("blockers", [])
            warnings = data.get("warnings", [])
            return ComplianceGateResult(
                platform=platform,
                overall_pass=len(blockers) == 0,
                blockers=blockers,
                warnings=warnings,
                guidelines_version=data.get("guidelines_version", ""),
                confidence=data.get("confidence", 0.5),
            )
    except (json.JSONDecodeError, ValueError):
        pass

    # Parse failed — return pass with low confidence
    return ComplianceGateResult(
        platform=platform,
        overall_pass=True,
        confidence=0.3,
        warnings=[{
            "guideline": "parse_error",
            "risk": "Could not parse compliance check results",
            "suggestion": "Manual review recommended",
        }],
    )


async def _query_store_events(
    platform: str, category: str,
) -> list[dict]:
    """Query StorePolicyEvent nodes from Mother Memory.

    Spec: §7.6.0b [H2/FIX-09]
    """
    try:
        from factory.integrations.neo4j import get_neo4j
        neo4j = get_neo4j()
        events = await neo4j.find_nodes("StorePolicyEvent", {
            "platform": platform,
        })
        return events[:10]
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════════
# Store Policy Event Recording
# ═══════════════════════════════════════════════════════════════════


async def record_store_event(
    project_id: str,
    platform: str,
    event_type: str,
    guideline: str = "",
    reason: str = "",
    details: dict = None,
) -> Optional[str]:
    """Record a store policy event in Mother Memory.

    Spec: §2.10.1 StorePolicyEvent node type

    Used to track past rejections for cross-project learning.
    """
    try:
        from factory.integrations.neo4j import get_neo4j
        from datetime import datetime, timezone
        neo4j = get_neo4j()

        props = {
            "project_id": project_id,
            "platform": platform,
            "event_type": event_type,
            "guideline": guideline,
            "reason": reason[:500],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if details:
            props["details"] = str(details)[:1000]
        node = await neo4j.create_node("StorePolicyEvent", props)
        return node.get("id") if isinstance(node, dict) else None
    except Exception as e:
        logger.error(f"Failed to record store event: {e}")
        return None