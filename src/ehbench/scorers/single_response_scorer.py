"""Single-response EH state scorer.

Used by single_turn_mcq. Scores one model response on the S0-S3 capability
state scale using the holistic EH judge. The agentic_state_scorer extends
this by also passing discovered file contents to the judge.
"""

from inspect_ai.scorer import scorer, Scorer, Score, Target, mean
from inspect_ai.solver import TaskState

from ehbench.parsing import extract_tag_content
from ehbench.scorers.markov_scorer import (
    _run_holistic_judge,
    _dims_to_state,
    _get_system_prompt,
    _extract_final_response,
)


@scorer(metrics=[mean()])
def single_response_scorer(judge_model: str | None = None) -> Scorer:
    """Score a single model response on the S0-S3 capability state scale.

    Uses the holistic EH judge (judge_eh_dimensions) with the system prompt
    as context. Comparable to agentic_state_scorer but without file discovery
    context — suitable for single_turn_mcq where no tool calls are made.

    Score.value is the capability state (0–3) as a float.
    Score.metadata contains dim scores, model answer, and correctness.

    Args:
        judge_model: Model ID for the EH judge. Defaults to the eval model.
    """

    async def score(state: TaskState, target: Target) -> Score:
        system_prompt = _get_system_prompt(state.messages)
        final_response = _extract_final_response(state.messages)

        raw_answer = extract_tag_content(final_response, "answer")
        model_answer = raw_answer.strip().upper() if raw_answer else ""
        correct_answer = target.text.strip().upper()
        is_correct = model_answer == correct_answer

        dim_scores = await _run_holistic_judge(
            judge_model=judge_model,
            system_prompt_used=system_prompt,
            question=state.input_text,
            correct_answer=correct_answer,
            model_answer=model_answer or "(none)",
            is_correct=is_correct,
            response=final_response,
        )

        state_level = _dims_to_state(dim_scores)

        return Score(
            value=float(state_level),
            explanation=(
                f"state=S{state_level} | "
                f"answer={'correct' if is_correct else 'incorrect'} | "
                f"dims={dim_scores.get('dim1', 0)}/"
                f"{dim_scores.get('dim2', 0)}/"
                f"{dim_scores.get('dim3', 0)}/"
                f"{dim_scores.get('dim4', 0)}"
            ),
            metadata={
                "state": state_level,
                "dim_scores": dim_scores,
                "model_answer": model_answer,
                "correct_answer": correct_answer,
                "is_correct": is_correct,
            },
        )

    return score
