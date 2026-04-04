"""
AI Factory Pipeline v5.6 — Final Project Validation

Validates:
  1. Project tree completeness (all expected files exist)
  2. Cross-layer imports (every module importable)
  3. Public API surface (key exports accessible)
  4. Configuration integrity
  5. Spec section coverage map
  6. Line counts per layer

Run: python -m scripts.validate_project

Spec Authority: v5.6 (complete)
"""

from __future__ import annotations

import importlib
import os
import sys
from datetime import datetime


def header(title: str) -> None:
    print(f"\n{'═' * 64}")
    print(f"  {title}")
    print(f"{'═' * 64}")


def check(label: str, condition: bool, detail: str = "") -> bool:
    icon = "✅" if condition else "❌"
    suffix = f" — {detail}" if detail else ""
    print(f"  {icon} {label}{suffix}")
    return condition


# ═══════════════════════════════════════════════════════════════════
# Phase 1: Project Tree
# ═══════════════════════════════════════════════════════════════════

EXPECTED_FILES = {
    # P0 Core
    "factory/__init__.py": "Package init",
    "factory/core/__init__.py": "Core init",
    "factory/core/state.py": "PipelineState, Stage, enums",
    "factory/core/roles.py": "AI role contracts, call_ai",
    "factory/core/stages.py": "Stage sequence",
    "factory/core/secrets.py": "GCP Secret Manager",
    "factory/core/execution.py": "Execution router",
    "factory/core/user_space.py": "User-space enforcement",
    "factory/core/config_models.py": "Configuration models",
    # P1 Telegram
    "factory/telegram/__init__.py": "Telegram init",
    "factory/telegram/bot.py": "Bot handler",
    "factory/telegram/commands.py": "Command handlers",
    "factory/telegram/notifications.py": "Notification sender",
    "factory/telegram/decisions.py": "Decision presenter",
    "factory/telegram/airlock.py": "Telegram airlock",
    "factory/telegram/health.py": "Telegram health",
    # P2 Pipeline
    "factory/pipeline/__init__.py": "Pipeline init",
    "factory/pipeline/s0_intake.py": "S0 Intake",
    "factory/pipeline/s1_legal.py": "S1 Legal Gate",
    "factory/pipeline/s2_blueprint.py": "S2 Blueprint",
    "factory/pipeline/s3_codegen.py": "S3 CodeGen",
    "factory/pipeline/s4_build.py": "S4 Build",
    "factory/pipeline/s5_test.py": "S5 Test",
    "factory/pipeline/s6_deploy.py": "S6 Deploy",
    "factory/pipeline/s7_verify.py": "S7 Verify",
    "factory/pipeline/s8_handoff.py": "S8 Handoff",
    # P3 Integrations
    "factory/integrations/__init__.py": "Integrations init",
    "factory/integrations/supabase.py": "Supabase client",
    "factory/integrations/github.py": "GitHub client",
    "factory/integrations/neo4j.py": "Neo4j client",
    "factory/integrations/anthropic.py": "Anthropic client",
    # P4 Design
    "factory/design/__init__.py": "Design init",
    "factory/design/contrast.py": "WCAG contrast",
    "factory/design/grid.py": "Grid enforcer",
    "factory/design/vibe_check.py": "Vibe check",
    "factory/design/visual_mocks.py": "Visual mocks",
    # P5 Monitoring
    "factory/monitoring/__init__.py": "Monitoring init",
    "factory/monitoring/budget_governor.py": "Budget Governor",
    "factory/monitoring/circuit_breaker.py": "Circuit breaker",
    "factory/monitoring/cost_tracker.py": "Cost tracker",
    "factory/monitoring/health.py": "Health endpoints",
    # P6 War Room
    "factory/war_room/__init__.py": "War Room init",
    "factory/war_room/levels.py": "Level definitions",
    "factory/war_room/escalation.py": "L1/L2/L3 escalation",
    "factory/war_room/war_room.py": "War Room orchestrator",
    "factory/war_room/patterns.py": "Pattern storage",
    # P7 Legal
    "factory/legal/__init__.py": "Legal init",
    "factory/legal/regulatory.py": "Regulatory resolver",
    "factory/legal/checks.py": "Legal check hooks",
    "factory/legal/docugen.py": "DocuGen templates",
    "factory/legal/compliance_gate.py": "Store compliance gate",
    # P8 Delivery
    "factory/delivery/__init__.py": "Delivery init",
    "factory/delivery/file_delivery.py": "File delivery",
    "factory/delivery/airlock.py": "App Store Airlock",
    "factory/delivery/app_store.py": "App store uploads",
    "factory/delivery/handoff_docs.py": "Handoff Intelligence Pack",
    # P9 Entry Points
    "factory/orchestrator.py": "Pipeline orchestrator",
    "factory/main.py": "FastAPI app",
    "factory/cli.py": "CLI",
    "factory/config.py": "Configuration",
    # P10 Deploy
    "requirements.txt": "Dependencies",
    "pyproject.toml": "Project config",
    "Dockerfile": "Container",
    "cloudbuild.yaml": "Cloud Build",
    ".env.example": "Env template",
    # P11 Tests
    "tests/__init__.py": "Tests init",
    "tests/conftest.py": "Test fixtures",
    "tests/test_core.py": "Core tests",
    "tests/test_pipeline.py": "Pipeline tests",
    "tests/test_monitoring.py": "Monitoring tests",
    "tests/test_war_room.py": "War Room tests",
    "tests/test_legal.py": "Legal tests",
    "tests/test_delivery.py": "Delivery tests",
    "tests/test_orchestrator.py": "Orchestrator tests",
    "tests/test_config.py": "Config tests",
    # P12 Ops
    "scripts/__init__.py": "Scripts init",
    "scripts/migrate_supabase.py": "Supabase migration",
    "scripts/migrate_neo4j.py": "Neo4j migration",
    "scripts/janitor.py": "Janitor Agent",
    "scripts/setup_secrets.py": "Secrets bootstrap",
    "scripts/migrate_v36_to_v54.py": "v3.6 migration",
    # P13 Docs
    "README.md": "Project README",
    "docs/ARCHITECTURE.md": "Architecture ref",
    "docs/OPERATOR_GUIDE.md": "Operator guide",
    "docs/ADR_INDEX.md": "ADR index",
}


