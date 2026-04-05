"""
AI Factory Pipeline v5.6 — Setup Wizard

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

Spec Authority: v5.6 §7.1.2, §7.1.3
"""

from __future__ import annotations

import logging
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
    send_message,   # Callable[str] → sends Telegram message to operator
) -> dict[str, Any]:
    """Run the 5-step setup wizard for an operator.

    Spec: §7.1.2

    Args:
        operator_id: Telegram user ID string.
        send_message: Async callable that sends a message to the operator.
                      Signature: async def send_message(text: str) -> None

    Returns:
        {step_key: {"stored": bool, "verified": bool, "detail": str}}
    """
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

    verifier = _VERIFIERS.get(verifier_name)
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
