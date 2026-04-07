"""
AI Factory Pipeline v5.6 — Unified Context Bridge

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

Spec Authority: v5.6 §2.2.2 (provider-agnostic AI interface)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from factory.core.state import PipelineState


# Stages where context injection adds value (not the very first call)
_CONTEXT_STAGES = {
    "S1_LEGAL", "S2_BLUEPRINT", "S3_CODEGEN",
    "S4_BUILD", "S5_TEST", "S6_DEPLOY",
    "S7_VERIFY", "S8_HANDOFF",
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

    # ── Code generation summary ──
    if state.s3_output:
        files = state.s3_output.get("generated_files", {})
        if files:
            count = len(files)
            key = [f for f in list(files.keys())[:6]]
            lines.append(f"│ Code       : {count} files generated ({', '.join(key)})")

    # ── Test results ──
    if state.s5_output:
        s5 = state.s5_output
        passed = s5.get("passed_tests", 0)
        total = s5.get("total_tests", 0)
        if total:
            lines.append(f"│ Tests      : {passed}/{total} passing")

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
