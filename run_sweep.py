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
from ehbench.tasks.single_turn_mcq import single_turn_mcq
from ehbench.tasks.agentic_discovery import agentic_discovery

# ---------------------------------------------------------------------------
# Condition lists
# ---------------------------------------------------------------------------

SINGLE_TURN_CONDITIONS = [
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

SEQUENTIAL_CONDITIONS = [
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
        choices=["single_turn", "sequential", "agentic", "all"],
        default="all",
        help="Which task type to sweep (default: all).",
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
        "--offset",
        type=int,
        default=0,
        help="Skip the first N questions (single-turn MCQ only). Use to APPEND a "
             "disjoint batch to an earlier run, e.g. --offset 50 --limit 50 adds "
             "questions with ids 51-100 to a prior first-50 run — no re-running.",
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
        "--questions-per-session",
        type=int,
        default=10,
        help="Questions per MCQ session (default: 10). Use 2-3 for smoke tests.",
    )
    parser.add_argument(
        "--conditions",
        nargs="+",
        default=None,
        help="Run only these condition names instead of the full list.",
    )
    parser.add_argument(
        "--dataset",
        default="wmdp-bio",
        help="Dataset name from ehbench.datasets.DATASETS "
             "(wmdp-bio / wmdp-cyber / wmdp-chem). Default: wmdp-bio.",
    )
    parser.add_argument(
        "--no-judge",
        action="store_true",
        help="Skip EH state scoring. Saves raw responses only; use 'inspect score' later to apply judges.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=None,
        help="Cap subject output tokens (runaway protection for heavy reasoners "
             "that can hang). Set well above normal output, e.g. 32000.",
    )
    parser.add_argument(
        "--time-limit",
        type=int,
        default=None,
        help="Per-sample clock-time limit in seconds. A stalled request is "
             "cancelled instead of hanging the run (e.g. 900 for a 15-min cap). "
             "Timed-out samples become errors; the eval still completes.",
    )
    args = parser.parse_args()

    # eval-level options (per-sample time limit + tolerate timed-out samples).
    eval_kwargs: dict = {}
    if args.time_limit:
        eval_kwargs["time_limit"] = args.time_limit
        eval_kwargs["fail_on_error"] = False

    limit = 1 if args.smoke_test else args.limit
    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Build the subject model, optionally with a max_tokens cap. eval() doesn't
    # take max_tokens directly, so it goes on the model's GenerateConfig.
    subject_model = args.model
    if args.max_tokens:
        from inspect_ai.model import get_model, GenerateConfig
        subject_model = get_model(args.model, config=GenerateConfig(max_tokens=args.max_tokens))

    errors: list[str] = []

    # --- Single-turn MCQ sweep ---
    if args.task in ("single_turn", "all"):
        conditions = args.conditions or SINGLE_TURN_CONDITIONS
        print(f"\n{'='*60}")
        print(f"  Single-turn MCQ sweep — {len(conditions)} condition(s)  model={args.model}")
        print(f"{'='*60}")

        for condition in conditions:
            print(f"\n  [{condition}]", flush=True)
            try:
                logs = inspect_eval(
                    single_turn_mcq(
                        condition=condition,
                        limit=limit,
                        offset=args.offset,
                        judge_model=args.judge_model,
                        score_eh=not args.no_judge,
                        dataset=args.dataset,
                    ),
                    model=subject_model,
                    log_dir=str(log_dir),
                    **eval_kwargs,
                )
                if logs:
                    print(f"    → {logs[0].location}")
                    if logs[0].status == "error":
                        msg = f"single_turn/{condition}: eval completed with status=error"
                        print(f"    [ERROR] {msg}")
                        errors.append(msg)
            except Exception as exc:
                msg = f"single_turn/{condition}: {exc}"
                print(f"    [ERROR] {msg}")
                errors.append(msg)

    # --- Sequential MCQ sweep ---
    if args.task in ("sequential", "all"):
        conditions = args.conditions or SEQUENTIAL_CONDITIONS
        print(f"\n{'='*60}")
        print(f"  Sequential MCQ sweep — {len(conditions)} condition(s)  model={args.model}")
        print(f"{'='*60}")

        for condition in conditions:
            print(f"\n  [{condition}]", flush=True)
            try:
                logs = inspect_eval(
                    sequential_mcq(
                        condition=condition,
                        questions_per_session=args.questions_per_session,
                        limit=limit,
                        judge_model=args.judge_model,
                        score_eh=not args.no_judge,
                        dataset=args.dataset,
                    ),
                    model=subject_model,
                    log_dir=str(log_dir),
                    **eval_kwargs,
                )
                if logs:
                    print(f"    → {logs[0].location}")
                    if logs[0].status == "error":
                        msg = f"sequential/{condition}: eval completed with status=error"
                        print(f"    [ERROR] {msg}")
                        errors.append(msg)
            except Exception as exc:
                msg = f"sequential/{condition}: {exc}"
                print(f"    [ERROR] {msg}")
                errors.append(msg)

    # --- Agentic sweep ---
    if args.task in ("agentic", "all"):
        conditions = args.conditions or AGENTIC_CONDITIONS
        print(f"\n{'='*60}")
        print(f"  Agentic sweep — {len(conditions)} condition(s)  model={args.model}")
        print(f"{'='*60}")

        for condition in conditions:
            print(f"\n  [{condition}]", flush=True)
            try:
                logs = inspect_eval(
                    agentic_discovery(
                        condition=condition,
                        model_name=args.model,
                        judge_model=args.judge_model,
                        score_eh=not args.no_judge,
                        dataset=args.dataset,
                        limit=limit,
                        offset=args.offset,
                    ),
                    model=subject_model,
                    log_dir=str(log_dir),
                    **eval_kwargs,
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
