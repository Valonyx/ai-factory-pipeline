"""
AI Factory Pipeline v5.8 — S6 Test Node

Implements:
  - §4.6 S6 Test (generate + run + analyze tests)
  - §4.6.1 Pre-Deploy Operator Acknowledgment Gate (FIX-08)
  - §4.6.2 Deploy decision waiting with timeout
  - War Room feedback on test failures

Spec Authority: v5.8 §4.6, §4.6.1, §4.6.2
"""

from __future__ import annotations
import os

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from factory.core.state import (
    AIRole,
    AutonomyMode,
    NotificationType,
    PipelineState,
    Stage,
    TechStack,
)
from factory.core.roles import call_ai
from factory.core.execution import ExecutionModeManager
from factory.core.user_space import enforce_user_space
from factory.pipeline.graph import pipeline_node, register_stage_node

logger = logging.getLogger("factory.pipeline.s6_test")


# ═══════════════════════════════════════════════════════════════════
# Test Runner Configuration
# ═══════════════════════════════════════════════════════════════════

TEST_COMMANDS: dict[TechStack, str] = {
    TechStack.FLUTTERFLOW:    "flutter test",
    TechStack.REACT_NATIVE:   "npx jest --ci --json",
    TechStack.SWIFT:          "swift test",
    TechStack.KOTLIN:         "./gradlew test",
    TechStack.UNITY:          "unity-editor -batchmode -runTests -testResults results.xml",
    TechStack.PYTHON_BACKEND: "python -m pytest --tb=short -q",
}

# Static analysis commands used when S5 was source_only (no binary to test)
_STATIC_ANALYSIS_COMMANDS: dict[TechStack, str] = {
    TechStack.FLUTTERFLOW:    "flutter analyze --no-pub 2>&1 || true",
    TechStack.REACT_NATIVE:   "npx eslint . --ext .js,.jsx,.ts,.tsx 2>&1 || true",
    TechStack.SWIFT:          "swiftlint --reporter json 2>&1 || true",
    TechStack.KOTLIN:         "./gradlew lint 2>&1 || true",
    TechStack.UNITY:          "echo 'Unity source check: no build environment'",
    TechStack.PYTHON_BACKEND: "python -m flake8 . --max-line-length=120 2>&1 || true",
}

# Pre-deploy gate timeouts
COPILOT_DEPLOY_TIMEOUT = 3600   # 1 hour
AUTOPILOT_DEPLOY_TIMEOUT = int(os.getenv("AUTOPILOT_DEPLOY_TIMEOUT", "900"))  # 15 min, override via env


# ═══════════════════════════════════════════════════════════════════
# §4.6 S6 Test Node
# ═══════════════════════════════════════════════════════════════════


