"""
AI Factory Pipeline v5.8.12 — Credential Registry + Pre-flight Gate
Issue 18: Every critical service has a defined scope, severity, and probe.
"""
from __future__ import annotations
import asyncio, logging, os
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Callable, Awaitable

logger = logging.getLogger("factory.core.credentials")

class CredentialSeverity(str, Enum):
    CRITICAL = "CRITICAL"    # pipeline cannot proceed without this
    DEGRADED = "DEGRADED"    # degrades quality but pipeline can continue
    OPTIONAL = "OPTIONAL"    # only required for specific optional features

@dataclass
class CredentialSpec:
    service_id: str
    scope: str                          # e.g. "ai/primary", "storage/db", "deploy/ios"
    env_vars: list[str]                 # any ONE of these is sufficient
    severity: CredentialSeverity
    free_alternative: Optional[str] = None  # human-readable: "Gemini free tier"
    fix_steps: list[str] = field(default_factory=list)
    # lightweight probe: returns True if credential is live (may be None = skip probe)
    probe: Optional[Callable[[], Awaitable[bool]]] = None

# ── Registry ──────────────────────────────────────────────────────
CREDENTIAL_REGISTRY: list[CredentialSpec] = [
    CredentialSpec(
        service_id="anthropic",
        scope="ai/primary",
        env_vars=["ANTHROPIC_API_KEY"],
        severity=CredentialSeverity.DEGRADED,   # cascade to Gemini if missing
        free_alternative="Google Gemini free tier (set GOOGLE_AI_API_KEY)",
        fix_steps=[
            "Get an API key at https://console.anthropic.com/",
            "Set ANTHROPIC_API_KEY=<key> in your .env file",
            "Or set GOOGLE_AI_API_KEY for the free Gemini fallback",
        ],
    ),
    CredentialSpec(
        service_id="google_ai",
        scope="ai/fallback",
        env_vars=["GOOGLE_AI_API_KEY", "GEMINI_API_KEY"],
        severity=CredentialSeverity.CRITICAL,   # needed if Anthropic missing
        free_alternative=None,
        fix_steps=[
            "Get a free API key at https://aistudio.google.com/",
            "Set GOOGLE_AI_API_KEY=<key> in your .env file",
        ],
    ),
    CredentialSpec(
        service_id="telegram",
        scope="bot/messaging",
        env_vars=["TELEGRAM_BOT_TOKEN"],
        severity=CredentialSeverity.CRITICAL,
        fix_steps=[
            "Create a bot via @BotFather on Telegram",
            "Set TELEGRAM_BOT_TOKEN=<token> in your .env file",
        ],
    ),
    CredentialSpec(
        service_id="supabase",
        scope="storage/db",
        env_vars=["SUPABASE_URL", "SUPABASE_SERVICE_KEY"],
        severity=CredentialSeverity.CRITICAL,
        fix_steps=[
            "Create a free project at https://supabase.com/",
            "Set SUPABASE_URL and SUPABASE_SERVICE_KEY in your .env file",
        ],
    ),
    CredentialSpec(
        service_id="github",
        scope="storage/code",
        env_vars=["GITHUB_TOKEN"],
        severity=CredentialSeverity.CRITICAL,
        fix_steps=[
            "Create a personal access token at https://github.com/settings/tokens",
            "Set GITHUB_TOKEN=<token> in your .env file",
        ],
    ),
    CredentialSpec(
        service_id="neo4j",
        scope="memory/graph",
        env_vars=["NEO4J_URI", "NEO4J_PASSWORD"],
        severity=CredentialSeverity.DEGRADED,
        free_alternative="In-memory fallback (no cross-session memory)",
        fix_steps=[
            "Create a free Aura instance at https://neo4j.com/cloud/aura/",
            "Set NEO4J_URI and NEO4J_PASSWORD in your .env file",
        ],
    ),
    CredentialSpec(
        service_id="firebase",
        scope="deploy/mobile",
        env_vars=["FIREBASE_SERVICE_ACCOUNT"],
        severity=CredentialSeverity.OPTIONAL,
        free_alternative="Deploy-less Telegram delivery (Issue 4)",
        fix_steps=[
            "Download service account JSON from Firebase Console",
            "Set FIREBASE_SERVICE_ACCOUNT=<base64-encoded JSON> in your .env file",
        ],
    ),
    CredentialSpec(
        service_id="apple",
        scope="deploy/ios",
        env_vars=["APPLE_ID", "APP_SPECIFIC_PASSWORD"],
        severity=CredentialSeverity.OPTIONAL,
        free_alternative="Deploy-less Telegram delivery (Issue 4)",
        fix_steps=[
            "Use an Apple Developer account",
            "Set APPLE_ID and APP_SPECIFIC_PASSWORD in your .env file",
        ],
    ),
]

def _has_any_env(env_vars: list[str]) -> bool:
    """Return True if at least one var is set and non-empty."""
    return any(os.environ.get(v, "").strip() for v in env_vars)

@dataclass
class CredentialCheckResult:
    service_id: str
    severity: CredentialSeverity
    present: bool
    missing_vars: list[str]
    free_alternative: Optional[str]
    fix_steps: list[str]

def check_credentials(
    scope_filter: Optional[str] = None,
) -> list[CredentialCheckResult]:
    """Check all registered credentials. Optionally filter by scope prefix."""
    results = []
    for spec in CREDENTIAL_REGISTRY:
        if scope_filter and not spec.scope.startswith(scope_filter):
            continue
        present = _has_any_env(spec.env_vars)
        results.append(CredentialCheckResult(
            service_id=spec.service_id,
            severity=spec.severity,
            present=present,
            missing_vars=[v for v in spec.env_vars if not os.environ.get(v, "").strip()] if not present else [],
            free_alternative=spec.free_alternative,
            fix_steps=spec.fix_steps,
        ))
    return results

def get_missing_critical(results: list[CredentialCheckResult]) -> list[CredentialCheckResult]:
    return [r for r in results if not r.present and r.severity == CredentialSeverity.CRITICAL]

def format_credential_error(missing: list[CredentialCheckResult]) -> str:
    lines = ["Missing required credentials:"]
    for r in missing:
        lines.append(f"\n* {r.service_id.upper()} ({r.severity.value})")
        lines.append(f"  Set any of: {', '.join(r.missing_vars)}")
        for step in r.fix_steps:
            lines.append(f"  -> {step}")
        if r.free_alternative:
            lines.append(f"  Free alternative: {r.free_alternative}")
    lines.append("\nFix the above then restart the bot.")
    return "\n".join(lines)
