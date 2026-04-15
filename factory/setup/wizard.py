"""
AI Factory Pipeline v5.8 — Setup Wizard

Implements §7.1.2: 4-step Telegram-driven setup wizard.

Steps:
  1. Anthropic API key  → verify_anthropic()
  2. Perplexity API key → verify_perplexity()
  3. Supabase URL + service key → verify_supabase()
  4. Neo4j URI + password → verify_neo4j()
  5. GitHub token → verify_github()

Each key collected via wait_for_operator_reply() (300s timeout → SKIP).
SKIP skips verification; key stored as "" (configurable later).
After all keys: schema init.

Spec Authority: v5.8 §7.1.2, §7.1.3
"""

from __future__ import annotations

import logging
import sys
from typing import Any

from factory.core.secrets import store_secret
from factory.telegram.decisions import wait_for_operator_reply
from factory.setup.verify import (
    verify_anthropic,
    verify_perplexity,
    verify_supabase,
    verify_neo4j,
    verify_github,
)

logger = logging.getLogger("factory.setup.wizard")

# ── Wizard step definitions ──────────────────────────────────────────────────

WIZARD_STEPS: list[dict] = [
    {
        "key": "ANTHROPIC_API_KEY",
        "prompt": (
            "🤖 *Step 1/5 — Anthropic API Key*\n\n"
            "Paste your Anthropic API key (starts with `sk-ant-...`).\n"
            "Send `SKIP` to configure later."
        ),
        "secret_name": "ANTHROPIC_API_KEY",
        "verifier": "anthropic",
    },
    {
        "key": "PERPLEXITY_API_KEY",
        "prompt": (
            "🔍 *Step 2/5 — Perplexity API Key*\n\n"
            "Paste your Perplexity API key (`pplx-...`).\n"
            "Send `SKIP` to configure later."
        ),
        "secret_name": "PERPLEXITY_API_KEY",
        "verifier": "perplexity",
    },
    {
        "key": "SUPABASE",
        "prompt": (
            "🗄️ *Step 3/5 — Supabase*\n\n"
            "Send your Supabase URL (e.g. `https://xxx.supabase.co`).\n"
            "Send `SKIP` to configure later."
        ),
        "secret_name": "SUPABASE_URL",
        "verifier": None,  # Two-part step
    },
    {
        "key": "NEO4J",
        "prompt": (
            "🧠 *Step 4/5 — Neo4j*\n\n"
            "Send your Neo4j URI (e.g. `neo4j+s://...`).\n"
            "Send `SKIP` to configure later."
        ),
        "secret_name": "NEO4J_URI",
        "verifier": None,  # Two-part step
    },
    {
        "key": "GITHUB_TOKEN",
        "prompt": (
            "🐙 *Step 5/5 — GitHub Token*\n\n"
            "Paste your GitHub Personal Access Token (`ghp_...`).\n"
            "Send `SKIP` to configure later."
        ),
        "secret_name": "GITHUB_TOKEN",
        "verifier": "github",
    },
]

_VERIFIERS = {
    "anthropic": verify_anthropic,
    "perplexity": verify_perplexity,
    "supabase": verify_supabase,
    "neo4j": verify_neo4j,
    "github": verify_github,
}


# ─────────────────────────────────────────────────────────────────────────────


