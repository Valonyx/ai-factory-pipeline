"""
AI Factory Pipeline v5.8 — Stage Chain Context Injection

Universal mechanism ensuring each pipeline stage (S0→S9) injects its
outputs into the next stage, preventing end-to-end drift.

Every stage's AI prompts are prefixed with a structured snapshot of all
prior completed stages via build_chain_context_block().

This extends the PipelineContext pattern (introduced in S4) to ALL stages:
  S0 → S1: app identity, platforms, payment flag, must-have features
  S1 → S2: blocked features, required consents, PDPL obligations
  S2 → S3: stack, screens, data model, auth provider
  S3 → S4: design type, mockups, specialist docs (also via PipelineContext)
  S4 → S5: generated files, wired tech, env vars
  S5 → S6: build success/failure, source_only flag, workspace path
  S6 → S7: test pass/fail, failures list, deploy approval status
  S7 → S8: deploy URLs, platform deployment results
  S8 → S9: verify_passed, compliance check count and details

Usage in any stage:
    from factory.pipeline.stage_chain import build_chain_context_block
    ctx_block = build_chain_context_block(state, current_stage="s6_test")
    prompt = ctx_block + "\\n" + my_prompt

Spec Authority: v5.8 §Phase7 — Cross-Stage Fidelity Lock
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from factory.core.state import PipelineState

logger = logging.getLogger("factory.pipeline.stage_chain")


# ═══════════════════════════════════════════════════════════════════
# StageChainEnvelope — structured snapshot of all prior stage outputs
# ═══════════════════════════════════════════════════════════════════


@dataclass
class StageChainEnvelope:
    """Structured snapshot of key outputs from all completed stages.

    Used by build_chain_context_block() to render a prompt-injectable
    context block that prevents any stage from drifting away from
    prior stage decisions.
    """

    # ── S0 Intake ──
    app_name: str = ""
    app_category: str = ""
    app_description: str = ""
    target_platforms: list = field(default_factory=list)
    market: str = ""
    has_payments: bool = False
    payment_sandbox: bool = False
    features_must: list = field(default_factory=list)

    # ── S1 Legal ──
    legal_dossier_generated: bool = False
    blocked_features: list = field(default_factory=list)
    required_consents: list = field(default_factory=list)
    pdpl_obligations: list = field(default_factory=list)
    data_residency: str = ""
    compliance_frameworks: list = field(default_factory=list)

    # ── S2 Blueprint ──
    selected_stack: str = ""
    screens: list = field(default_factory=list)
    data_model: list = field(default_factory=list)
    api_endpoints: list = field(default_factory=list)
    auth_provider: str = ""
    ieee_docs_count: int = 0

    # ── S3 Design ──
    design_type: str = ""
    mockup_paths: list = field(default_factory=list)
    specialist_doc_names: list = field(default_factory=list)
    component_library: str = ""
    design_tokens_path: str = ""

    # ── S4 CodeGen ──
    generated_files_count: int = 0
    generated_files_sample: list = field(default_factory=list)
    tech_items_wired: list = field(default_factory=list)
    blueprint_drift_detected: bool = False
    env_var_names: list = field(default_factory=list)

    # ── S5 Build ──
    build_success: bool = False
    source_only: bool = False
    workspace_path: str = ""
    build_duration_seconds: float = 0.0
    files_written: int = 0
    build_artifacts: dict = field(default_factory=dict)

    # ── S6 Test ──
    tests_passed: bool = False
    total_tests: int = 0
    passed_tests: int = 0
    failed_tests: int = 0
    test_failures: list = field(default_factory=list)
    deploy_approved: bool = True

    # ── S7 Deploy ──
    deploy_success: bool = False
    deploy_source_only: bool = False
    deployment_platforms: list = field(default_factory=list)
    deploy_urls: dict = field(default_factory=dict)

    # ── S8 Verify ──
    verify_passed: bool = False
    verify_check_count: int = 0
    verify_checks: list = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════
# Envelope builder
# ═══════════════════════════════════════════════════════════════════


def build_stage_chain_envelope(state: "PipelineState") -> StageChainEnvelope:
    """Extract all available stage outputs into a StageChainEnvelope.

    Reads whichever sN_output fields are populated on state.
    Missing stages simply leave their envelope fields at defaults.
    """
    env = StageChainEnvelope()

    # ── S0 ──
    s0 = state.s0_output or {}
    env.app_name = s0.get("app_name", "")
    env.app_category = s0.get("app_category", "")
    env.app_description = (
        s0.get("app_description", "") or s0.get("concept", "")
    )[:400]
    env.target_platforms = s0.get("target_platforms", [])
    env.market = s0.get("market", "KSA")
    env.has_payments = bool(s0.get("has_payments", False))
    env.features_must = s0.get("features_must", [])

    # ── S1 ──
    s1 = state.s1_output or {}
    env.legal_dossier_generated = bool(
        s1.get("dossier_generated")
        or s1.get("legal_documents")
        or s1.get("docugen_count", 0)
    )
    # S1 dossier is cached on project_metadata by _ingest_s1_dossier() in S2
    s1_dossier = state.project_metadata.get("s1_dossier") or {}
    env.blocked_features = s1_dossier.get("blocked_features", [])
    env.required_consents = s1_dossier.get("required_consents", [])
    env.pdpl_obligations = s1_dossier.get("pdpl_obligations", [])
    env.payment_sandbox = bool(s1_dossier.get("payment_sandbox", False))
    env.data_residency = s1_dossier.get("data_residency", "")
    env.compliance_frameworks = [
        str(f) for f in s1.get("applicable_frameworks", [])[:6]
    ]

    # ── S2 ──
    s2 = state.s2_output or {}
    env.selected_stack = s2.get("selected_stack", "")
    env.screens = s2.get("screens", [])
    env.data_model = s2.get("data_model", [])
    env.api_endpoints = s2.get("api_endpoints", [])
    env.auth_provider = s2.get("auth_provider", "")
    env.ieee_docs_count = len(s2.get("ieee_docs", {}))

    # ── S3 ──
    s3 = state.s3_output or {}
    env.design_type = s3.get("design_type", "")
    env.mockup_paths = s3.get("mockup_paths", [])
    env.specialist_doc_names = list(s3.get("specialist_docs", {}).keys())
    env.component_library = s3.get("component_library", "")
    env.design_tokens_path = s3.get("design_tokens_path", "")

    # ── S4 ──
    s4 = state.s4_output or {}
    files = s4.get("generated_files", {})
    env.generated_files_count = len(files)
    env.generated_files_sample = list(files.keys())[:10]
    env.tech_items_wired = [
        (t.get("name", str(t)) if isinstance(t, dict) else str(t))
        for t in s4.get("tech_items_wired", [])
    ]
    drift = s4.get("blueprint_drift", {})
    env.blueprint_drift_detected = bool(
        drift.get("drift_detected") if isinstance(drift, dict) else False
    )
    env.env_var_names = list(s4.get("env_vars", {}).keys())

    # ── S5 ──
    if state.s5_output is not None:
        s5 = state.s5_output
        env.build_success = bool(s5.get("build_success", False))
        env.source_only = bool(s5.get("source_only", False))
        env.workspace_path = s5.get("workspace_path", "")
        env.build_duration_seconds = float(s5.get("build_duration_seconds", 0.0))
        env.files_written = int(s5.get("files_written", 0))
        env.build_artifacts = s5.get("artifacts", {})

    # ── S6 ──
    if state.s6_output is not None:
        s6 = state.s6_output
        env.tests_passed = bool(s6.get("passed", False))
        env.total_tests = int(s6.get("total_tests", 0))
        env.passed_tests = int(s6.get("passed_tests", 0))
        env.failed_tests = int(s6.get("failed_tests", 0))
        env.test_failures = s6.get("failures", [])[:5]
        env.deploy_approved = not bool(s6.get("deploy_cancelled", False))

    # ── S7 ──
    if state.s7_output is not None:
        s7 = state.s7_output
        env.deploy_success = bool(s7.get("all_success", False))
        env.deploy_source_only = bool(s7.get("source_only", False))
        deployments = s7.get("deployments", {})
        env.deployment_platforms = list(deployments.keys())
        env.deploy_urls = {
            k: v.get("url", "")
            for k, v in deployments.items()
            if isinstance(v, dict) and v.get("url")
        }

    # ── S8 ──
    if state.s8_output is not None:
        s8 = state.s8_output
        env.verify_passed = bool(s8.get("passed", False))
        env.verify_check_count = int(s8.get("check_count", 0))
        env.verify_checks = s8.get("checks", [])[:10]

    return env


# ═══════════════════════════════════════════════════════════════════
# Context block builder
# ═══════════════════════════════════════════════════════════════════


def build_chain_context_block(
    state: "PipelineState",
    current_stage: str = "",
    compact: bool = False,
) -> str:
    """Build a structured context block from all prior stage outputs.

    Inject this at the start of stage AI prompts to prevent drift.

    Args:
        state: Current pipeline state.
        current_stage: e.g. "s6_test" — shown in the block header.
        compact: If True, emit shorter format (one line per stage).

    Returns:
        Formatted multi-line string for prompt injection. Empty string
        when no prior stages have completed.
    """
    env = build_stage_chain_envelope(state)

    # Only emit the block when at least S0 has data
    if not env.app_name and not env.selected_stack and not env.generated_files_count:
        return ""

    stage_label = f" → {current_stage}" if current_stage else ""
    lines: list[str] = [
        f"╔══ STAGE CHAIN CONTEXT{stage_label} — outputs from all prior stages ══"
    ]

    # ── S0 ──
    if env.app_name:
        lines.append(
            f"│ S0 │ App: {env.app_name!r} | Category: {env.app_category}"
            f" | Market: {env.market}"
        )
        if env.target_platforms:
            lines.append(f"│    │ Platforms: {', '.join(env.target_platforms)}")
        if env.has_payments:
            sandbox_note = " (sandbox only)" if env.payment_sandbox else " (live)"
            lines.append(f"│    │ Payments: YES{sandbox_note}")
        if env.features_must and not compact:
            lines.append(
                f"│    │ Must-have features: "
                f"{', '.join(str(f) for f in env.features_must[:6])}"
            )

    # ── S1 ──
    if env.blocked_features or env.required_consents or env.compliance_frameworks:
        if env.blocked_features:
            lines.append(
                f"│ S1 │ 🚫 BLOCKED features: {', '.join(env.blocked_features)}"
            )
        if env.required_consents:
            lines.append(
                f"│    │ ✅ Required consents: {', '.join(env.required_consents)}"
            )
        if env.pdpl_obligations and not compact:
            lines.append(
                f"│    │ PDPL obligations: {', '.join(env.pdpl_obligations)}"
            )
        if env.data_residency:
            lines.append(f"│    │ Data residency: {env.data_residency}")
        if env.compliance_frameworks:
            lines.append(
                f"│    │ Frameworks: {', '.join(env.compliance_frameworks)}"
            )

    # ── S2 ──
    if env.selected_stack:
        lines.append(
            f"│ S2 │ Stack: {env.selected_stack} | Auth: {env.auth_provider or 'TBD'}"
        )
        if env.screens:
            names = [
                (s.get("name", "?") if isinstance(s, dict) else str(s))
                for s in env.screens[:10]
            ]
            lines.append(
                f"│    │ Screens ({len(env.screens)}): {', '.join(names)}"
            )
        if env.data_model and not compact:
            mnames = [
                (m.get("name", "?") if isinstance(m, dict) else str(m))
                for m in env.data_model[:8]
            ]
            lines.append(f"│    │ Data models: {', '.join(mnames)}")
        if env.api_endpoints and not compact:
            epaths = [
                (e.get("path", "?") if isinstance(e, dict) else str(e))
                for e in env.api_endpoints[:6]
            ]
            lines.append(f"│    │ API routes: {', '.join(epaths)}")

    # ── S3 ──
    if env.design_type:
        lines.append(f"│ S3 │ Design type: {env.design_type}")
        if env.specialist_doc_names and not compact:
            lines.append(
                f"│    │ Specialist docs: {', '.join(env.specialist_doc_names[:5])}"
            )
        if env.mockup_paths:
            lines.append(f"│    │ Mockups: {len(env.mockup_paths)} screens")

    # ── S4 ──
    if env.generated_files_count > 0:
        lines.append(f"│ S4 │ Generated: {env.generated_files_count} files")
        if env.tech_items_wired and not compact:
            lines.append(
                f"│    │ Tech wired: {', '.join(env.tech_items_wired[:8])}"
            )
        if env.blueprint_drift_detected:
            lines.append("│    │ ⚠ Blueprint drift was detected and corrected")
        if env.env_var_names and not compact:
            lines.append(
                f"│    │ Env vars: {', '.join(env.env_var_names[:8])}"
            )

    # ── S5 ──
    if state.s5_output is not None:
        if env.build_success:
            build_status = "✓ success"
        elif env.source_only:
            build_status = "source-only (no binary)"
        else:
            build_status = "✗ failed"
        lines.append(
            f"│ S5 │ Build: {build_status} | {env.files_written} files"
            f" | {env.build_duration_seconds:.1f}s"
        )
        if env.workspace_path and not compact:
            lines.append(f"│    │ Workspace: {env.workspace_path}")

    # ── S6 ──
    if state.s6_output is not None:
        test_status = "✓ passed" if env.tests_passed else "✗ failed"
        lines.append(
            f"│ S6 │ Tests: {test_status} "
            f"({env.passed_tests}/{env.total_tests})"
        )
        if env.test_failures and not compact:
            for failure in env.test_failures[:3]:
                if isinstance(failure, dict):
                    lines.append(
                        f"│    │   ✗ {failure.get('test', '?')}: "
                        f"{failure.get('error', '')[:80]}"
                    )
        if not env.deploy_approved:
            lines.append("│    │ ⚠ Deploy was cancelled by operator")

    # ── S7 ──
    if state.s7_output is not None:
        if env.deploy_success:
            deploy_status = "✓ deployed"
        elif env.deploy_source_only:
            deploy_status = "source-zip delivered"
        else:
            deploy_status = "✗ failed"
        platforms_str = ", ".join(env.deployment_platforms) or "none"
        lines.append(
            f"│ S7 │ Deploy: {deploy_status} | Platforms: {platforms_str}"
        )
        for platform, url in env.deploy_urls.items():
            if url:
                lines.append(f"│    │   → {platform}: {url}")

    # ── S8 ──
    if state.s8_output is not None:
        verify_status = "✓ passed" if env.verify_passed else "✗ failed"
        lines.append(
            f"│ S8 │ Verify: {verify_status} ({env.verify_check_count} checks)"
        )

    lines.append("╚══ END STAGE CHAIN CONTEXT ══\n")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════
# Convenience: inject chain block into a prompt string
# ═══════════════════════════════════════════════════════════════════


def inject_chain_context(
    prompt: str,
    state: "PipelineState",
    current_stage: str = "",
    compact: bool = False,
) -> str:
    """Prepend the stage chain context block to a prompt.

    Drop-in wrapper so callers don't need to handle the empty-string case.

    Args:
        prompt: The original stage AI prompt.
        state: Current pipeline state.
        current_stage: Stage label for the block header.
        compact: Whether to use the compact single-line-per-stage format.

    Returns:
        Enriched prompt with chain context prepended, or original prompt
        if no prior stage data is available.
    """
    block = build_chain_context_block(state, current_stage=current_stage, compact=compact)
    if not block:
        return prompt
    return block + prompt
