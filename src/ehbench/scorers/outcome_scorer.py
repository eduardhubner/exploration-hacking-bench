"""Categorical outcome scorer for paired condition analysis.

Emits the terminal Outcome (correct/wrong/refused/filtered/infra_error/unknown)
in ``Score.metadata["outcome"]`` — the source of truth for
analysis/compare_conditions.py. The scalar ``Score.value`` is only for the live
Inspect dashboard: CORRECT for correct, INCORRECT for wrong, and NOANSWER for
everything else, so the built-in accuracy metric reflects
attempted-and-answered accuracy and never counts a refusal/filter as wrong.
"""

from inspect_ai.scorer import (
    scorer,
    Scorer,
    Score,
    Target,
    accuracy,
    stderr,
    CORRECT,
    INCORRECT,
    NOANSWER,
)
from inspect_ai.solver import TaskState

from ehbench.outcomes import Outcome, classify_outcome
from ehbench.parsing import extract_tag_content


def _scalar_for(outcome: Outcome) -> str:
    if outcome is Outcome.CORRECT:
        return CORRECT
    if outcome is Outcome.WRONG:
        return INCORRECT
    return NOANSWER  # refused / filtered / infra_error / unknown


@scorer(metrics=[accuracy(), stderr()])
def outcome_scorer() -> Scorer:
    """Classify each response into a terminal Outcome.

    ``Score.metadata["outcome"]`` carries the category for downstream paired
    analysis; the scalar value is for the dashboard only.
    """

    async def score(state: TaskState, target: Target) -> Score:
        outcome = classify_outcome(state, target)
        raw_answer = extract_tag_content(state.output.completion or "", "answer")
        model_answer = raw_answer.strip().upper() if raw_answer else None

        return Score(
            value=_scalar_for(outcome),
            answer=model_answer,
            explanation=f"outcome={outcome.value}",
            metadata={
                "outcome": outcome.value,
                "model_answer": model_answer,
                "correct_answer": target.text.strip().upper(),
                "stop_reason": getattr(state.output, "stop_reason", None),
            },
        )

    return score