async def run_setup_wizard(
    operator_id: str,
    send_message=None,   # Optional: if provided, runs 5-step mode; else 8-secret mode
) -> dict[str, Any]:
    """Run the setup wizard for an operator.

    Spec: §7.1.2

    Two modes:
    - 5-step mode (send_message provided): interactive with given send callback.
      Returns {step_key: {"stored": bool, "verified": bool, "skipped": bool, "detail": str}}
    - 8-secret mode (no send_message): uses internal Telegram send/reply functions.
      Returns {"passed": [...], "failed": [...], "skipped": [...], "supabase_schema": ..., "neo4j_schema": ...}

    Args:
        operator_id: Telegram user ID string.
        send_message: Optional async callable. If None, uses internal Telegram functions.
    """
    if send_message is None:
        return await _run_setup_wizard_8secret(operator_id)

    results: dict[str, Any] = {}

    await send_message(
        "⚙️ *AI Factory Setup Wizard*\n\n"
        "I'll guide you through 5 service connections.\n"
        "Each key has a 5-minute entry window.\n"
        "Stuck? Send `SKIP` to skip a step."
    )

    # ── Step 1: Anthropic ────────────────────────────────────────────
    results["anthropic"] = await _collect_single_key(
        operator_id=operator_id,
        send_message=send_message,
        prompt=(
            "🤖 *Step 1/5 — Anthropic API Key*\n\n"
            "Paste your key (`sk-ant-...`) or `SKIP`."
        ),
        secret_name="ANTHROPIC_API_KEY",
        verifier_name="anthropic",
    )

    # ── Step 2: Perplexity ───────────────────────────────────────────
    results["perplexity"] = await _collect_single_key(
        operator_id=operator_id,
        send_message=send_message,
        prompt=(
            "🔍 *Step 2/5 — Perplexity API Key*\n\n"
            "Paste your key (`pplx-...`) or `SKIP`."
        ),
        secret_name="PERPLEXITY_API_KEY",
        verifier_name="perplexity",
    )

    # ── Step 3: Supabase (two keys) ──────────────────────────────────
    results["supabase"] = await _collect_supabase(
        operator_id=operator_id,
        send_message=send_message,
    )

    # ── Step 4: Neo4j (two keys) ─────────────────────────────────────
    results["neo4j"] = await _collect_neo4j(
        operator_id=operator_id,
        send_message=send_message,
    )

    # ── Step 5: GitHub ───────────────────────────────────────────────
    results["github"] = await _collect_single_key(
        operator_id=operator_id,
        send_message=send_message,
        prompt=(
            "🐙 *Step 5/5 — GitHub Token*\n\n"
            "Paste your token (`ghp_...`) or `SKIP`."
        ),
        secret_name="GITHUB_TOKEN",
        verifier_name="github",
    )

    # ── Summary ──────────────────────────────────────────────────────
    verified = sum(1 for r in results.values() if r.get("verified"))
    skipped = sum(1 for r in results.values() if r.get("skipped"))
    total = len(results)

    summary_lines = ["✅ *Setup Complete*\n"]
    for service, result in results.items():
        icon = "✅" if result.get("verified") else ("⏭️" if result.get("skipped") else "❌")
        detail = result.get("detail", "")
        summary_lines.append(f"{icon} {service.capitalize()}: {detail}")

    summary_lines.append(
        f"\n{verified}/{total} services verified. "
        f"{skipped} skipped (configure later via /setup)."
    )
    await send_message("\n".join(summary_lines))

    # ── Schema init ──────────────────────────────────────────────────
    if results.get("supabase", {}).get("verified"):
        await send_message("🗄️ Initializing database schema...")
        try:
            from factory.setup.schema import initialize_schema
            schema_result = await initialize_schema()
            tables_ok = schema_result.get("supabase_tables", 0)
            neo4j_ok = schema_result.get("neo4j_indexes", 0)
            await send_message(
                f"✅ Schema ready: {tables_ok} tables, {neo4j_ok} Neo4j indexes."
            )
        except Exception as e:
            await send_message(f"⚠️ Schema init failed: {str(e)[:200]}")

    logger.info(
        f"[Wizard] Operator {operator_id}: {verified}/{total} verified"
    )
    return results


