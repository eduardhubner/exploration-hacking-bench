"""Run a full sweep of all EH capability stage conditions.

Iterates over every condition in the MCQ (sequential_mcq) and/or agentic
discovery tasks and saves Inspect AI logs to the output directory.

Usage
-----
    # Full sweep, both tasks:
    python run_sweep.py --model anthropic/claude-sonnet-4-6

    # Smoke test (1 sample per condition):
    python run_sweep.py --model anthropic/claude-sonnet-4-6 --smoke-test

    # MCQ only, 5 sessions per condition:
    python run_sweep.py --model anthropic/claude-sonnet-4-6 --task mcq --limit 5

    # Agentic only, separate judge model:
    python run_sweep.py --model anthropic/claude-sonnet-4-6 --task agentic \\
        --judge-model anthropic/claude-haiku-4-5-20251001
"""

import argparse
import os
import sys
from pathlib import Path

# Allow running from project root without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

os.environ.setdefault("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")

from inspect_ai import eval as inspect_eval  # type: ignore[import]

from ehbench.tasks.sequential_mcq import sequential_mcq
from ehbench.tasks.agentic_discovery import agentic_discovery

# ---------------------------------------------------------------------------
# Condition lists
# ---------------------------------------------------------------------------

MCQ_CONDITIONS = [
    "baseline",
    "level2_training_awareness",
    "level3_goal_conflict_tm1",
    "level3_goal_conflict_tm2",
    "level4_action_knowledge_tm1",
    "level4_action_knowledge_tm2",
    "level5_desire_nudge_tm1",
    "level5_desire_nudge_tm2",
    "level6_explicit_instruction",
]

AGENTIC_CONDITIONS = [
    "level2",
    "level3-tm1",
    "level3-tm2",
    "level4-tm1",
    "level4-tm2",
    "level5-tm1",
    "level5-tm2",
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run full EH capability stage sweep across all conditions."
    )
    parser.add_argument(
        "--model",
        required=True,
        help="Model ID passed to Inspect AI (e.g. anthropic/claude-sonnet-4-6).",
    )
    parser.add_argument(
        "--task",
        choices=["mcq", "agentic", "both"],
        default="both",
        help="Which task type to sweep (default: both).",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Run with limit=1 per condition for a quick end-to-end check.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max samples per condition (overridden by --smoke-test).",
    )
    parser.add_argument(
        "--log-dir",
        default="logs",
        help="Directory to write Inspect AI logs (default: logs/).",
    )
    parser.add_argument(
        "--judge-model",
        default=None,
        help="Model ID to use as the EH judge. Defaults to the eval model.",
    )
    parser.add_argument(
        "--conditions",
        nargs="+",
        default=None,
        help="Run only these condition names instead of the full list.",
    )
    args = parser.parse_args()

    limit = 1 if args.smoke_test else args.limit
    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    errors: list[str] = []

    # --- MCQ sweep ---
    if args.task in ("mcq", "both"):
        conditions = args.conditions or MCQ_CONDITIONS
        print(f"\n{'='*60}")
        print(f"  MCQ sweep — {len(conditions)} condition(s)  model={args.model}")
        print(f"{'='*60}")

        for condition in conditions:
            print(f"\n  [{condition}]", flush=True)
            try:
                logs = inspect_eval(
                    sequential_mcq(
                        condition=condition,
                        limit=limit,
                        judge_model=args.judge_model,
                    ),
                    model=args.model,
                    log_dir=str(log_dir),
                )
                if logs:
                    print(f"    → {logs[0].location}")
                    if logs[0].status == "error":
                        msg = f"MCQ/{condition}: eval completed with status=error"
                        print(f"    [ERROR] {msg}")
                        errors.append(msg)
            except Exception as exc:
                msg = f"MCQ/{condition}: {exc}"
                print(f"    [ERROR] {msg}")
                errors.append(msg)

    # --- Agentic sweep ---
    if args.task in ("agentic", "both"):
        conditions = args.conditions or AGENTIC_CONDITIONS
        print(f"\n{'='*60}")
        print(f"  Agentic sweep — {len(conditions)} condition(s)  model={args.model}")
        print(f"{'='*60}")

        for condition in conditions:
            print(f"\n  [{condition}]", flush=True)
            try:
                logs = inspect_eval(
                    agentic_discovery(condition=condition),
                    model=args.model,
                    log_dir=str(log_dir),
                    limit=limit,
                )
                if logs:
                    print(f"    → {logs[0].location}")
                    if logs[0].status == "error":
                        msg = f"agentic/{condition}: eval completed with status=error"
                        print(f"    [ERROR] {msg}")
                        errors.append(msg)
            except Exception as exc:
                msg = f"agentic/{condition}: {exc}"
                print(f"    [ERROR] {msg}")
                errors.append(msg)

    # --- Summary ---
    print(f"\n{'='*60}")
    if errors:
        print(f"  Completed with {len(errors)} error(s):")
        for e in errors:
            print(f"    • {e}")
        sys.exit(1)
    else:
        print("  All conditions completed successfully.")


if __name__ == "__main__":
    main()
