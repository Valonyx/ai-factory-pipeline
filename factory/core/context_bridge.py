"""
AI Factory Pipeline v5.8 — Unified Context Bridge

Solves the provider-switch coherence problem: when the AI chain falls
back from Gemini → Groq → OpenRouter etc., the new model has never
seen prior exchanges. Without intervention it starts cold, potentially
contradicting earlier architectural decisions or forgetting app context.

The Context Bridge serializes the relevant parts of PipelineState into
a compact "memory block" that is prepended to every AI prompt, so any
provider — regardless of where in the chain — receives full project context.

What it injects (only the fields that exist):
  - Project identity and current stage
  - App name, category, and description
  - Key legal/compliance decisions
  - Chosen tech stack and architecture (screens, data models)
  - Code generation summary
  - War room status and last error
  - Budget tracking

Injected automatically by call_ai() — no caller changes needed.

Spec Authority: v5.8 §2.2.2 (provider-agnostic AI interface)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from factory.core.state import PipelineState


# Stages where context injection adds value (not the very first call)
_CONTEXT_STAGES = {
    "S1_LEGAL", "S2_BLUEPRINT", "S4_CODEGEN",
    "S5_BUILD", "S6_TEST", "S7_DEPLOY",
    "S8_VERIFY", "S9_HANDOFF",
    "WAR_ROOM", "HALTED",
}


def build_context_block(state: "PipelineState") -> str:
    """Build a compact memory block from PipelineState.

    Structured so any LLM immediately understands the project context
    without needing conversation history from previous provider calls.
    """
    lines: list[str] = [
        "╔══ PROJECT MEMORY (injected for provider continuity) ══",
    ]

    # ── Identity ──
    lines.append(f"│ Project ID : {state.project_id}")
    lines.append(f"│ Stage      : {state.current_stage.value}")

    # ── App concept ──
    if state.s0_output:
        s0 = state.s0_output
        name = s0.get("app_name", "")
        category = s0.get("app_category", "")
        desc = s0.get("app_description", "") or s0.get("concept", "")
        target = s0.get("target_platform", "")
        if name:
            lines.append(f"│ App        : {name}" + (f" [{category}]" if category else ""))
        if desc:
            lines.append(f"│ Concept    : {desc[:300]}")
        if target:
            lines.append(f"│ Platform   : {target}")
    elif state.project_metadata.get("raw_input"):
        raw = state.project_metadata["raw_input"]
        lines.append(f"│ Idea       : {raw[:300]}")

    # ── Legal / compliance ──
    if state.s1_output:
        s1 = state.s1_output
        frameworks = s1.get("applicable_frameworks", [])
        if frameworks:
            lines.append(f"│ Legal      : {', '.join(str(f) for f in frameworks[:6])}")
        flags = []
        if s1.get("requires_gdpr"):
            flags.append("GDPR")
        if s1.get("requires_pci"):
            flags.append("PCI-DSS")
        if s1.get("requires_hipaa"):
            flags.append("HIPAA")
        if flags:
            lines.append(f"│ Compliance : {', '.join(flags)}")
        if state.legal_halt:
            lines.append(f"│ ⚠ Legal halt: {state.legal_halt_reason[:120]}")

    # ── Architecture (most critical for code coherence) ──
    if state.s2_output:
        s2 = state.s2_output
        stack = s2.get("selected_stack", "")
        if stack:
            lines.append(f"│ Stack      : {stack}")
        screens = s2.get("screens", [])
        if screens:
            names = [s.get("name", "?") for s in screens[:10]]
            lines.append(f"│ Screens    : {', '.join(names)}")
        models = s2.get("data_model", [])
        if models:
            mnames = [m.get("name", "?") for m in models[:8]]
            lines.append(f"│ Data models: {', '.join(mnames)}")
        api_ep = s2.get("api_endpoints", [])
        if api_ep:
            epnames = [e.get("path", "?") for e in api_ep[:6]]
            lines.append(f"│ API routes : {', '.join(epnames)}")
        auth = s2.get("auth_provider", "")
        if auth:
            lines.append(f"│ Auth       : {auth}")

    # ── Design (S3) ──
    if state.s3_output:
        s3 = state.s3_output
        design_type = s3.get("design_type", "")
        if design_type:
            lines.append(f"│ Design type: {design_type}")
        mockups = s3.get("mockup_paths", [])
        if mockups:
            lines.append(f"│ Mockups    : {len(mockups)} screens")
        spec_docs = list(s3.get("specialist_docs", {}).keys())
        if spec_docs:
            lines.append(f"│ Spec docs  : {', '.join(spec_docs[:4])}")

    # ── Code generation summary (S4) ──
    if state.s4_output:
        files = state.s4_output.get("generated_files", {})
        if files:
            count = len(files)
            key = list(files.keys())[:6]
            lines.append(f"│ Code       : {count} files generated ({', '.join(key)})")
        tech = state.s4_output.get("tech_items_wired", [])
        if tech:
            tech_names = [
                (t.get("name", str(t)) if isinstance(t, dict) else str(t))
                for t in tech[:6]
            ]
            lines.append(f"│ Tech wired : {', '.join(tech_names)}")

    # ── Build results (S5) ──
    if state.s5_output:
        s5 = state.s5_output
        build_ok = s5.get("build_success", False)
        source_only = s5.get("source_only", False)
        files_written = s5.get("files_written", 0)
        if build_ok:
            lines.append(f"│ Build      : ✓ success ({files_written} files)")
        elif source_only:
            lines.append(f"│ Build      : source-only ({files_written} files — no binary)")
        else:
            lines.append(f"│ Build      : ✗ failed")
        ws = s5.get("workspace_path", "")
        if ws:
            lines.append(f"│ Workspace  : {ws}")

    # ── Test results (S6) ──
    if state.s6_output:
        s5 = state.s6_output
        passed = s5.get("passed_tests", 0)
        total = s5.get("total_tests", 0)
        if total:
            lines.append(f"│ Tests      : {passed}/{total} passing")

    # ── Deploy results (S7) ──
    if state.s7_output:
        s7 = state.s7_output
        all_ok = s7.get("all_success", False)
        src_only = s7.get("source_only", False)
        deployments = s7.get("deployments", {})
        platforms = list(deployments.keys())
        if all_ok:
            lines.append(f"│ Deploy     : ✓ success | {', '.join(platforms)}")
        elif src_only:
            lines.append(f"│ Deploy     : source-zip sent | {', '.join(platforms)}")
        else:
            lines.append(f"│ Deploy     : ✗ failed | {', '.join(platforms)}")
        for platform, info in deployments.items():
            if isinstance(info, dict) and info.get("url"):
                lines.append(f"│ URL        : {platform} → {info['url']}")

    # ── Verify results (S8) ──
    if state.s8_output:
        s8 = state.s8_output
        verify_ok = s8.get("passed", False)
        check_count = s8.get("check_count", 0)
        lines.append(
            f"│ Verify     : {'✓ passed' if verify_ok else '✗ failed'}"
            f" ({check_count} checks)"
        )

    # ── Budget ──
    spent = getattr(state, "total_cost_usd", 0.0)
    limit = state.project_metadata.get("budget_limit_usd", 25)
    if spent > 0:
        lines.append(f"│ Budget     : ${spent:.3f} / ${limit:.0f} used")

    # ── War room / errors ──
    if getattr(state, "war_room_active", False):
        level = getattr(state.war_room_level, "value", "ACTIVE") if state.war_room_level else "ACTIVE"
        lines.append(f"│ ⚠ War room : {level}")
    last_err = getattr(state, "last_error", "") or ""
    if last_err:
        lines.append(f"│ Last error : {last_err[:200]}")

    # ── Exa grounding status ──
    grounding = state.project_metadata.get("_last_scout_grounding")
    if grounding and grounding.get("grounded"):
        confidence = grounding.get("confidence", 0.0)
        source = grounding.get("source", "?")
        preview = grounding.get("prompt_preview", "")
        lines.append(
            f"│ Scout grnd : {int(confidence * 100)}% confidence "
            f"(Exa-grounded {source!r} result)"
        )
        if preview:
            lines.append(f"│ Last query : {preview}")

    lines.append("╚══ END PROJECT MEMORY ══\n")
    return "\n".join(lines)


async def pack_context(
    state: "PipelineState",
    stage: str,
    budget_tokens: int = 2000,
) -> str:
    """Return the highest-value context slice for a given stage + token budget.

    Issue 21 §8: Instead of stuffing all prior state, surgically pick the
    most relevant slices and respect the token budget. Falls back to
    build_context_block() when token budget is generous.

    Token estimate: 1 token ≈ 4 chars.
    """
    from factory.memory.retrieval import (
        get_requirements, get_screens, get_api_spec,
        get_data_models, get_legal_clauses_for,
        get_related_files,
    )

    budget_chars = budget_tokens * 4
    project_id = getattr(state, "project_id", "")

    # ── Stage-specific priority slices ─────────────────────────────
    slices: list[str] = []

    if stage in ("S4_CODEGEN", "S5_BUILD"):
        reqs = await get_requirements(project_id)
        screens = await get_screens(project_id)
        api = await get_api_spec(project_id)
        models = await get_data_models(project_id)
        for label, items in (
            ("Requirements", reqs), ("Screens", screens),
            ("API Endpoints", api), ("Data Models", models),
        ):
            if items:
                block = f"[{label}]\n" + "\n".join(
                    r.get("content","")[:200] for r in items[:10]
                )
                slices.append(block)

    elif stage in ("S1_LEGAL", "S8_VERIFY"):
        clauses = await get_legal_clauses_for(project_id)
        if clauses:
            slices.append(
                "[Legal Clauses]\n" + "\n".join(
                    r.get("content","")[:200] for r in clauses[:8]
                )
            )

    elif stage in ("S6_TEST", "S7_DEPLOY", "S9_HANDOFF"):
        files = await get_related_files(project_id)
        if files:
            slices.append(
                "[Source Files]\n" + "\n".join(
                    r.get("content","")[:150] for r in files[:15]
                )
            )

    # ── Trim to budget ──────────────────────────────────────────────
    combined = "\n\n".join(slices)
    if len(combined) > budget_chars:
        combined = combined[:budget_chars] + "\n[...truncated — use retrieval tools for more]"

    # ── Fallback: base context block ────────────────────────────────
    base = build_context_block(state)
    base_trimmed = base[:max(0, budget_chars - len(combined))]

    parts = [p for p in (base_trimmed, combined) if p.strip()]
    return "\n\n".join(parts) if parts else ""


def inject_context(prompt: str, state: "PipelineState") -> str:
    """Prepend project + operator memory blocks to a prompt.

    Project memory (from PipelineState) is always injected when context
    exists. Operator memory (from Mother Memory) is injected when an
    operator_id is present, giving any AI provider full conversation history.

    This is synchronous to keep call_ai() simple — operator memory is
    pre-fetched and cached on the state object when available.
    """
    stage_name = state.current_stage.value if state.current_stage else ""

    has_project_context = (
        state.s0_output is not None
        or state.s1_output is not None
        or state.s2_output is not None
        or state.s3_output is not None
        or state.s4_output is not None
        or state.s5_output is not None
        or state.s6_output is not None
        or state.s7_output is not None
        or state.s8_output is not None
        or getattr(state, "war_room_active", False)
        or stage_name in _CONTEXT_STAGES
    )

    blocks: list[str] = []

    if has_project_context:
        blocks.append(build_context_block(state))

    # Inject pre-fetched operator memory if available on state metadata
    operator_memory = state.project_metadata.get("_operator_memory_block", "")
    if operator_memory:
        blocks.append(operator_memory)

    if not blocks:
        return prompt

    return "".join(blocks) + prompt


async def inject_context_async(
    prompt: str,
    state: "PipelineState",
    operator_id: Optional[str] = None,
) -> str:
    """Async version — fetches operator memory from Mother Memory live.

    Use this when the prompt is being built outside of call_ai() or when
    you want fresh memory (e.g., for the Telegram bot's AI responder).
    """
    stage_name = state.current_stage.value if state.current_stage else ""

    has_project_context = (
        state.s0_output is not None
        or state.s1_output is not None
        or state.s2_output is not None
        or state.s3_output is not None
        or state.s4_output is not None
        or state.s5_output is not None
        or state.s6_output is not None
        or state.s7_output is not None
        or state.s8_output is not None
        or getattr(state, "war_room_active", False)
        or stage_name in _CONTEXT_STAGES
    )

    blocks: list[str] = []

    if has_project_context:
        blocks.append(build_context_block(state))

    # Pull fresh operator memory if we have an operator_id
    oid = operator_id or state.operator_id or state.project_metadata.get("operator_id", "")
    if oid:
        try:
            from factory.memory.mother_memory import build_memory_block
            mem = await build_memory_block(
                operator_id=oid,
                project_id=state.project_id,
            )
            if mem:
                blocks.append(mem)
        except Exception:
            pass  # never crash a pipeline call over memory fetch

    if not blocks:
        return prompt

    return "".join(blocks) + prompt
