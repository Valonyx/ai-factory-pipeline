"""
factory/core/dry_run.py — Central DRY_RUN gate

Phase 5 FIX-MOCK: DRY_RUN=true must never bypass production code paths.
Previously, 14+ files checked os.getenv("DRY_RUN") independently, making
it trivially easy for a misconfigured deployment to silently short-circuit
every stage (legal, build, verify, image gen, etc.).

The gate defined here allows DRY_RUN only when the process is demonstrably
running under a test runner or CI environment. In production (none of those
markers present), is_dry_run() always returns False, making DRY_RUN=true a
no-op.

Test-context markers checked (any one sufficient):
  PYTEST_CURRENT_TEST — pytest sets this automatically for every test
  CI                  — set by GitHub Actions, CircleCI, Jenkins, etc.
  TESTING             — explicit opt-in for non-pytest test harnesses
"""

from __future__ import annotations

import os

__all__ = ["is_dry_run", "is_mock_provider"]


def _in_test_context() -> bool:
    """Return True when the process is running under a known test/CI harness."""
    return bool(
        os.getenv("PYTEST_CURRENT_TEST")
        or os.getenv("CI")
        or os.getenv("TESTING", "").lower() in ("true", "1", "yes")
    )


def is_dry_run() -> bool:
    """Return True only when DRY_RUN is set AND we are in a test/CI context.

    In production (no PYTEST_CURRENT_TEST, CI, or TESTING marker):
      - Always returns False regardless of DRY_RUN env var value.
      - Logs a one-time warning if DRY_RUN=true is detected in production
        so operators know the flag has no effect and can clean up the env.

    In test/CI:
      - Behaves exactly as the previous scattered os.getenv("DRY_RUN") did.
    """
    raw = os.getenv("DRY_RUN", "").lower()
    requested = raw in ("true", "1", "yes")

    if not requested:
        return False

    if _in_test_context():
        return True

    # DRY_RUN=true but no test context — production guard triggered.
    _warn_once()
    return False


_warned = False


def _warn_once() -> None:
    global _warned
    if not _warned:
        import logging
        logging.getLogger("factory.core.dry_run").warning(
            "DRY_RUN=true detected in a non-test context — "
            "the flag is IGNORED in production to prevent silent stage bypass. "
            "Unset DRY_RUN or set CI=true / TESTING=true if this is intentional."
        )
        _warned = True


def is_mock_provider() -> bool:
    """Return True only when AI_PROVIDER=mock AND we are in a test/CI context.

    Keeps mock provider responses contained to the test boundary so
    production runs never silently return AI-fabricated placeholder data.
    """
    raw = os.getenv("AI_PROVIDER", "").lower()
    if raw != "mock":
        return False
    if _in_test_context():
        return True
    _warn_once_mock()
    return False


_warned_mock = False


def _warn_once_mock() -> None:
    global _warned_mock
    if not _warned_mock:
        import logging
        logging.getLogger("factory.core.dry_run").warning(
            "AI_PROVIDER=mock detected in a non-test context — "
            "the flag is IGNORED in production. "
            "Unset AI_PROVIDER or set CI=true / TESTING=true if this is intentional."
        )
        _warned_mock = True
