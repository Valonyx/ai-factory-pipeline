"""
AI Factory Pipeline v5.6 — Core State Models

Implements:
  - §2.1.1 Core Enumerations (Stage, TechStack, ExecutionMode, AutonomyMode, AIRole)
  - §2.1.2 Valid Stage Transitions (VALID_TRANSITIONS map)
  - §2.1.3 PipelineState (Polymorphic, mutable, Pydantic v2)
  - §2.1.3a AssetRef Model (durable binary asset references)
  - §2.1.3b One-Stack-Per-Project Constraint
  - §2.1.4 Stack Metadata Validators (6 stacks)
  - §2.1.5 Stage Transition Function (transition_to — the ONLY way to change stages)
  - §2.1.6 Stage Gate Decorator (distributed locking via Postgres advisory locks)
  - §2.2.1 RoleContract (frozen dataclass — immutable role boundary)
  - §2.2.4 War Room Levels
  - §2.6  Blueprint Schema (polyglot, consumed by S3–S8)
  - §2.14 Budget Governor Tiers (GREEN/AMBER/RED/BLACK)
  - §2.7.2 pipeline_node decorator (legal hook + snapshot wrapper)

All collection-type fields use Field(default_factory=...).
No mutable default literals (= [] or = {}) anywhere per v5.4.2 [C4].

Spec Authority: v5.6 §2.1–§2.14
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field as dc_field
from datetime import datetime, timezone
from enum import Enum, IntEnum
from functools import wraps
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger("factory.core.state")


# ═══════════════════════════════════════════════════════════════════
# §2.1.1 Core Enumerations
# ═══════════════════════════════════════════════════════════════════


class Stage(str, Enum):
    """Pipeline stages S0–S8 plus terminal states.

    Spec: §2.1.1
    COMPLETED = terminal success — project finished all stages.
    HALTED = terminal failure — requires manual intervention.
    """
    S0_INTAKE     = "S0_INTAKE"
    S1_LEGAL      = "S1_LEGAL"
    S2_BLUEPRINT  = "S2_BLUEPRINT"
    S3_CODEGEN    = "S3_CODEGEN"
    S4_BUILD      = "S4_BUILD"
    S5_TEST       = "S5_TEST"
    S6_DEPLOY     = "S6_DEPLOY"
    S7_VERIFY     = "S7_VERIFY"
    S8_HANDOFF    = "S8_HANDOFF"
    COMPLETED     = "COMPLETED"
    HALTED        = "HALTED"


class TechStack(str, Enum):
    """Supported technology stacks. One per project (§2.1.3b [H4]).

    Spec: §2.1.1, §1.3.4
    """
    FLUTTERFLOW    = "flutterflow"
    REACT_NATIVE   = "react_native"
    SWIFT          = "swift"
    KOTLIN         = "kotlin"
    UNITY          = "unity"
    PYTHON_BACKEND = "python_backend"


class ExecutionMode(str, Enum):
    """Pipeline execution modes.

    Spec: §2.1.1, §2.7 (Three-Mode Execution Layer)
    """
    CLOUD  = "cloud"
    LOCAL  = "local"
    HYBRID = "hybrid"


class AutonomyMode(str, Enum):
    """Operator autonomy modes.

    Spec: §2.1.1, §3.7 (4-Way Decision Matrix)
    AUTOPILOT = full autonomous, pipeline decides everything.
    COPILOT = semi-autonomous, 4-way decision menus via Telegram.
    """
    AUTOPILOT = "autopilot"
    COPILOT   = "copilot"


class AIRole(str, Enum):
    """AI model roles with enforced boundaries.

    Spec: §2.1.1, §2.2 (Eyes vs. Hands Doctrine)
    """
    SCOUT      = "scout"
    STRATEGIST = "strategist"
    ENGINEER   = "engineer"
    QUICK_FIX  = "quick_fix"


class WarRoomLevel(IntEnum):
    """War Room escalation levels.

    Spec: §2.2.4
    L1: Haiku quick fix (~$0.005 illustrative)
    L2: Scout researches → Sonnet applies fix (~$0.10 illustrative)
    L3: Opus orchestrates full rewrite plan (~$0.50 illustrative)
    Cost notes are illustrative — enforcement via circuit breaker §3.6.
    """
    L1_QUICK_FIX = 1
    L2_RESEARCHED = 2
    L3_WAR_ROOM = 3


class BudgetTier(str, Enum):
    """Budget Governor tiers — graduated degradation.

    Spec: §2.14.2
    Thresholds are percentages of BUDGET_CONFIG hard_ceiling_usd ($800).
    """
    GREEN = "GREEN"   # 0–79%: normal operation
    AMBER = "AMBER"   # 80–94%: degrade models
    RED   = "RED"     # 95–99%: block new intake
    BLACK = "BLACK"   # 100%: hard stop


class NotificationType(str, Enum):
    """Telegram notification types for operator alerts.

    Spec: §5.4
    """
    INFO             = "info"
    STAGE_TRANSITION = "stage_transition"
    DECISION_NEEDED  = "decision_needed"
    ERROR            = "error"
    BUDGET_ALERT     = "budget_alert"
    LEGAL_ALERT      = "legal_alert"
    RESEARCH_NEEDED  = "research_needed"
    WAR_ROOM         = "war_room"
    COMPLETION       = "completion"


# ═══════════════════════════════════════════════════════════════════
# §2.1.2 Valid Stage Transitions
# ═══════════════════════════════════════════════════════════════════

VALID_TRANSITIONS: dict[Stage, list[Stage]] = {
    Stage.S0_INTAKE:    [Stage.S1_LEGAL,     Stage.HALTED],
    Stage.S1_LEGAL:     [Stage.S2_BLUEPRINT, Stage.HALTED],
    Stage.S2_BLUEPRINT: [Stage.S3_CODEGEN,   Stage.HALTED],
    Stage.S3_CODEGEN:   [Stage.S4_BUILD,     Stage.HALTED],
    Stage.S4_BUILD:     [Stage.S5_TEST,      Stage.HALTED],
    Stage.S5_TEST:      [Stage.S6_DEPLOY, Stage.S3_CODEGEN, Stage.HALTED],
    Stage.S6_DEPLOY:    [Stage.S7_VERIFY,    Stage.HALTED],
    Stage.S7_VERIFY:    [Stage.S8_HANDOFF, Stage.S6_DEPLOY, Stage.HALTED],
    Stage.S8_HANDOFF:   [Stage.COMPLETED,    Stage.HALTED],
    Stage.COMPLETED:    [],  # Terminal — no outbound transitions
    Stage.HALTED:       [],  # Terminal — requires manual intervention
}


# ═══════════════════════════════════════════════════════════════════
# §2.14 Budget Governor Thresholds
# ═══════════════════════════════════════════════════════════════════

BUDGET_TIER_THRESHOLDS: dict[BudgetTier, int] = {
    BudgetTier.AMBER: 80,
    BudgetTier.RED:   95,
    BudgetTier.BLACK: 100,
}

BUDGET_GOVERNOR_ENABLED: bool = (
    os.getenv("BUDGET_GOVERNOR_ENABLED", "true").lower() == "true"
)


# ═══════════════════════════════════════════════════════════════════
# §2.2.1 Model Configuration (Environment-Driven)
# ═══════════════════════════════════════════════════════════════════

MODEL_CONFIG: dict[str, str] = {
    "strategist":      os.getenv("STRATEGIST_MODEL",       "claude-opus-4-6"),
    "engineer":        os.getenv("ENGINEER_MODEL",          "claude-sonnet-4-5-20250929"),
    "quick_fix":       os.getenv("QUICKFIX_MODEL",          "claude-haiku-4-5-20251001"),
    "gui_supervisor":  os.getenv("GUI_SUPERVISOR_MODEL",    "claude-haiku-4-5-20251001"),
    "scout_search":    os.getenv("SCOUT_MODEL",             "sonar-pro"),
    "scout_reasoning": os.getenv("SCOUT_REASONING_MODEL",   "sonar-reasoning-pro"),
}

MODEL_OVERRIDES: dict[str, Optional[str]] = {
    "strategist": os.getenv("STRATEGIST_MODEL_OVERRIDE"),
    "engineer":   os.getenv("ENGINEER_MODEL_OVERRIDE"),
    "quick_fix":  os.getenv("QUICKFIX_MODEL_OVERRIDE"),
}

VALID_ANTHROPIC_MODELS: set[str] = {
    "claude-opus-4-6",
    "claude-opus-4-5-20250929",
    "claude-sonnet-4-5-20250929",
    "claude-sonnet-4-20250514",
    "claude-haiku-4-5-20251001",
}


# ═══════════════════════════════════════════════════════════════════
# §3.6 Circuit Breaker — Per-Role Phase Budget Limits
# ═══════════════════════════════════════════════════════════════════

PHASE_BUDGET_LIMITS: dict[str, float] = {
    "scout_research":      2.00,
    "strategist_planning": 5.00,
    "design_engine":      10.00,
    "codegen_engineer":   25.00,
    "testing_qa":          8.00,
    "deploy_release":      5.00,
    "legal_guardian":      3.00,
    "war_room_debug":     15.00,
}

BUDGET_GUARDRAILS: dict[str, Any] = {
    "phase_limits": PHASE_BUDGET_LIMITS,
    "per_project_cap_usd":     25.00,
    "monthly_ai_hard_cap":     80.00,
    "monthly_infra_expected": 202.50,
    "macincloud_hours_cap":    20,
    "strategist_calls_cap":     8,
}


# ═══════════════════════════════════════════════════════════════════
# §1.4.0 Canonical Budget Configuration
# ═══════════════════════════════════════════════════════════════════

BUDGET_CONFIG: dict[str, Any] = {
    "version": "5.6",
    "fx_rate": 3.75,  # USD→SAR (SAMA peg since 1986) [V16]

    "fixed_monthly": {
        "neo4j_aura_pro":              65.00,
        "supabase_pro":                25.00,
        "flutterflow_growth":          80.00,
        "domain_dns":                   1.50,
        "apple_developer_monthly":      8.25,
        "cloudflare_tunnel":            0.00,
        "cloud_run":                    0.00,
        "cloud_scheduler":              0.00,
        "github":                       0.00,
        "firebase_spark":               0.00,
        "omniparser_v2":                0.00,
    },

    "variable_monthly_4proj": {
        "anthropic_opus":               5.75,
        "anthropic_sonnet":            21.00,
        "anthropic_haiku":              2.20,
        "perplexity_sonar":             4.60,
        "macincloud_payg":             30.00,
        "ui_tars_openrouter":          12.00,
    },

    "hard_ceiling_usd":  800.00,
    "hard_ceiling_sar": 3000.00,
}

# Computed values (never hardcoded elsewhere)
BUDGET_CONFIG["fixed_subtotal"] = sum(BUDGET_CONFIG["fixed_monthly"].values())
BUDGET_CONFIG["variable_subtotal"] = sum(BUDGET_CONFIG["variable_monthly_4proj"].values())
BUDGET_CONFIG["total_baseline"] = (
    BUDGET_CONFIG["fixed_subtotal"] + BUDGET_CONFIG["variable_subtotal"]
)
BUDGET_CONFIG["total_baseline_sar"] = (
    BUDGET_CONFIG["total_baseline"] * BUDGET_CONFIG["fx_rate"]
)
BUDGET_CONFIG["buffer_remaining"] = (
    BUDGET_CONFIG["hard_ceiling_usd"] - BUDGET_CONFIG["total_baseline"]
)


# ═══════════════════════════════════════════════════════════════════
# Budget Buffer Segments (ADR-048)
# ═══════════════════════════════════════════════════════════════════

BUDGET_BUFFER_SEGMENTS: dict[str, Any] = {
    "version": "5.6",
    "total_buffer_usd": BUDGET_CONFIG["buffer_remaining"],
    "segments": {
        "deterministic_growth": {"usd": 200.00, "pct_of_buffer": 36.7},
        "elastic_spike":        {"usd": 200.00, "pct_of_buffer": 36.7},
        "incident_reserve":     {"usd": 100.00, "pct_of_buffer": 18.4},
        "unallocated":          {"usd": 44.70,  "pct_of_buffer": 8.2},
    },
}


# ═══════════════════════════════════════════════════════════════════
# §2.2.3 Research Degradation Policy
# ═══════════════════════════════════════════════════════════════════

RESEARCH_DEGRADATION_POLICY: dict[str, str] = {
    "primary":    "perplexity_sonar_pro",
    "fallback_1": "cached_verified_sources",
    "fallback_2": "operator_provided_sources",
    "fallback_3": "mark_as_UNVERIFIED",
    # NEVER: "opus_ungrounded_research" — removed per C5
}

SCOUT_MAX_CONTEXT_TIER: str = os.getenv("SCOUT_MAX_CONTEXT_TIER", "medium")

CONTEXT_TIER_LIMITS: dict[str, dict[str, Any]] = {
    "small":  {"max_tokens":  4_000, "search_recency": "week",  "max_sources": 3},
    "medium": {"max_tokens": 16_000, "search_recency": "month", "max_sources": 5},
    "large":  {"max_tokens": 64_000, "search_recency": "year",  "max_sources": 10},
}


# ═══════════════════════════════════════════════════════════════════
# §7.5 File Delivery Constants
# ═══════════════════════════════════════════════════════════════════

TELEGRAM_FILE_LIMIT_MB: int = int(os.getenv("TELEGRAM_FILE_LIMIT_MB", "50"))
SOFT_FILE_LIMIT_MB: int = int(os.getenv("SOFT_FILE_LIMIT_MB", "200"))
ARTIFACT_TTL_HOURS: int = int(os.getenv("ARTIFACT_TTL_HOURS", "72"))


# ═══════════════════════════════════════════════════════════════════
# §7.6 Store Compliance Configuration
# ═══════════════════════════════════════════════════════════════════

STRICT_STORE_COMPLIANCE: bool = (
    os.getenv("STRICT_STORE_COMPLIANCE", "false").lower() == "true"
)
COMPLIANCE_CONFIDENCE_THRESHOLD: float = float(
    os.getenv("COMPLIANCE_CONFIDENCE_THRESHOLD", "0.7")
)


# ═══════════════════════════════════════════════════════════════════
# §6.7.1 Vector Backend Configuration
# ═══════════════════════════════════════════════════════════════════

VECTOR_BACKEND: str = os.getenv("VECTOR_BACKEND", "pgvector")


# ═══════════════════════════════════════════════════════════════════
# §2.11 Secrets — Required Secrets List (Appendix B)
# ═══════════════════════════════════════════════════════════════════

REQUIRED_SECRETS: list[str] = [
    "ANTHROPIC_API_KEY",
    "PERPLEXITY_API_KEY",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_KEY",
    "NEO4J_URI",
    "NEO4J_PASSWORD",
    "GITHUB_TOKEN",
    "TELEGRAM_BOT_TOKEN",
    "GCP_PROJECT_ID",
    "FLUTTERFLOW_API_TOKEN",
    "UI_TARS_ENDPOINT",
    "UI_TARS_API_KEY",
    "APPLE_ID",
    "APP_SPECIFIC_PASSWORD",
    "FIREBASE_SERVICE_ACCOUNT",
]


# ═══════════════════════════════════════════════════════════════════
# Exceptions
# ═══════════════════════════════════════════════════════════════════


class IllegalTransition(Exception):
    """Raised when an invalid stage transition is attempted.

    Spec: §2.1.5
    """
    pass


class BudgetExceeded(Exception):
    """Raised when circuit breaker fires (per-phase or per-project).

    Spec: §3.6
    """
    pass


class BudgetExhaustedError(Exception):
    """Raised when monthly budget hits BLACK tier (100%).

    Spec: §2.14.2
    """
    pass


class BudgetIntakeBlockedError(Exception):
    """Raised when RED tier blocks new S0 Intake.

    Spec: §2.14.2
    """
    pass


class RoleViolationError(Exception):
    """Raised when an AI role attempts an unauthorized action.

    Spec: §2.2.1
    """
    pass


class UserSpaceViolation(Exception):
    """Raised when a command contains prohibited patterns (sudo, etc.).

    Spec: §2.8 (User-Space Enforcer)
    """
    pass


class SnapshotWriteError(Exception):
    """Raised when triple-write fails and is rolled back.

    Spec: §2.9.1
    """
    pass


# ═══════════════════════════════════════════════════════════════════
# §2.2.1 RoleContract (Frozen Dataclass)
# ═══════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class RoleContract:
    """Immutable contract defining what each AI role can and cannot do.

    Spec: §2.2.1
    frozen=True makes this immutable — role boundaries cannot be
    changed at runtime except by creating a new contract instance
    (used by Budget Governor degradation §2.14).
    """
    role: AIRole
    model: str
    can_read_web: bool
    can_write_code: bool
    can_write_files: bool
    can_plan_architecture: bool
    can_decide_legal: bool
    can_manage_war_room: bool
    max_output_tokens: int


# Default role contracts per spec §2.2.1
ROLE_CONTRACTS: dict[AIRole, RoleContract] = {
    AIRole.SCOUT: RoleContract(
        role=AIRole.SCOUT,
        model=MODEL_CONFIG["scout_search"],
        can_read_web=True,
        can_write_code=False,
        can_write_files=False,
        can_plan_architecture=False,
        can_decide_legal=False,
        can_manage_war_room=False,
        max_output_tokens=4096,
    ),
    AIRole.STRATEGIST: RoleContract(
        role=AIRole.STRATEGIST,
        model=MODEL_CONFIG["strategist"],
        can_read_web=False,
        can_write_code=False,
        can_write_files=False,
        can_plan_architecture=True,
        can_decide_legal=True,
        can_manage_war_room=True,
        max_output_tokens=8192,
    ),
    AIRole.ENGINEER: RoleContract(
        role=AIRole.ENGINEER,
        model=MODEL_CONFIG["engineer"],
        can_read_web=False,
        can_write_code=True,
        can_write_files=True,
        can_plan_architecture=False,
        can_decide_legal=False,
        can_manage_war_room=False,
        max_output_tokens=16384,
    ),
    AIRole.QUICK_FIX: RoleContract(
        role=AIRole.QUICK_FIX,
        model=MODEL_CONFIG["quick_fix"],
        can_read_web=False,
        can_write_code=True,
        can_write_files=True,
        can_plan_architecture=False,
        can_decide_legal=False,
        can_manage_war_room=False,
        max_output_tokens=4096,
    ),
}


# ═══════════════════════════════════════════════════════════════════
# §2.1.3a AssetRef Model
# ═══════════════════════════════════════════════════════════════════


class AssetRef(BaseModel):
    """Durable reference to a binary asset in Supabase Storage.

    Spec: §2.1.3a
    Binary assets uploaded via Telegram are immediately persisted
    to Supabase Storage bucket project-assets/{project_id}/.
    Downstream stages reference storage_url — never local paths.
    """
    asset_type: str
    filename: str
    storage_url: str
    uploaded_at: datetime

    @field_validator("asset_type")
    @classmethod
    def validate_type(cls, v: str) -> str:
        allowed = {
            "logo", "screenshot", "voice_memo", "document",
            "icon", "font", "media",
        }
        if v not in allowed:
            raise ValueError(f"asset_type must be one of {allowed}, got '{v}'")
        return v


# ═══════════════════════════════════════════════════════════════════
# §2.1.4 Stack Metadata Validators
# ═══════════════════════════════════════════════════════════════════


class FlutterFlowMetadata(BaseModel):
    """Metadata for FlutterFlow stack projects.

    Spec: §2.1.4
    """
    ff_project_id: str
    ff_pages: list[str]
    ff_collections: list[str]
    ff_api_calls: list[str] = Field(default_factory=list)


class ReactNativeMetadata(BaseModel):
    """Metadata for React Native stack projects.

    Spec: §2.1.4
    """
    expo_project_id: Optional[str] = None
    package_json: dict
    entry_point: str = "App.tsx"
    navigation_lib: str = "react-navigation"
    state_management: str = "zustand"


class SwiftMetadata(BaseModel):
    """Metadata for Swift (iOS native) stack projects.

    Spec: §2.1.4
    """
    xcode_project_path: str
    bundle_id: str
    swift_version: str = "5.10"
    minimum_ios: str = "16.0"
    uses_swiftui: bool = True


class KotlinMetadata(BaseModel):
    """Metadata for Kotlin (Android native) stack projects.

    Spec: §2.1.4
    """
    gradle_project_path: str
    package_name: str
    min_sdk: int = 26
    uses_compose: bool = True


class UnityMetadata(BaseModel):
    """Metadata for Unity (games/AR/VR) stack projects.

    Spec: §2.1.4
    """
    unity_project_path: str
    unity_version: str
    target_platforms: list[str]
    render_pipeline: str = "URP"


class PythonBackendMetadata(BaseModel):
    """Metadata for Python backend (API/data/ML) stack projects.

    Spec: §2.1.4
    """
    framework: str = "fastapi"
    python_version: str = "3.11"
    database: str = "postgresql"
    deploy_target: str = "cloud_run"


STACK_METADATA_MAP: dict[TechStack, type[BaseModel]] = {
    TechStack.FLUTTERFLOW:    FlutterFlowMetadata,
    TechStack.REACT_NATIVE:   ReactNativeMetadata,
    TechStack.SWIFT:          SwiftMetadata,
    TechStack.KOTLIN:         KotlinMetadata,
    TechStack.UNITY:          UnityMetadata,
    TechStack.PYTHON_BACKEND: PythonBackendMetadata,
}


def validate_stack_metadata(state: "PipelineState") -> None:
    """Validate project_metadata matches the selected stack's schema.

    Spec: §2.1.4
    Called at S2 after stack selection to ensure metadata is valid.

    Raises:
        ValueError: If no stack selected or metadata doesn't match schema.
    """
    if state.selected_stack is None:
        raise ValueError("Cannot validate metadata: no stack selected")
    validator_cls = STACK_METADATA_MAP[state.selected_stack]
    validator_cls.model_validate(state.project_metadata)


# ═══════════════════════════════════════════════════════════════════
# §7.6 ComplianceGateResult
# ═══════════════════════════════════════════════════════════════════


class ComplianceGateResult(BaseModel):
    """Structured output from S1 App Store compliance preflight.

    Spec: §7.6.0b [H2]
    """
    platform: str
    overall_pass: bool
    blockers: list[dict] = Field(default_factory=list)
    warnings: list[dict] = Field(default_factory=list)
    guidelines_version: str = ""
    confidence: float = 0.0
    source_ids: list[str] = Field(default_factory=list)

    def should_block(self) -> bool:
        """Block only if STRICT mode AND blockers found AND confidence > threshold.

        Spec: §7.6.0b [H2/FIX-09]
        """
        return (
            STRICT_STORE_COMPLIANCE
            and len(self.blockers) > 0
            and self.confidence > COMPLIANCE_CONFIDENCE_THRESHOLD
        )


# ═══════════════════════════════════════════════════════════════════
# §2.1.6 StageExecution (Idempotency Context)
# ═══════════════════════════════════════════════════════════════════


@dataclass
class StageExecution:
    """Idempotency context for stage execution.

    Spec: §2.1.6 [C6]
    Prevents duplicate execution when concurrent workers trigger.
    """
    stage_run_id: str = dc_field(default_factory=lambda: uuid4().hex)
    project_id: str = ""
    stage: str = ""
    retry_count: int = 0
    dedupe_window_seconds: int = 300


# ═══════════════════════════════════════════════════════════════════
# §2.6 Blueprint Schema (Polyglot)
# ═══════════════════════════════════════════════════════════════════


class Blueprint(BaseModel):
    """Master specification generated at S2. Consumed by S3–S8.

    Spec: §2.6
    The Blueprint is the master specification for a project.
    It is stack-agnostic in structure, with stack-specific
    configuration stored in stack_config.
    """
    model_config = {"validate_assignment": True}

    project_id: str
    app_name: str
    app_description: str
    target_platforms: list[str]
    selected_stack: TechStack

    # Universal fields (all stacks)
    screens: list[dict]
    data_model: list[dict]
    api_endpoints: list[dict]
    auth_method: str
    payment_mode: str = "SANDBOX"
    legal_classification: str
    data_residency: str = "KSA"

    # Stack-specific config
    stack_config: dict = Field(default_factory=dict)

    # Design
    color_palette: dict = Field(default_factory=dict)
    typography: dict = Field(default_factory=dict)
    design_system: str = "material3"

    # Legal
    business_model: Optional[str] = None
    required_legal_docs: list[str] = Field(default_factory=list)
    generated_by: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def enforce_sandbox_default(self) -> "Blueprint":
        """Default payment_mode to SANDBOX. Production requires approval.

        Spec: §2.6
        """
        # Production mode checked at runtime via Mother Memory
        return self

    @model_validator(mode="after")
    def validate_screen_data_bindings(self) -> "Blueprint":
        """Every screen data_binding must reference a valid collection.

        Spec: §2.6
        Catches orphaned screen bindings at blueprint validation time,
        not at build time.
        """
        collection_names = {c["collection"] for c in self.data_model if "collection" in c}
        for screen in self.screens:
            for binding in screen.get("data_bindings", []):
                if (
                    binding.get("collection")
                    and binding["collection"] not in collection_names
                ):
                    raise ValueError(
                        f"Screen '{screen.get('name', '?')}' binds to "
                        f"'{binding['collection']}' which doesn't exist "
                        f"in data_model."
                    )
        return self

    @field_validator("selected_stack")
    @classmethod
    def validate_single_stack(cls, v: Any) -> TechStack:
        """Enforce one-stack-per-project constraint.

        Spec: §2.1.3b [H4]
        """
        if isinstance(v, list):
            raise ValueError(
                "Exactly one stack per project. For multi-stack apps, "
                "use program_id to group related single-stack projects."
            )
        return v


# ═══════════════════════════════════════════════════════════════════
# §2.1.3 PipelineState (Polymorphic)
# ═══════════════════════════════════════════════════════════════════


class PipelineState(BaseModel):
    """Mutable state object carried through LangGraph.

    Spec: §2.1.3
    frozen=False (Pydantic v2 default) — LangGraph requires direct
    field assignment.
    validate_assignment=True — every write triggers Pydantic validation.

    All collection-type fields use Field(default_factory=...) per [C4].
    """
    model_config = {"validate_assignment": True}

    # ── Identity ──
    project_id: str
    operator_id: str
    snapshot_id: Optional[int] = None
    program_id: Optional[str] = None

    # ── Stage Control ──
    current_stage: Stage = Stage.S0_INTAKE
    previous_stage: Optional[Stage] = None
    stage_history: list[dict] = Field(default_factory=list)
    retry_count: int = 0

    # ── Autonomy & Execution ──
    autonomy_mode: AutonomyMode = AutonomyMode.AUTOPILOT
    execution_mode: ExecutionMode = ExecutionMode.CLOUD
    local_heartbeat_alive: bool = False

    # ── Stack Selection (set at S2) ──
    selected_stack: Optional[TechStack] = None

    # ── Polymorphic Metadata ──
    project_metadata: dict[str, Any] = Field(default_factory=dict)

    # ── Brand Assets (durable Supabase Storage) ──
    brand_assets: list[dict] = Field(default_factory=list)

    # ── Continuous Legal Thread ──
    legal_halt: bool = False
    legal_halt_reason: Optional[str] = None
    legal_checks_log: list[dict] = Field(default_factory=list)

    # ── Stage Outputs ──
    s0_output: Optional[dict] = None
    s1_output: Optional[dict] = None
    s2_output: Optional[dict] = None
    s3_output: Optional[dict] = None
    s4_output: Optional[dict] = None
    s5_output: Optional[dict] = None
    s6_output: Optional[dict] = None
    s7_output: Optional[dict] = None
    s8_output: Optional[dict] = None

    # ── Design Mocks (S2) ──
    design_mocks: list[str] = Field(default_factory=list)

    # ── DocuGen Outputs ──
    legal_documents: dict[str, str] = Field(default_factory=dict)

    # ── War Room State ──
    war_room_active: bool = False
    war_room_history: list[dict] = Field(default_factory=list)

    # ── Budget Tracking ──
    phase_costs: dict[str, float] = Field(default_factory=dict)
    total_cost_usd: float = 0.0
    circuit_breaker_triggered: bool = False

    # ── Warnings & Errors ──
    warnings: list[dict] = Field(default_factory=list)
    errors: list[dict] = Field(default_factory=list)

    # ── Timestamps ──
    created_at: str = ""
    updated_at: str = ""

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        if not self.created_at:
            object.__setattr__(
                self, "created_at",
                datetime.now(timezone.utc).isoformat(),
            )
        object.__setattr__(
            self, "updated_at",
            datetime.now(timezone.utc).isoformat(),
        )


# ═══════════════════════════════════════════════════════════════════
# §2.1.5 Stage Transition Function
# ═══════════════════════════════════════════════════════════════════


def transition_to(state: PipelineState, target: Stage) -> None:
    """The ONLY way to change stages.

    Spec: §2.1.5
    Enforces the transition map, checks for legal halts,
    records history, resets retry count on forward progress.

    Args:
        state: Current pipeline state (mutated in place).
        target: Target stage.

    Raises:
        IllegalTransition: If the transition is not in VALID_TRANSITIONS.
    """
    # Check continuous legal halt
    if state.legal_halt and target != Stage.HALTED:
        raise IllegalTransition(
            f"Legal halt active: {state.legal_halt_reason}. "
            f"Only transition to HALTED is allowed."
        )

    current = state.current_stage
    allowed = VALID_TRANSITIONS.get(current, [])
    if target not in allowed:
        raise IllegalTransition(
            f"Cannot transition from {current.value} to {target.value}. "
            f"Allowed: {[s.value for s in allowed]}"
        )

    now = datetime.now(timezone.utc).isoformat()

    # Close current stage in history
    if state.stage_history:
        state.stage_history[-1]["exited_at"] = now

    # Open new stage
    state.stage_history.append({
        "stage": target.value,
        "entered_at": now,
        "exited_at": None,
    })

    state.previous_stage = current
    state.current_stage = target
    state.updated_at = now

    # Reset retry count on forward progress (not on loops)
    stage_order = list(Stage)
    if stage_order.index(target) > stage_order.index(current):
        state.retry_count = 0

    logger.info(
        f"[{state.project_id}] Stage transition: "
        f"{current.value} → {target.value}"
    )


# ═══════════════════════════════════════════════════════════════════
# §2.1.3b Multi-Stack Detection
# ═══════════════════════════════════════════════════════════════════


async def detect_multi_stack_intent(
    requirements: dict,
    state: PipelineState,
) -> Optional[dict]:
    """At S0/S1: detect if brief describes multi-stack solution.

    Spec: §2.1.3b [H4]
    If the brief describes multiple stacks, propose a program split
    instead of a single project.

    Returns:
        None if single-stack, or dict with program_id and sub_projects.
    """
    # Lazy import to avoid circular dependency
    from factory.core.roles import call_ai

    indicators = [
        "game" in str(requirements).lower()
        and "companion" in str(requirements).lower(),
        len(requirements.get("target_platforms", [])) > 2,
        any(
            w in str(requirements).lower()
            for w in ["backend api + mobile", "web + native", "multiple apps"]
        ),
    ]

    if sum(indicators) >= 2:
        split_proposal = await call_ai(
            role=AIRole.STRATEGIST,
            prompt=(
                f"This project brief describes a multi-stack solution.\n"
                f"Requirements: {json.dumps(requirements, indent=2)}\n\n"
                f"Split into separate single-stack projects. For each:\n"
                f"- project_suffix (e.g., '-game', '-companion', '-api')\n"
                f"- selected_stack (one TechStack enum)\n"
                f"- shared_interfaces (API contracts between sub-projects)\n"
                f'Return JSON: {{"program_id": "<name>", "sub_projects": [...]}}'
            ),
            state=state,
            action="plan_architecture",
        )
        try:
            return json.loads(split_proposal)
        except json.JSONDecodeError:
            logger.error(
                f"Failed to parse multi-stack proposal: {split_proposal[:200]}"
            )
            return None
    return None


# ═══════════════════════════════════════════════════════════════════
# §2.8 Stack Selection Criteria
# ═══════════════════════════════════════════════════════════════════

STACK_SELECTION_CRITERIA: dict[str, dict[str, Any]] = {
    "flutterflow": {
        "keywords": ["rapid mvp", "crud", "simple", "no-code", "low-code"],
        "complexity_max": "medium",
        "base_score": 70,
        "requires_gui_automation": True,
    },
    "react_native": {
        "keywords": ["cross-platform", "custom ui", "javascript", "web-first"],
        "complexity_max": "high",
        "base_score": 65,
        "requires_gui_automation": False,
    },
    "swift": {
        "keywords": ["ios only", "arkit", "healthkit", "apple", "premium"],
        "complexity_max": "high",
        "base_score": 60,
        "requires_gui_automation": False,
    },
    "kotlin": {
        "keywords": ["android only", "jetpack", "compose", "material"],
        "complexity_max": "high",
        "base_score": 60,
        "requires_gui_automation": False,
    },
    "unity": {
        "keywords": ["game", "3d", "ar", "vr", "augmented", "virtual"],
        "complexity_max": "high",
        "base_score": 55,
        "requires_gui_automation": False,
    },
    "python_backend": {
        "keywords": ["api", "backend", "data", "ml", "machine learning", "pipeline"],
        "complexity_max": "high",
        "base_score": 65,
        "requires_gui_automation": False,
    },
}

# GUI Stack Pivot threshold [H3]: 3 consecutive GUI failures
# trigger War Room L3 and CLI-native stack proposal.
GUI_FAILURE_PIVOT_THRESHOLD: int = 3
CLI_NATIVE_BONUS: int = 15
GUI_AUTOMATION_PENALTY: int = -10