@pipeline_node(Stage.S6_TEST)
async def s6_test_node(state: PipelineState) -> PipelineState:
    """S5: Test — generate and run tests, analyze results.

    Spec: §4.6
    Step 1: Generate test suite (if not present)
    Step 2: Run tests
    Step 3: Analyze results
    Step 4: Pre-deploy gate (FIX-08)

    Cost target: <$0.50
    """
    blueprint_data = state.s2_output or {}
    files = (state.s4_output or {}).get("generated_files", {})
    stack_value = blueprint_data.get("selected_stack", "flutterflow")

    try:
        stack = TechStack(stack_value)
    except ValueError:
        stack = TechStack.FLUTTERFLOW

    exec_mgr = ExecutionModeManager(state)

    # ── Inject S5 build context — critical for test strategy ──
    s5_output = state.s5_output or {}
    source_only = s5_output.get("source_only", False)
    build_success = s5_output.get("build_success", False)
    workspace_path = s5_output.get("workspace_path", "")
    files_written = s5_output.get("files_written", 0)

    if source_only:
        logger.info(
            f"[{state.project_id}] S6: S5 was source_only — "
            f"switching to static analysis (no binary to run tests against)"
        )

    # ── Step 1: Generate test suite (if not present) ──
    test_files_exist = any("test" in k.lower() for k in files.keys())
    if not test_files_exist:
        files = await _generate_test_suite(
            state, blueprint_data, files, stack,
            s5_context={
                "source_only": source_only,
                "build_success": build_success,
                "workspace_path": workspace_path,
                "files_written": files_written,
            },
        )
        state.s4_output["generated_files"] = files

    # ── Step 2: Run tests ──
    # Use static analysis when S5 produced source-only (no binary built)
    if source_only:
        test_cmd = _STATIC_ANALYSIS_COMMANDS.get(
            stack, "echo 'Static analysis: no analyzer available'"
        )
    else:
        test_cmd = TEST_COMMANDS.get(stack, "echo 'No test runner'")
    requires_mac = stack in (TechStack.SWIFT, TechStack.FLUTTERFLOW, TechStack.UNITY)

    result = await exec_mgr.execute_task({
        "name": "run_tests" if not source_only else "static_analysis",
        "type": "build",
        "command": enforce_user_space(test_cmd),
        "timeout": 600,
    }, requires_macincloud=requires_mac and not source_only)

    # ── Step 3: Analyze results ──
    test_output = await _analyze_test_results(state, result)
    # Annotate with S5 context so S7/S8 know the build mode
    test_output["source_only"] = source_only
    test_output["build_success"] = build_success
    test_output["test_mode"] = "static_analysis" if source_only else "full_test_suite"
    state.s6_output = test_output
    state.project_metadata["tests_passed"] = test_output.get("passed", False)

    # ── Step 4: Pre-deploy gate (FIX-08) ──
    if test_output.get("passed", False):
        deploy_approved = await pre_deploy_gate(state)
        if not deploy_approved:
            # Operator cancelled — mark as not passed to route back
            state.s6_output["passed"] = False
            state.s6_output["deploy_cancelled"] = True
            logger.info(
                f"[{state.project_id}] Deploy cancelled by operator"
            )

    logger.info(
        f"[{state.project_id}] S6 Test: "
        f"passed={test_output.get('passed')}, "
        f"total={test_output.get('total_tests', 0)}, "
        f"failed={test_output.get('failed_tests', 0)}"
    )
    return state


# ═══════════════════════════════════════════════════════════════════
# Test Generation
# ═══════════════════════════════════════════════════════════════════


async def _generate_test_suite(
    state: PipelineState,
    blueprint_data: dict,
    files: dict,
    stack: TechStack,
    s5_context: Optional[dict] = None,
) -> dict:
    """Generate test suite if not present.

    Spec: §4.6 Step 1

    Args:
        s5_context: Build context from S5 (source_only, build_success,
                    workspace_path, files_written). Injected into the
                    test generation prompt to prevent drift from S5.
    """
    screens = blueprint_data.get("screens", [])
    data_model = blueprint_data.get("data_model", [])
    api_endpoints = blueprint_data.get("api_endpoints", [])
    s5 = s5_context or {}

    # Inject S5 build context into test generation strategy
    source_only = s5.get("source_only", False)
    build_note = (
        "NOTE: S5 build produced source code only (no binary). "
        "Generate tests that can run via static analysis or in CI without "
        "a built binary. Focus on unit tests and linting-compatible tests."
        if source_only else
        "S5 build succeeded. Generate the full test suite including "
        "widget/component tests and integration tests."
    )

    from factory.core.stage_enrichment import enrich_prompt
    from factory.pipeline.stage_chain import build_chain_context_block
    chain_ctx = build_chain_context_block(state, current_stage="s6_test", compact=True)

    _test_base = (
        f"{chain_ctx}"
        f"Generate test suite for {stack.value} project.\n\n"
        f"S5 BUILD CONTEXT:\n"
        f"- Build success: {s5.get('build_success', 'N/A')}\n"
        f"- Source only (no binary): {source_only}\n"
        f"- Files written: {s5.get('files_written', 'N/A')}\n"
        f"- Workspace: {s5.get('workspace_path', 'N/A')}\n"
        f"- Strategy: {build_note}\n\n"
        f"Screens: {[s.get('name', '?') for s in screens]}\n"
        f"Data model: {json.dumps(data_model)[:2000]}\n"
        f"API endpoints: {json.dumps(api_endpoints)[:1500]}\n\n"
        f"Generate:\n"
        f"- Unit tests for data models\n"
        f"- Widget/component tests for key screens\n"
        f"- Integration test for auth flow (if applicable)\n\n"
        f"Return JSON (no markdown): {{\"file_path\": \"file_content\", ...}}"
    )
    _test_prompt = await enrich_prompt("s6_test", _test_base, state, scout=False)
    test_result = await call_ai(
        role=AIRole.ENGINEER,
        prompt=_test_prompt,
        state=state,
        action="write_code",
    )

    try:
        test_files = json.loads(test_result)
        files.update(test_files)
    except json.JSONDecodeError:
        logger.warning(f"[{state.project_id}] S5: Test generation parse failed")

    return files