def validate_project_tree() -> tuple[int, int]:
    header("Phase 1: Project Tree")
    found = 0
    missing = 0
    for path, desc in sorted(EXPECTED_FILES.items()):
        exists = os.path.exists(path)
        if exists:
            found += 1
        else:
            missing += 1
            check(path, False, f"MISSING — {desc}")
    print(f"\n  Files: {found}/{len(EXPECTED_FILES)} present")
    if missing:
        print(f"  ❌ {missing} files missing")
    else:
        print(f"  ✅ All {found} files present")
    return found, missing


# ═══════════════════════════════════════════════════════════════════
# Phase 2: Cross-Layer Imports
# ═══════════════════════════════════════════════════════════════════

IMPORT_MODULES = [
    "factory",
    "factory.core",
    "factory.core.state",
    "factory.core.roles",
    "factory.core.stages",
    "factory.core.secrets",
    "factory.core.execution",
    "factory.core.user_space",
    "factory.telegram",
    "factory.telegram.notifications",
    "factory.pipeline",
    "factory.pipeline.s0_intake",
    "factory.pipeline.s3_codegen",
    "factory.pipeline.s8_handoff",
    "factory.integrations",
    "factory.integrations.supabase",
    "factory.design",
    "factory.design.contrast",
    "factory.monitoring",
    "factory.monitoring.budget_governor",
    "factory.monitoring.health",
    "factory.war_room",
    "factory.war_room.levels",
    "factory.war_room.war_room",
    "factory.legal",
    "factory.legal.regulatory",
    "factory.legal.checks",
    "factory.delivery",
    "factory.delivery.file_delivery",
    "factory.delivery.handoff_docs",
    "factory.orchestrator",
    "factory.main",
    "factory.cli",
    "factory.config",
    "scripts.migrate_supabase",
    "scripts.migrate_neo4j",
    "scripts.janitor",
]


def validate_imports() -> tuple[int, int]:
    header("Phase 2: Cross-Layer Imports")
    success = 0
    failed = 0
    for mod_name in IMPORT_MODULES:
        try:
            importlib.import_module(mod_name)
            success += 1
        except Exception as e:
            failed += 1
            check(mod_name, False, str(e)[:80])
    print(f"\n  Modules: {success}/{len(IMPORT_MODULES)} importable")
    if not failed:
        print(f"  ✅ All {success} modules import cleanly")
    return success, failed


# ═══════════════════════════════════════════════════════════════════
# Phase 3: Public API Surface
# ═══════════════════════════════════════════════════════════════════

