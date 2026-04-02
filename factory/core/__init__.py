"""
AI Factory Pipeline v5.6 — Core Module

Public API for the core foundation layer.
All enums, models, contracts, and configuration live here.
"""

from factory.core.state import (
    # Enumerations
    Stage,
    TechStack,
    ExecutionMode,
    AutonomyMode,
    AIRole,
    WarRoomLevel,
    BudgetTier,
    NotificationType,
    # Models
    PipelineState,
    Blueprint,
    AssetRef,
    RoleContract,
    ComplianceGateResult,
    StageExecution,
    # Stack metadata validators
    FlutterFlowMetadata,
    ReactNativeMetadata,
    SwiftMetadata,
    KotlinMetadata,
    UnityMetadata,
    PythonBackendMetadata,
    STACK_METADATA_MAP,
    validate_stack_metadata,
    # Configuration
    VALID_TRANSITIONS,
    BUDGET_CONFIG,
    BUDGET_GUARDRAILS,
    BUDGET_BUFFER_SEGMENTS,
    BUDGET_TIER_THRESHOLDS,
    BUDGET_GOVERNOR_ENABLED,
    MODEL_CONFIG,
    MODEL_OVERRIDES,
    VALID_ANTHROPIC_MODELS,
    ROLE_CONTRACTS,
    PHASE_BUDGET_LIMITS,
    REQUIRED_SECRETS,
    RESEARCH_DEGRADATION_POLICY,
    SCOUT_MAX_CONTEXT_TIER,
    CONTEXT_TIER_LIMITS,
    STACK_SELECTION_CRITERIA,
    TELEGRAM_FILE_LIMIT_MB,
    SOFT_FILE_LIMIT_MB,
    ARTIFACT_TTL_HOURS,
    STRICT_STORE_COMPLIANCE,
    COMPLIANCE_CONFIDENCE_THRESHOLD,
    VECTOR_BACKEND,
    GUI_FAILURE_PIVOT_THRESHOLD,
    CLI_NATIVE_BONUS,
    GUI_AUTOMATION_PENALTY,
    # Functions
    transition_to,
    detect_multi_stack_intent,
    # Exceptions
    IllegalTransition,
    BudgetExceeded,
    BudgetExhaustedError,
    BudgetIntakeBlockedError,
    RoleViolationError,
    UserSpaceViolation,
    SnapshotWriteError,
)

from factory.core.roles import (
    call_ai,
    war_room_escalate,
    set_budget_governor,
)

from factory.core.stages import (
    stage_gate,
    pipeline_node,
    route_after_test,
    route_after_verify,
)

from factory.core.user_space import (
    enforce_user_space,
    validate_file_path,
    sanitize_for_shell,
    PROHIBITED_PATTERNS,
    SAFE_INSTALL_REWRITES,
)

from factory.core.execution import (
    ExecutionModeManager,
    HeartbeatMonitor,
    heartbeat_loop,
    execute_command,
    write_file,
)

from factory.core.secrets import (
    get_secret,
    get_secret_or_raise,
    validate_secrets,
    fetch_from_gcp_secret_manager,
    load_dotenv_if_available,
    SECRET_ROTATION_DAYS,
    DEFERRABLE_SECRETS,
)

__all__ = [
    # Enums
    "Stage", "TechStack", "ExecutionMode", "AutonomyMode", "AIRole",
    "WarRoomLevel", "BudgetTier", "NotificationType",
    # Models
    "PipelineState", "Blueprint", "AssetRef", "RoleContract",
    "ComplianceGateResult", "StageExecution",
    # Functions
    "call_ai", "war_room_escalate", "transition_to",
    "stage_gate", "pipeline_node",
    "enforce_user_space", "execute_command", "write_file",
    "get_secret", "validate_secrets",
    # Config
    "BUDGET_CONFIG", "MODEL_CONFIG", "ROLE_CONTRACTS",
]