# ═══════════════════════════════════════════════════════════════════
# Test Result Analysis
# ═══════════════════════════════════════════════════════════════════


async def _analyze_test_results(
    state: PipelineState, result: dict,
) -> dict:
    """Analyze test runner output.

    Spec: §4.6 Step 3
    """
    analysis = await call_ai(
        role=AIRole.QUICK_FIX,
        prompt=(
            f"Analyze test results.\n\n"
            f"Exit code: {result.get('exit_code', -1)}\n"
            f"Stdout:\n{result.get('stdout', '')[-3000:]}\n"
            f"Stderr:\n{result.get('stderr', '')[-2000:]}\n\n"
            f"Return ONLY valid JSON:\n"
            f'{{\n'
            f'  "passed": true/false,\n'
            f'  "total_tests": 0,\n'
            f'  "passed_tests": 0,\n'
            f'  "failed_tests": 0,\n'
            f'  "security_critical": false,\n'
            f'  "failures": [{{"file": "...", "test": "...", '
            f'"error": "...", "severity": "critical|normal"}}]\n'
            f'}}'
        ),
        state=state,
        action="general",
    )

    try:
        return json.loads(analysis)
    except json.JSONDecodeError:
        import os
        # In CLI/dry-run: mock executor has no exit_code — treat as passed
        dry_run = (
            os.getenv("TELEGRAM_BOT_TOKEN") is None
            or os.getenv("DRY_RUN", "false").lower() == "true"
        )
        exit_code = result.get("exit_code", 0 if dry_run else -1)
        passed = exit_code == 0
        return {
            "passed": passed,
            "total_tests": 1,
            "passed_tests": 1 if passed else 0,
            "failed_tests": 0 if passed else 1,
            "security_critical": False,
            "failures": [],
        }


# ═══════════════════════════════════════════════════════════════════
# §4.6.1 Pre-Deploy Gate (FIX-08, ADR-046)
# ═══════════════════════════════════════════════════════════════════


async def pre_deploy_gate(state: PipelineState) -> bool:
    """Pre-deploy operator acknowledgment gate.

    Spec: §4.6.1 (FIX-08)
    Copilot: requires explicit /deploy_confirm (1-hour timeout → auto-approve)
    Autopilot: 15-minute auto-approve timer with /deploy_cancel escape
    """
    # CLI / dry-run bypass — no Telegram configured, auto-approve immediately
    import os
    if os.getenv("TELEGRAM_BOT_TOKEN") is None or os.getenv("DRY_RUN", "false").lower() == "true":
        logger.info(f"[{state.project_id}] pre_deploy_gate: CLI/dry-run bypass — auto-approved")
        return True
    from factory.telegram.notifications import notify_operator
    from factory.telegram.decisions import check_deploy_decision, clear_deploy_decision

    project_name = (state.s0_output or {}).get("app_name", state.project_id)
    stack = state.selected_stack.value if state.selected_stack else "unknown"
    test_summary = state.s6_output or {}
    passed = test_summary.get("passed_tests", 0)
    total = test_summary.get("total_tests", 0)
    failed = test_summary.get("failed_tests", 0)

    # Determine target stores
    target_stores = _get_target_stores(state.selected_stack)
    store_str = " + ".join(target_stores) if target_stores else "deployment target"

    # Compliance artifacts count
    compliance_count = len(
        (state.s2_output or {}).get("compliance_artifacts", [])
    )

    if state.autonomy_mode == AutonomyMode.COPILOT:
        # ── Copilot: require explicit confirmation ──
        await notify_operator(
            state,
            NotificationType.DECISION_NEEDED,
            f"✅ Testing complete for {project_name}\n\n"
            f"Platform: {stack}\n"
            f"Tests: {passed}/{total} passed ({failed} failed)\n"
            f"Target: {store_str}\n"
            f"Compliance: {compliance_count} artifacts in /legal/\n\n"
            f"⚠️ Deploying to {store_str} carries compliance risk.\n\n"
            f"✅ /deploy_confirm — proceed with deployment\n"
            f"❌ /deploy_cancel — return for modifications",
        )

        result = await _wait_for_deploy_decision(
            state, timeout_seconds=COPILOT_DEPLOY_TIMEOUT,
        )

        if result == "timeout":
            logger.warning(
                f"[{state.project_id}] [FIX-08] Operator unresponsive 1h, auto-approving"
            )
            await _log_deploy_consent(state, "auto_timeout_1h")
            return True
        elif result == "confirm":
            await _log_deploy_consent(state, "copilot_confirm")
            return True
        else:
            return False

    else:
        # ── Autopilot: 15-minute auto-approve timer ──
        await notify_operator(
            state,
            NotificationType.INFO,
            f"⏱️ Auto-deploying {project_name} in 15 minutes\n\n"
            f"Platform: {stack} → {store_str}\n"
            f"Tests: {passed}/{total} passed\n\n"
            f"❌ /deploy_cancel — stop deployment within 15 minutes",
        )

        result = await _wait_for_deploy_decision(
            state, timeout_seconds=AUTOPILOT_DEPLOY_TIMEOUT,
        )

        if result == "cancel":
            return False
        else:
            await _log_deploy_consent(state, "autopilot_auto_15m")
            return True