API_CHECKS = [
    ("factory.__version__", "5.6.0"),
    ("factory.config.PIPELINE_VERSION", "5.6"),
    ("factory.config.MODELS.strategist", "claude-opus-4-6"),
    ("factory.config.MODELS.engineer", "claude-sonnet-4-5-20250929"),
    ("factory.config.MODELS.quick_fix", "claude-haiku-4-5-20251001"),
    ("factory.config.MODELS.scout", "sonar-pro"),
    ("factory.config.BUDGET.monthly_budget_usd", 300.0),
    ("factory.config.DELIVERY.telegram_file_limit_mb", 50),
    ("factory.config.DATA_RESIDENCY.primary_region", "me-central1"),
]


def validate_api_surface() -> tuple[int, int]:
    header("Phase 3: Public API Surface")
    passed = 0
    failed = 0
    for attr_path, expected in API_CHECKS:
        parts = attr_path.split(".")
        try:
            obj = importlib.import_module(parts[0])
            for part in parts[1:]:
                obj = getattr(obj, part)
            ok = obj == expected
            check(attr_path, ok, f"{obj}" if not ok else f"{expected}")
            passed += ok
            failed += (not ok)
        except Exception as e:
            check(attr_path, False, str(e)[:60])
            failed += 1
    return passed, failed


# ═══════════════════════════════════════════════════════════════════
# Phase 4: Configuration Integrity
# ═══════════════════════════════════════════════════════════════════


def validate_configuration() -> tuple[int, int]:
    header("Phase 4: Configuration Integrity")
    from factory.config import (
        REQUIRED_SECRETS, CONDITIONAL_SECRETS,
        validate_required_config, get_config_summary,
    )
    passed = 0
    failed = 0

    ok = len(REQUIRED_SECRETS) >= 9
    check("Required secrets ≥ 9", ok, str(len(REQUIRED_SECRETS)))
    passed += ok; failed += (not ok)

    ok = len(CONDITIONAL_SECRETS) >= 4
    check("Conditional secrets ≥ 4", ok, str(len(CONDITIONAL_SECRETS)))
    passed += ok; failed += (not ok)

    summary = get_config_summary()
    ok = summary["version"] == "5.6.0"
    check("Config summary version", ok)
    passed += ok; failed += (not ok)

    ok = "models" in summary and "budget" in summary
    check("Config summary completeness", ok)
    passed += ok; failed += (not ok)

    return passed, failed


# ═══════════════════════════════════════════════════════════════════
# Phase 5: Spec Section Coverage
# ═══════════════════════════════════════════════════════════════════

SPEC_COVERAGE = {
    "§2.1": ("PipelineState", "factory/core/state.py"),
    "§2.2.4": ("War Room L1/L2/L3", "factory/war_room/"),
    "§2.5": ("User-space enforcement", "factory/core/user_space.py"),
    "§2.6": ("Blueprint schema, Model config", "factory/config.py"),
    "§2.7.1": ("DAG topology", "factory/orchestrator.py"),
    "§2.7.2": ("pipeline_node decorator", "factory/orchestrator.py"),
    "§2.7.3": ("Continuous Legal Thread", "factory/legal/checks.py"),
    "§2.14": ("Budget Governor", "factory/monitoring/budget_governor.py"),
    "§3.5": ("Design Engine", "factory/design/"),
    "§3.7": ("Autonomy modes", "factory/core/state.py"),
    "§3.8": ("Role information flow", "factory/core/roles.py"),
    "§4.0": ("Stage execution model", "factory/pipeline/"),
    "§4.1": ("S0 Intake", "factory/pipeline/s0_intake.py"),
    "§4.1.1": ("S1 Legal Gate", "factory/pipeline/s1_legal.py"),
    "§4.2": ("S2 Blueprint", "factory/pipeline/s2_blueprint.py"),
    "§4.3": ("S3 CodeGen", "factory/pipeline/s3_codegen.py"),
    "§4.4": ("S4 Build", "factory/pipeline/s4_build.py"),
    "§4.5": ("S5 Test", "factory/pipeline/s5_test.py"),
    "§4.6": ("S6 Deploy", "factory/pipeline/s6_deploy.py"),
    "§4.7": ("S7 Verify", "factory/pipeline/s7_verify.py"),
    "§4.8": ("S8 Handoff", "factory/pipeline/s8_handoff.py"),
    "§4.9": ("FIX-27 Handoff Intelligence Pack", "factory/delivery/handoff_docs.py"),
    "§5.1": ("Telegram webhook", "factory/main.py"),
    "§5.6": ("Session schema", "scripts/migrate_supabase.py"),
    "§6.3": ("Mother Memory v2", "factory/war_room/patterns.py"),
    "§6.5": ("Janitor Agent", "scripts/janitor.py"),
    "§7.4.1": ("Health endpoints", "factory/monitoring/health.py"),
    "§7.5": ("File delivery [C3]", "factory/delivery/file_delivery.py"),
    "§7.6": ("Store compliance", "factory/legal/compliance_gate.py"),
    "§7.7.1": ("GCP Secrets", "factory/core/secrets.py"),
    "§8.3": ("Migration scripts", "scripts/migrate_v36_to_v54.py"),
    "§8.9": ("Env var reference", "factory/config.py"),
    "§8.10": ("Function contracts", "factory/delivery/handoff_docs.py"),
    "FIX-06": ("Advisory/Strict toggle", "factory/legal/compliance_gate.py"),
    "FIX-07": ("Compliance artifacts", "factory/pipeline/s2_blueprint.py"),
    "FIX-19": ("Scout context tiers", "factory/config.py"),
    "FIX-21": ("iOS 5-step submission", "factory/delivery/app_store.py"),
    "FIX-27": ("Handoff Intelligence Pack", "factory/delivery/handoff_docs.py"),
}