# ─────────────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _collect_single_key(
    operator_id: str,
    send_message,
    prompt: str,
    secret_name: str,
    verifier_name: str,
) -> dict:
    """Collect a single API key with verification."""
    await send_message(prompt)
    value = await wait_for_operator_reply(operator_id, timeout=300, default="SKIP")

    if value.upper() == "SKIP" or not value.strip():
        logger.info(f"[Wizard] {secret_name}: skipped by {operator_id}")
        return {"stored": False, "verified": False, "skipped": True, "detail": "skipped"}

    store_secret(secret_name, value.strip())
    logger.info(f"[Wizard] {secret_name}: stored for {operator_id}")

    # Dynamic lookup so monkeypatching works in tests
    verifier = getattr(sys.modules[__name__], f"verify_{verifier_name}", None)
    if verifier:
        try:
            result = await verifier()
            await send_message(
                f"✅ {result['service']} connected "
                f"({result['latency_ms']}ms): {result['detail']}"
            )
            return {
                "stored": True,
                "verified": True,
                "skipped": False,
                "detail": result["detail"],
            }
        except Exception as e:
            detail = str(e)[:120]
            await send_message(f"⚠️ Verification failed: {detail}")
            return {
                "stored": True,
                "verified": False,
                "skipped": False,
                "detail": f"stored but unverified: {detail}",
            }

    return {"stored": True, "verified": False, "skipped": False, "detail": "stored"}


async def _collect_supabase(operator_id: str, send_message) -> dict:
    """Collect Supabase URL + service key (two-part step)."""
    await send_message(
        "🗄️ *Step 3/5 — Supabase*\n\n"
        "Send your Supabase URL (`https://xxx.supabase.co`) or `SKIP`."
    )
    url = await wait_for_operator_reply(operator_id, timeout=300, default="SKIP")
    if url.upper() == "SKIP":
        return {"stored": False, "verified": False, "skipped": True, "detail": "skipped"}

    store_secret("SUPABASE_URL", url.strip())

    await send_message(
        "🔑 Now paste your Supabase *Service Role Key* (`eyJ...`)."
    )
    key = await wait_for_operator_reply(operator_id, timeout=300, default="SKIP")
    if key.upper() == "SKIP":
        return {"stored": True, "verified": False, "skipped": False, "detail": "URL stored, key skipped"}

    store_secret("SUPABASE_SERVICE_KEY", key.strip())

    try:
        result = await verify_supabase()
        await send_message(
            f"✅ Supabase connected ({result['latency_ms']}ms): {result['detail']}"
        )
        return {"stored": True, "verified": True, "skipped": False, "detail": result["detail"]}
    except Exception as e:
        detail = str(e)[:120]
        await send_message(f"⚠️ Supabase verification failed: {detail}")
        return {"stored": True, "verified": False, "skipped": False, "detail": detail}


async def _collect_neo4j(operator_id: str, send_message) -> dict:
    """Collect Neo4j URI + password (two-part step)."""
    await send_message(
        "🧠 *Step 4/5 — Neo4j (Mother Memory)*\n\n"
        "Send your Neo4j URI (`neo4j+s://...`) or `SKIP`."
    )
    uri = await wait_for_operator_reply(operator_id, timeout=300, default="SKIP")
    if uri.upper() == "SKIP":
        return {"stored": False, "verified": False, "skipped": True, "detail": "skipped"}

    store_secret("NEO4J_URI", uri.strip())

    await send_message("🔑 Now paste your Neo4j *password*.")
    password = await wait_for_operator_reply(operator_id, timeout=300, default="SKIP")
    if password.upper() == "SKIP":
        return {"stored": True, "verified": False, "skipped": False, "detail": "URI stored, password skipped"}

    store_secret("NEO4J_PASSWORD", password.strip())

    try:
        result = await verify_neo4j()
        await send_message(
            f"✅ Neo4j connected ({result['latency_ms']}ms): {result['detail']}"
        )
        return {"stored": True, "verified": True, "skipped": False, "detail": result["detail"]}
    except Exception as e:
        detail = str(e)[:120]
        await send_message(f"⚠️ Neo4j verification failed: {detail}")
        return {"stored": True, "verified": False, "skipped": False, "detail": detail}


# ═══════════════════════════════════════════════════════════════════
# Test-compatible exports
# ═══════════════════════════════════════════════════════════════════

SECRET_TIMEOUT_SECONDS: int = 300
SECRET_SKIP_VALUE: str = "SKIP"