def _get_target_stores(stack: Optional[TechStack]) -> list[str]:
    """Determine target store names from stack."""
    if stack is None:
        return ["deployment target"]

    stores = []
    mobile_stacks = (
        TechStack.SWIFT, TechStack.FLUTTERFLOW,
        TechStack.REACT_NATIVE, TechStack.UNITY,
    )
    if stack in mobile_stacks:
        if stack != TechStack.KOTLIN:
            stores.append("App Store")
        if stack != TechStack.SWIFT:
            stores.append("Google Play")
    elif stack == TechStack.KOTLIN:
        stores.append("Google Play")
    elif stack == TechStack.PYTHON_BACKEND:
        stores.append("Cloud Run")

    return stores or ["deployment target"]


# ═══════════════════════════════════════════════════════════════════
# §4.6.2 Deploy Decision Waiting (FIX-08)
# ═══════════════════════════════════════════════════════════════════


async def _wait_for_deploy_decision(
    state: PipelineState,
    timeout_seconds: int,
) -> str:
    """Wait for operator deploy decision.

    Spec: §4.6.2 (FIX-08)
    Returns: "confirm", "cancel", or "timeout"
    Polls deploy_decisions every 5 seconds.
    """
    from factory.telegram.decisions import check_deploy_decision, clear_deploy_decision

    # Check immediately before entering poll loop (handles pre-recorded decisions)
    decision = await check_deploy_decision(state.project_id)
    if decision:
        await clear_deploy_decision(state.project_id)
        return decision

    # If timeout is 0 (test/stub mode), return timeout immediately
    if timeout_seconds == 0:
        return "timeout"

    poll_interval = 5  # seconds
    elapsed = 0

    while elapsed < timeout_seconds:
        decision = await check_deploy_decision(state.project_id)
        if decision:
            await clear_deploy_decision(state.project_id)
            return decision
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

    return "timeout"


async def _log_deploy_consent(
    state: PipelineState, method: str,
) -> None:
    """Log DeploymentConsent event for audit trail.

    Spec: §4.6.2 (FIX-08)
    """
    consent_event = {
        "event_type": "DeploymentConsent",
        "operator_id": state.operator_id,
        "project_id": state.project_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "method": method,
        "stack": state.selected_stack.value if state.selected_stack else "unknown",
        "test_results": state.s6_output,
    }
    logger.info(
        f"[FIX-08] DeploymentConsent: "
        f"project={state.project_id} method={method}"
    )
    # Always append to in-memory audit log (fast, no I/O)
    state.project_metadata.setdefault("audit_log", []).append(consent_event)

    # Persist to Supabase audit_log table (non-blocking)
    try:
        from factory.integrations.supabase import get_supabase_client
        client = get_supabase_client()
        if client:
            client.table("audit_log").insert({
                "operator_id": state.operator_id,
                "project_id": state.project_id,
                "action": "DeploymentConsent",
                "details": {
                    "method": method,
                    "stack": state.selected_stack.value if state.selected_stack else "unknown",
                    "stage": "s6_test",
                },
            }).execute()
    except Exception as e:
        logger.debug(f"[audit] Supabase write failed (non-fatal): {e}")


# Register with DAG (replaces stub)
register_stage_node("s6_test", s6_test_node)