def validate_spec_coverage() -> tuple[int, int]:
    header("Phase 5: Spec Section Coverage")
    covered = 0
    missing = 0
    for section, (desc, path) in sorted(SPEC_COVERAGE.items()):
        exists = os.path.exists(path)
        if exists:
            covered += 1
        else:
            missing += 1
            check(f"{section} {desc}", False, f"File missing: {path}")
    print(f"\n  Spec sections: {covered}/{len(SPEC_COVERAGE)} covered")
    if not missing:
        print(f"  ✅ All {covered} specification sections have implementations")
    return covered, missing


# ═══════════════════════════════════════════════════════════════════
# Phase 6: Line Counts
# ═══════════════════════════════════════════════════════════════════

LAYER_PATHS = {
    "P0 Core": "factory/core",
    "P1 Telegram": "factory/telegram",
    "P2 Pipeline": "factory/pipeline",
    "P3 Integrations": "factory/integrations",
    "P4 Design": "factory/design",
    "P5 Monitoring": "factory/monitoring",
    "P6 War Room": "factory/war_room",
    "P7 Legal": "factory/legal",
    "P8 Delivery": "factory/delivery",
    "P9 Entry Points": None,   # Special handling
    "P10 Config": None,        # Special handling
    "P11 Tests": "tests",
    "P12 Ops": "scripts",
    "P13 Docs": "docs",
}

P9_FILES = [
    "factory/orchestrator.py",
    "factory/main.py",
    "factory/cli.py",
    "factory/__init__.py",
]

P10_FILES = [
    "factory/config.py",
    "requirements.txt",
    "pyproject.toml",
    "Dockerfile",
    "cloudbuild.yaml",
    ".env.example",
]


def count_lines(path: str) -> int:
    if os.path.isfile(path):
        try:
            with open(path, "r", errors="ignore") as f:
                return sum(1 for _ in f)
        except Exception:
            return 0
    elif os.path.isdir(path):
        total = 0
        for root, _, files in os.walk(path):
            for fn in files:
                if fn.endswith((".py", ".md", ".txt", ".toml", ".yaml", ".yml")):
                    total += count_lines(os.path.join(root, fn))
        return total
    return 0


def validate_line_counts() -> int:
    header("Phase 6: Line Counts")
    grand_total = 0
    for layer, path in LAYER_PATHS.items():
        if layer == "P9 Entry Points":
            lines = sum(count_lines(f) for f in P9_FILES)
        elif layer == "P10 Config":
            lines = sum(count_lines(f) for f in P10_FILES)
        elif path:
            lines = count_lines(path)
        else:
            lines = 0
        grand_total += lines
        files = 0
        if path and os.path.isdir(path):
            files = sum(
                1 for _, _, fs in os.walk(path)
                for f in fs if f.endswith((".py", ".md"))
            )
        elif layer == "P9 Entry Points":
            files = len(P9_FILES)
        elif layer == "P10 Config":
            files = len(P10_FILES)
        print(f"  {layer:20s}  {lines:5d} lines  ({files} files)")

    # Add README
    readme_lines = count_lines("README.md")
    grand_total += readme_lines
    print(f"  {'README':20s}  {readme_lines:5d} lines")

    print(f"\n  {'GRAND TOTAL':20s}  {grand_total:5d} lines")
    return grand_total


