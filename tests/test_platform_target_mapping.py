"""
Issue 22 — Platform → Deploy Target mapping tests.

Covers factory/core/platform_targets.py strict resolver and guards against
App Store / Google Play side effects on web-only projects.
"""

from __future__ import annotations

import pytest

from factory.core.platform_targets import (
    PLATFORM_TARGET_MAP,
    resolve_deploy_targets,
)


def test_map_has_all_canonical_platforms():
    assert set(PLATFORM_TARGET_MAP) == {
        "web", "ios", "android",
        "desktop_mac", "desktop_win", "desktop_linux",
    }


def test_every_entry_has_both_keys_as_lists():
    for platform, entry in PLATFORM_TARGET_MAP.items():
        assert isinstance(entry["deploy_targets"], list), platform
        assert isinstance(entry["store_targets"], list), platform


def test_web_never_resolves_to_app_store_or_google_play():
    out = resolve_deploy_targets(["web"])
    assert "app_store" not in out["deploy_targets"]
    assert "app_store" not in out["store_targets"]
    assert "google_play" not in out["deploy_targets"]
    assert "google_play" not in out["store_targets"]
    assert out["deploy_targets"] == ["web_hosting"]


def test_ios_resolves_to_app_store_targets():
    out = resolve_deploy_targets(["ios"])
    assert "app_store" in out["store_targets"]
    assert "testflight" in out["deploy_targets"]
    # But not android.
    assert "google_play" not in out["store_targets"]


def test_android_resolves_to_google_play_targets():
    out = resolve_deploy_targets(["android"])
    assert "google_play" in out["store_targets"]
    # But not iOS.
    assert "app_store" not in out["store_targets"]


def test_multi_platform_merges_without_duplicates():
    out = resolve_deploy_targets(["web", "ios", "android"])
    assert out["deploy_targets"].count("web_hosting") == 1
    assert "testflight" in out["deploy_targets"]
    assert "google_play" in out["deploy_targets"]


def test_order_is_preserved():
    out = resolve_deploy_targets(["android", "web"])
    assert out["platforms"] == ["android", "web"]
    assert out["deploy_targets"].index("google_play_internal") < out["deploy_targets"].index("web_hosting")


def test_empty_list_raises():
    with pytest.raises(ValueError, match="empty"):
        resolve_deploy_targets([])


def test_unknown_platform_raises():
    with pytest.raises(ValueError, match="unknown"):
        resolve_deploy_targets(["blackberry"])


def test_desktop_variants_have_no_store_targets():
    for p in ("desktop_mac", "desktop_win", "desktop_linux"):
        out = resolve_deploy_targets([p])
        assert out["store_targets"] == []


def test_web_only_integration_has_no_app_store_strings():
    """Guard against downstream accidentally re-adding store targets."""
    out = resolve_deploy_targets(["web"])
    rendered = str(out)
    assert "app_store" not in rendered
    assert "google_play" not in rendered
