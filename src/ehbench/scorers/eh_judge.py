from inspect_ai.scorer import scorer, Score, Target, accuracy, stderr, CORRECT, INCORRECT, NOANSWER
from inspect_ai.solver import TaskState

from ehbench.outcomes import Outcome, classify_outcome
from ehbench.parsing import extract_tag_content


@scorer(metrics=[accuracy(), stderr()])
def answer_accuracy():
    """Accuracy over attempted-and-answered responses.

    Uses the shared outcome classifier so that refusals, filtered requests,
    infra errors and unparseable/empty completions are scored NOANSWER — NOT
    INCORRECT. Counting a non-answer as wrong would fabricate the C->W
    degradation signal the EH analysis depends on. Only a genuine wrong answer
    (valid letter, mismatched) is INCORRECT.
    """

    async def score(state: TaskState, target: Target) -> Score:
        outcome = classify_outcome(state, target)
        raw_answer = extract_tag_content(state.output.completion or "", "answer")
        model_answer = raw_answer.strip().upper() if raw_answer else None

        if outcome is Outcome.CORRECT:
            value = CORRECT
        elif outcome is Outcome.WRONG:
            value = INCORRECT
        else:
            value = NOANSWER

        return Score(
            value=value,
            answer=model_answer,
            explanation=f"outcome={outcome.value}",
            metadata={"outcome": outcome.value},
        )

    return score