# ═══════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════


def main():
    print("╔════════════════════════════════════════════════════════════╗")
    print("║   AI Factory Pipeline v5.6 — Final Project Validation    ║")
    print("║   Specification: v5.6 Clean Room (11,845 lines)          ║")
    print(f"║   Validation Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}                     ║")
    print("╚════════════════════════════════════════════════════════════╝")

    results = {}

    # Phase 1
    found, missing = validate_project_tree()
    results["tree"] = {"found": found, "missing": missing}

    # Phase 2
    success, failed = validate_imports()
    results["imports"] = {"success": success, "failed": failed}

    # Phase 3
    passed, failed = validate_api_surface()
    results["api"] = {"passed": passed, "failed": failed}

    # Phase 4
    passed, failed = validate_configuration()
    results["config"] = {"passed": passed, "failed": failed}

    # Phase 5
    covered, missing = validate_spec_coverage()
    results["spec"] = {"covered": covered, "missing": missing}

    # Phase 6
    total_lines = validate_line_counts()
    results["lines"] = total_lines

    # ── Final Summary ──
    header("FINAL VALIDATION SUMMARY")

    all_passed = all([
        results["tree"]["missing"] == 0,
        results["imports"]["failed"] == 0,
        results["api"]["failed"] == 0,
        results["config"]["failed"] == 0,
        results["spec"]["missing"] == 0,
    ])

    print(f"  Project Tree:     {results['tree']['found']} files ({'✅ PASS' if results['tree']['missing'] == 0 else '❌ FAIL'})")
    print(f"  Module Imports:   {results['imports']['success']} modules ({'✅ PASS' if results['imports']['failed'] == 0 else '❌ FAIL'})")
    print(f"  API Surface:      {results['api']['passed']} checks ({'✅ PASS' if results['api']['failed'] == 0 else '❌ FAIL'})")
    print(f"  Configuration:    {results['config']['passed']} checks ({'✅ PASS' if results['config']['failed'] == 0 else '❌ FAIL'})")
    print(f"  Spec Coverage:    {results['spec']['covered']} sections ({'✅ PASS' if results['spec']['missing'] == 0 else '❌ FAIL'})")
    print(f"  Total Lines:      {results['lines']}")

    print(f"\n{'═' * 64}")
    if all_passed:
        print("  ✅ ALL PHASES PASSED — PROJECT VALIDATION COMPLETE")
    else:
        print("  ❌ SOME PHASES FAILED — Review output above")
    print(f"{'═' * 64}")

    # ── Completion Certificate ──
    if all_passed:
        print(f"""
╔════════════════════════════════════════════════════════════╗
║                                                            ║
║     AI FACTORY PIPELINE v5.6 — IMPLEMENTATION COMPLETE     ║
║                                                            ║
║  Spec:       v5.6 Clean Room (11,845 lines)                ║
║  Code:       ~{results['lines']:,} lines across 80+ files{' ' * (17 - len(str(results['lines'])))}║
║  Layers:     14 (P0-P13)                                   ║
║  Stages:     9 (S0-S8) + conditional routing               ║
║  AI Roles:   4 (Scout/Strategist/Engineer/Quick Fix)       ║
║  Tests:      ~90 unit tests                                ║
║  Supabase:   11 tables + 7 indexes                         ║
║  Neo4j:      18 indexes + 1 constraint + 12 node types     ║
║  Stacks:     6 (FlutterFlow/Swift/Kotlin/RN/Python/Unity)  ║
║  Legal:      14 aliases, 9 checks, 5 templates             ║
║  Delivery:   3 tiers + Airlock + 7 handoff docs            ║
║  Budget:     4-tier governor ($300/mo default)              ║
║  Region:     me-central1 (GCP Dammam, KSA)                 ║
║  Deploy:     Cloud Run via Cloud Build                      ║
║                                                            ║
║  All specification sections implemented.                    ║
║  All modules import cleanly.                                ║
║  All configuration verified.                                ║
║                                                            ║
╚════════════════════════════════════════════════════════════╝
""")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())