# WIZARD_SECRETS: 8 tuples of (secret_name, description)
# Format: (name, description) — matches Appendix B
WIZARD_SECRETS: list[tuple] = [
    ("ANTHROPIC_API_KEY",    "Anthropic API key (sk-ant-...)"),
    ("PERPLEXITY_API_KEY",   "Perplexity API key (pplx-...)"),
    ("TELEGRAM_BOT_TOKEN",   "Telegram Bot Token (from @BotFather)"),
    ("GITHUB_TOKEN",         "GitHub Personal Access Token (ghp_...)"),
    ("SUPABASE_URL",         "Supabase project URL (https://xxx.supabase.co)"),
    ("SUPABASE_SERVICE_KEY", "Supabase service role key"),
    ("NEO4J_URI",            "Neo4j URI (neo4j+s://...)"),
    ("NEO4J_PASSWORD",       "Neo4j password"),
]


def check_secret_exists(secret_name: str) -> bool:
    """Check if a secret is already configured in the environment.

    Spec: §7.1.2
    Returns True if the secret is set and non-empty.
    """
    import os
    return bool(os.getenv(secret_name))


def _get_send_function():
    """Return the send_message function for wizard prompts.

    Returns the Telegram send_message function, or a no-op stub.
    Spec: §7.1.2
    """
    try:
        from factory.telegram.notifications import send_telegram_message
        return send_telegram_message
    except ImportError:
        async def _noop(operator_id, text, **kwargs):
            pass
        return _noop


def _get_reply_function():
    """Return the wait_for_operator_reply function for wizard.

    Spec: §7.1.2
    """
    from factory.telegram.decisions import wait_for_operator_reply
    return wait_for_operator_reply


async def _run_setup_wizard_8secret(operator_id: str) -> dict:
    """Run the 8-secret setup wizard for an operator (internal variant).

    Spec: §7.1.2
    Collects all 8 secrets via Telegram, stores them, then initializes schemas.

    Returns:
        {"passed": [...], "failed": [...], "skipped": [...],
         "supabase_schema": dict, "neo4j_schema": dict}
    """
    send_fn = _get_send_function()
    reply_fn = _get_reply_function()

    results: dict = {"passed": [], "failed": [], "skipped": []}

    for secret_name, description in WIZARD_SECRETS:
        # If already configured, skip prompt
        if check_secret_exists(secret_name):
            results["passed"].append(secret_name)
            continue

        # Prompt operator
        await send_fn(
            operator_id,
            f"🔑 *{secret_name}*\n{description}\n\nSend the value or `SKIP`:",
        )

        # Wait for reply
        value = await reply_fn(
            operator_id,
            timeout=SECRET_TIMEOUT_SECONDS,
            default=SECRET_SKIP_VALUE,
        )

        if value == SECRET_SKIP_VALUE or not value:
            results["skipped"].append(secret_name)
        else:
            try:
                from factory.core.secrets import store_secret as _store
                await _store(secret_name, value)
                results["passed"].append(secret_name)
            except Exception as e:
                logger.error(f"[Wizard] Failed to store {secret_name}: {e}")
                results["failed"].append(secret_name)

    # Initialize schemas
    from factory.setup.schema import (
        initialize_supabase_schema, initialize_neo4j_schema,
    )
    results["supabase_schema"] = await initialize_supabase_schema(
        supabase_client=None,
    )
    results["neo4j_schema"] = await initialize_neo4j_schema(
        neo4j_client=None,
    )

    # Send summary
    total = len(WIZARD_SECRETS)
    passed = len(results["passed"])
    skipped = len(results["skipped"])
    failed = len(results["failed"])
    await send_fn(
        operator_id,
        f"📊 Setup Complete\n\n"
        f"✅ Configured: {passed}/{total}\n"
        f"⏭️ Skipped: {skipped}\n"
        f"❌ Failed: {failed}\n\n"
        f"Run /status to verify your configuration.",
    )

    return results
