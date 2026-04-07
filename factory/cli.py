"""
AI Factory Pipeline v5.6 — CLI for Local Testing

Usage:
    python -m factory.cli "Build an e-commerce app for KSA"
    python -m factory.cli --mode copilot "Build a delivery app"
    python -m factory.cli --status
    python -m factory.cli --health

Not for production use. Production uses Cloud Run + Telegram.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

# Load .env for local development before any factory imports read env vars
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from factory.core.state import PipelineState, Stage, AutonomyMode
from factory.monitoring.health import health_check, PIPELINE_VERSION
from factory.monitoring.budget_governor import budget_governor
from factory.monitoring.cost_tracker import cost_tracker


def main():
    parser = argparse.ArgumentParser(
        description=f"AI Factory Pipeline v{PIPELINE_VERSION} CLI",
    )
    parser.add_argument(
        "description",
        nargs="?",
        help="App description to build",
    )
    parser.add_argument(
        "--mode",
        choices=["autopilot", "copilot"],
        default="autopilot",
        help="Autonomy mode (default: autopilot)",
    )
    parser.add_argument(
        "--operator",
        default="cli-operator",
        help="Operator ID (default: cli-operator)",
    )
    parser.add_argument(
        "--health",
        action="store_true",
        help="Show health status",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show pipeline status",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose logging",
    )

    args = parser.parse_args()

    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.health:
        result = health_check()
        print(f"Health: {result['status']}")
        print(f"Version: {result['version']}")
        print(f"Timestamp: {result['timestamp']}")
        return

    if args.status:
        status = budget_governor.status()
        print(f"AI Factory Pipeline v{PIPELINE_VERSION}")
        print(f"  Budget tier: {status['tier']}")
        print(f"  Spend: {status['spend_pct']:.1f}%")
        print(f"  Remaining: ${status['remaining_usd']:.2f}")
        print(f"  Monthly cost: ${cost_tracker.monthly_total():.2f}")
        return

    if not args.description:
        parser.print_help()
        print("\nExample: python -m factory.cli \"Build an e-commerce app\"")
        sys.exit(1)

    # Run pipeline
    print(f"AI Factory Pipeline v{PIPELINE_VERSION}")
    print(f"Mode: {args.mode}")
    print(f"Description: {args.description}")
    print("=" * 60)

    from factory.orchestrator import run_pipeline_from_description

    state = asyncio.run(
        run_pipeline_from_description(
            args.description,
            args.operator,
            args.mode,
        )
    )

    print("=" * 60)
    print(f"Project: {state.project_id}")
    print(f"Final stage: {state.current_stage.value}")
    print(f"Total cost: ${state.total_cost_usd:.2f}")
    print(f"Stages: {len(state.stage_history)}")
    print(
        f"War Room: {len(state.war_room_history)} activations, "
        f"{state.retry_count} retries"
    )
    print(
        f"Legal: {len(state.legal_checks_log)} checks, "
        f"{'HALT' if state.legal_halt else 'OK'}"
    )


if __name__ == "__main__":
    main()

def _show_health() -> None:
    """Print pipeline health status to stdout.

    Used by: tests, CLI health check command.
    """
    from factory.config import get_config_summary
    summary = get_config_summary()
    print(f"Status: healthy")
    print(f"Version: {summary['version']}")
    print(f"Pipeline: v{summary.get('pipeline_version', '5.6')}")
    print(f"Region: {summary.get('data_residency', 'me-central1')}")
