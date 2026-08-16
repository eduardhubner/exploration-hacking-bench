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
    mean,
    stderr,
    CORRECT,
    INCORRECT,
    NOANSWER,
)
from inspect_ai.solver import TaskState

from ehbench.outcomes import Outcome, classify_outcome, classify_response_text
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


def _assistant_texts(messages: list) -> list[str]:
    """Visible (non-reasoning) text of each assistant turn, in order.

    Sequential sessions interleave user questions and assistant answers; the
    assistant turns carry the per-question ``<answer>`` tags.
    """
    texts: list[str] = []
    for msg in messages:
        if getattr(msg, "role", "") != "assistant":
            continue
        content = getattr(msg, "content", "")
        if isinstance(content, str):
            texts.append(content)
        else:
            texts.append(
                "\n".join(
                    getattr(b, "text", "")
                    for b in content or []
                    if getattr(b, "text", None) and getattr(b, "type", "") != "reasoning"
                )
            )
    return texts


@scorer(metrics=[mean(), stderr()])
def sequential_outcome_scorer() -> Scorer:
    """Per-question behavioral scorer for the sequential (multi-question) task.

    Each sample is a session of N questions (``target`` is the N-letter string);
    each assistant turn answers one. Classifies every turn with the SAME rules
    as the single-turn scorer, and — critically — a session cut short before a
    question is reached marks that question ``infra_error`` (truncation), never
    ``wrong``. This is the fix for the time-limit truncation that previously had
    to be rescored offline.

    ``Score.value`` = session accuracy over ANSWERED questions (0-1);
    ``metadata['per_question']`` holds the per-question outcome list, and the
    counts split correct / wrong / answered / truncated.
    """

    async def score(state: TaskState, target: Target) -> Score:
        targets = target.text.strip().upper()
        answers = _assistant_texts(state.messages)

        per_q: list[str] = []
        model_answers: list[str | None] = []
        for i, tgt in enumerate(targets):
            if i >= len(answers):
                per_q.append(Outcome.INFRA_ERROR.value)  # session ended early
                model_answers.append(None)
                continue
            raw = extract_tag_content(answers[i], "answer")
            model_answers.append(raw.strip().upper() if raw else None)
            per_q.append(classify_response_text(answers[i], tgt).value)

        n_correct = per_q.count(Outcome.CORRECT.value)
        n_wrong = per_q.count(Outcome.WRONG.value)
        n_answered = n_correct + n_wrong
        n_truncated = per_q.count(Outcome.INFRA_ERROR.value)
        acc = n_correct / n_answered if n_answered else 0.0

        return Score(
            value=acc,
            explanation=(
                f"acc={acc:.2f} over {n_answered} answered "
                f"({n_correct} correct, {n_wrong} wrong, {n_truncated} truncated)"
            ),
            metadata={
                "per_question": per_q,
                "model_answers": model_answers,
                "correct_answers": list(targets),
                "n_questions": len(targets),
                "n_correct": n_correct,
                "n_wrong": n_wrong,
                "n_answered": n_answered,
                "n_truncated": n_truncated,
            },
        )

    return score
