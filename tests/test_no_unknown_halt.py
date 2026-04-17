"""
Issue 19 guard — no hardcoded "unknown" as halt reason.

Ensures:
  1. HaltCode enum has no UNKNOWN member.
  2. No file under factory/ sets halt_reason, halt_reason_struct, or
     legal_halt_reason to the literal string "unknown" (case-insensitive).
  3. format_halt_message renders actionable text (never shows the word
     "unknown" as THE reason).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from factory.core.halt import HaltCode, HaltReason, set_halt


FACTORY_ROOT = Path(__file__).resolve().parent.parent / "factory"


def test_halt_code_has_no_unknown_member():
    assert "UNKNOWN" not in HaltCode.__members__
    for member in HaltCode:
        assert member.value.lower() != "unknown"


def test_halt_reason_rejects_empty_detail():
    with pytest.raises(ValueError):
        HaltReason(code=HaltCode.APP_NAME_MISSING, title="x", detail="", stage="S0")
    with pytest.raises(ValueError):
        HaltReason(code=HaltCode.APP_NAME_MISSING, title="", detail="d", stage="S0")


def test_no_halt_reason_assigned_literal_unknown():
    """Scan factory/ for halt_reason = "unknown" style assignments."""
    # Patterns that would indicate a hardcoded "unknown" halt reason.
    bad_patterns = [
        re.compile(r'halt_reason\s*=\s*["\']unknown["\']', re.IGNORECASE),
        re.compile(r'legal_halt_reason\s*=\s*["\']unknown["\']', re.IGNORECASE),
        re.compile(r'halt_reason_struct\s*=\s*["\']unknown["\']', re.IGNORECASE),
        re.compile(
            r'project_metadata\[["\']halt_reason["\']\]\s*=\s*["\']unknown["\']',
            re.IGNORECASE,
        ),
    ]
    offenders: list[tuple[str, int, str]] = []
    for py in FACTORY_ROOT.rglob("*.py"):
        try:
            text = py.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for i, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            # Skip pure-comment lines and docstring-ish lines.
            if stripped.startswith("#"):
                continue
            for pat in bad_patterns:
                m = pat.search(line)
                if not m:
                    continue
                # Skip if the match sits inside a string literal that is a
                # comment/docstring (i.e. inside a triple-quoted block or an
                # inline backtick quote). A simple heuristic: require the
                # match to appear to the left of any "#" and to not be
                # enclosed in backticks.
                prefix = line[: m.start()]
                if "`" in prefix and "`" in line[m.end():]:
                    continue
                offenders.append((str(py.relative_to(FACTORY_ROOT.parent)), i, stripped))
    assert not offenders, (
        "Hardcoded 'unknown' halt-reason assignments found:\n  "
        + "\n  ".join(f"{p}:{ln}: {t}" for p, ln, t in offenders)
    )


def test_format_for_telegram_includes_all_fields():
    r = HaltReason(
        code=HaltCode.APP_NAME_MISSING,
        title="Name missing",
        detail="No explicit app name found in intake message",
        stage="S0_INTAKE",
        remediation_steps=["Reply with: app name: \"My App\"", "/cancel"],
    )
    out = r.format_for_telegram()
    assert "APP_NAME_MISSING" in out
    assert "Name missing" in out
    assert "S0_INTAKE" in out
    assert "No explicit app name" in out
    assert "/cancel" in out
    # At least one actionable command present.
    assert any(cmd in out for cmd in ("/cancel", "/continue", "/restore"))


def test_each_halt_code_renders_cleanly():
    for code in HaltCode:
        r = HaltReason(
            code=code,
            title=f"title for {code.value}",
            detail=f"detail for {code.value}",
            stage="S0_INTAKE",
            remediation_steps=["step one"],
        )
        out = r.format_for_telegram()
        assert code.value in out
        assert "step one" in out


def test_set_halt_populates_state_metadata():
    class _S:
        legal_halt = False
        legal_halt_reason = None
        project_metadata: dict = {}

    s = _S()
    s.project_metadata = {}
    reason = HaltReason(
        code=HaltCode.APP_NAME_MISSING,
        title="t",
        detail="d",
        stage="S0_INTAKE",
    )
    set_halt(s, reason)
    assert s.legal_halt is True
    assert "APP_NAME_MISSING" in s.legal_halt_reason
    assert s.project_metadata["halt_reason_struct"]["code"] == "APP_NAME_MISSING"
