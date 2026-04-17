"""
AI Factory Pipeline v5.8.12 — Tests for Issue 18: Credential Registry.
"""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from factory.core.credentials import (
    CREDENTIAL_REGISTRY,
    CredentialCheckResult,
    CredentialSeverity,
    check_credentials,
    format_credential_error,
    get_missing_critical,
)
from factory.core.halt import HaltCode
from factory.core.state import PipelineState, Stage


# ── Helpers ──────────────────────────────────────────────────────────────────

def _all_env_vars() -> dict[str, str]:
    """Return a dict with every env var in the registry set to a dummy value."""
    env: dict[str, str] = {}
    for spec in CREDENTIAL_REGISTRY:
        for var in spec.env_vars:
            env[var] = f"dummy_{var}"
    return env


# ── Tests ─────────────────────────────────────────────────────────────────────


class TestCheckCredentials:
    def test_check_credentials_all_present(self):
        """When all env vars are set, no CRITICAL credentials are missing."""
        with patch.dict(os.environ, _all_env_vars(), clear=False):
            results = check_credentials()
        missing = get_missing_critical(results)
        assert missing == [], f"Expected no missing CRITICAL, got: {[r.service_id for r in missing]}"

    def test_check_credentials_missing_telegram(self):
        """Unsetting TELEGRAM_BOT_TOKEN surfaces as a missing CRITICAL credential."""
        env = _all_env_vars()
        # Remove telegram token entirely
        env.pop("TELEGRAM_BOT_TOKEN", None)

        with patch.dict(os.environ, env, clear=False):
            # Also unset from the real environment for this test
            saved = os.environ.pop("TELEGRAM_BOT_TOKEN", None)
            try:
                results = check_credentials()
                missing = get_missing_critical(results)
            finally:
                if saved is not None:
                    os.environ["TELEGRAM_BOT_TOKEN"] = saved

        service_ids = [r.service_id for r in missing]
        assert "telegram" in service_ids, f"Expected telegram in missing, got: {service_ids}"

    def test_ai_cascade_logic(self):
        """If Anthropic is absent but Google AI is present, google_ai is NOT flagged as missing."""
        env = _all_env_vars()
        # Remove anthropic, keep google_ai present
        env.pop("ANTHROPIC_API_KEY", None)
        env["GOOGLE_AI_API_KEY"] = "dummy_google_key"

        saved_anthropic = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            with patch.dict(os.environ, env, clear=False):
                cred_results = check_credentials()
                _missing_critical = get_missing_critical(cred_results)
                _ai_creds_absent = not any(
                    r.present for r in cred_results if r.service_id in ("anthropic", "google_ai")
                )
                _real_missing = [
                    r for r in _missing_critical
                    if r.service_id != "google_ai" or _ai_creds_absent
                ]
        finally:
            if saved_anthropic is not None:
                os.environ["ANTHROPIC_API_KEY"] = saved_anthropic

        service_ids = [r.service_id for r in _real_missing]
        assert "google_ai" not in service_ids, (
            f"google_ai should NOT be in real_missing when anthropic cascades to it. Got: {service_ids}"
        )

    def test_both_ai_missing_is_critical(self):
        """When both Anthropic and Google AI are missing, google_ai IS flagged."""
        saved_anthropic = os.environ.pop("ANTHROPIC_API_KEY", None)
        saved_google = os.environ.pop("GOOGLE_AI_API_KEY", None)
        saved_gemini = os.environ.pop("GEMINI_API_KEY", None)
        try:
            cred_results = check_credentials()
            _missing_critical = get_missing_critical(cred_results)
            _ai_creds_absent = not any(
                r.present for r in cred_results if r.service_id in ("anthropic", "google_ai")
            )
            _real_missing = [
                r for r in _missing_critical
                if r.service_id != "google_ai" or _ai_creds_absent
            ]
        finally:
            if saved_anthropic is not None:
                os.environ["ANTHROPIC_API_KEY"] = saved_anthropic
            if saved_google is not None:
                os.environ["GOOGLE_AI_API_KEY"] = saved_google
            if saved_gemini is not None:
                os.environ["GEMINI_API_KEY"] = saved_gemini

        service_ids = [r.service_id for r in _real_missing]
        assert "google_ai" in service_ids, (
            f"google_ai SHOULD be in real_missing when both AI providers are absent. Got: {service_ids}"
        )

    def test_format_credential_error_nonempty(self):
        """format_credential_error output contains service_id, env var name, and fix step."""
        fake_missing = [
            CredentialCheckResult(
                service_id="myservice",
                severity=CredentialSeverity.CRITICAL,
                present=False,
                missing_vars=["MY_SERVICE_KEY"],
                free_alternative=None,
                fix_steps=["Go to https://example.com and get a key"],
            )
        ]
        output = format_credential_error(fake_missing)
        assert "MYSERVICE" in output
        assert "MY_SERVICE_KEY" in output
        assert "https://example.com" in output


class TestRunPipelineHaltsOnMissingCredential:
    @pytest.mark.asyncio
    async def test_run_pipeline_halts_on_missing_critical(self, fresh_state):
        """run_pipeline halts with CREDENTIAL_MISSING when check_credentials returns a missing CRITICAL."""
        fake_missing = [
            CredentialCheckResult(
                service_id="telegram",
                severity=CredentialSeverity.CRITICAL,
                present=False,
                missing_vars=["TELEGRAM_BOT_TOKEN"],
                free_alternative=None,
                fix_steps=["Create a bot via @BotFather on Telegram"],
            )
        ]
        # All results: the one above + the others marked present
        fake_all_results = fake_missing + [
            CredentialCheckResult(
                service_id="google_ai",
                severity=CredentialSeverity.CRITICAL,
                present=True,
                missing_vars=[],
                free_alternative=None,
                fix_steps=[],
            )
        ]

        # Override SKIP_CREDENTIAL_PREFLIGHT so the pre-flight actually runs,
        # then mock the credential functions so we control what they return.
        with patch.dict(os.environ, {"SKIP_CREDENTIAL_PREFLIGHT": "false"}, clear=False), \
             patch(
                 "factory.core.credentials.check_credentials",
                 return_value=fake_all_results,
             ), patch(
                 "factory.core.credentials.get_missing_critical",
                 return_value=fake_missing,
             ), patch(
                 "factory.core.credentials.format_credential_error",
                 return_value="Missing: TELEGRAM_BOT_TOKEN",
             ):
            from factory.orchestrator import run_pipeline
            result = await run_pipeline(fresh_state)

        assert result.current_stage == Stage.HALTED
        struct = result.project_metadata.get("halt_reason_struct", {})
        assert struct.get("code") == HaltCode.CREDENTIAL_MISSING.value
