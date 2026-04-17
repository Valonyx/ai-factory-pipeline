"""
AI Factory Pipeline v5.8.12 — Strict Platform → Deploy Target Mapping

Issue 22 (Phase 1): platforms chosen by the operator in S0 MUST determine
which deploy targets and store accounts the pipeline touches. No iOS /
Google Play side-effects when the operator only asked for web.

Spec Authority: v5.8.12 Phase 1 §22
"""

from __future__ import annotations


PLATFORM_TARGET_MAP: dict[str, dict[str, list[str]]] = {
    "web":          {"deploy_targets": ["web_hosting"], "store_targets": []},
    "ios":          {"deploy_targets": ["testflight", "app_store"], "store_targets": ["app_store"]},
    "android":      {"deploy_targets": ["google_play_internal", "google_play"], "store_targets": ["google_play"]},
    "desktop_mac":  {"deploy_targets": ["mac_pkg"], "store_targets": []},
    "desktop_win":  {"deploy_targets": ["win_installer"], "store_targets": []},
    "desktop_linux":{"deploy_targets": ["appimage"], "store_targets": []},
}


def resolve_deploy_targets(platforms: list[str]) -> dict[str, list[str]]:
    """Map a list of operator-selected platforms to deploy + store targets.

    Strict mapping — never silently drops, never silently adds. Unknown
    platforms or an empty list raise ValueError so callers must handle
    the failure explicitly (typically by halting with PLATFORMS_NOT_SELECTED).

    Returns:
        {"deploy_targets": [...], "store_targets": [...], "platforms": [...]}
        Lists are de-duplicated while preserving first-seen order.
    """
    if not platforms:
        raise ValueError(
            "resolve_deploy_targets: platforms list is empty — operator has "
            "not chosen any platform yet. Halt with PLATFORMS_NOT_SELECTED."
        )
    unknown = [p for p in platforms if p not in PLATFORM_TARGET_MAP]
    if unknown:
        raise ValueError(
            f"resolve_deploy_targets: unknown platform(s): {unknown}. "
            f"Known platforms: {sorted(PLATFORM_TARGET_MAP)}"
        )

    deploy: list[str] = []
    store: list[str] = []
    for p in platforms:
        entry = PLATFORM_TARGET_MAP[p]
        for t in entry["deploy_targets"]:
            if t not in deploy:
                deploy.append(t)
        for t in entry["store_targets"]:
            if t not in store:
                store.append(t)
    return {
        "deploy_targets": deploy,
        "store_targets": store,
        "platforms": list(platforms),
    }
