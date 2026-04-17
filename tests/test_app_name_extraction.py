"""
Issue 14 — App Name Integrity tests.

Covers the explicit-pattern extractor + validator in
factory/pipeline/s0_intake.py (_extract_app_name_explicit, _validate_app_name).
"""

from __future__ import annotations

import pytest

from factory.pipeline.s0_intake import (
    _extract_app_name_explicit,
    _validate_app_name,
)


# ── _validate_app_name ────────────────────────────────────────────────

@pytest.mark.parametrize(
    "candidate, expected",
    [
        ("Pulsey AI", "Pulsey AI"),
        ('"Pulsey AI"', "Pulsey AI"),
        ("  Pulsey  ", "Pulsey"),
        ("“Pulsey”", "Pulsey"),
        ("Acme Todo", "Acme Todo"),
        # Imperative verbs — rejected.
        ("Change platform to web", None),
        ("change platform", None),
        ("UPDATE THE APP", None),
        ("Add feature", None),
        ("Remove login", None),
        ("Make it faster", None),
        ("Rename project", None),
        # Length rules.
        ("A", None),
        ("", None),
        ("   ", None),
        (None, None),
        ("X" * 65, None),
        ("X" * 60, "X" * 60),  # boundary OK
        # Alphanumeric minimum.
        ("!!", None),
        ("!1", None),  # only one alnum char
        ("!12", "!12"),
        # Unicode round-trip.
        ("مطبخي", "مطبخي"),
    ],
)
def test_validate_app_name(candidate, expected):
    assert _validate_app_name(candidate) == expected


# ── _extract_app_name_explicit ────────────────────────────────────────

@pytest.mark.parametrize(
    "raw, expected",
    [
        ('app name: "Pulsey AI"', "Pulsey AI"),
        ("app name: Pulsey AI — a tracker", "Pulsey AI"),
        ("app name: Pulsey AI, tracker", "Pulsey AI"),
        ('App Name = "Acme Todo"', "Acme Todo"),
        ('Build a todo app called "Acme Todo"', "Acme Todo"),
        ("call it \"Zenith\"", "Zenith"),
        ('named "Nova"', "Nova"),
        ('name: "Nova"', "Nova"),
        # Curly quotes.
        ("app name: “Pulsey AI”", "Pulsey AI"),
        # Imperative — no valid extraction, returns None.
        ("Change platform to web", None),
        ("Modify the login screen", None),
        # No explicit name — returns None, NEVER fabricates.
        ("Build me a pulse tracking app for athletes", None),
        ("Make a todo list app", None),
        # Empty / whitespace.
        ("", None),
        ("   ", None),
        # Windowed search: quoted string near the word "name".
        ('The project name should be "Pulsey"', "Pulsey"),
        # Unicode.
        ('app name: "مطبخي"', "مطبخي"),
    ],
)
def test_extract_app_name_explicit(raw, expected):
    assert _extract_app_name_explicit(raw) == expected


def test_long_name_with_description_stops_at_dash():
    assert _extract_app_name_explicit(
        "app name: Pulsey AI — a pulse tracking app for athletes"
    ) == "Pulsey AI"


def test_change_platform_never_becomes_app_name():
    """Regression guard for BUG-B from PHASE_0 audit."""
    for raw in [
        "Change platform to web",
        "change platform to ios",
        "Update the deploy target",
        "Modify the backend",
    ]:
        # Neither explicit extraction nor validation should accept these.
        assert _extract_app_name_explicit(raw) is None
        # Also reject if someone tries to validate the whole message as a name.
        assert _validate_app_name(raw) is None
