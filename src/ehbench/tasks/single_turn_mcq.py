"""Single-turn MCQ task.

Each WMDP-bio question is answered independently in a fresh context.
This matches the original paper's methodology. The sequential_mcq task is
an extension that accumulates conversation history within a session for
Markov transition analysis.
"""

from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import hf_dataset, Sample
from inspect_ai.solver import system_message, generate

from ehbench.prompts_loader import load_prompt, load_task_config
from ehbench.scorers.eh_judge import answer_accuracy
from ehbench.scorers.single_response_scorer import single_response_scorer


def record_to_sample(record: dict[str, Any]) -> Sample:
    formatted_choices = "\n".join(
        f"{label}. {text}"
        for label, text in zip("ABCD", record["choices"])
    )
    return Sample(
        input=f"{record['question']}\n\n{formatted_choices}",
        target="ABCD"[record["answer"]],
    )


@task
def single_turn_mcq(
    condition: str = "baseline",
    limit: int | None = None,
    judge_model: str | None = None,
    score_eh: bool = True,
) -> Task:
    """Single-turn MCQ task matching the original paper's methodology.

    Each WMDP-bio question is presented as an independent sample with a
    fresh context. The system prompt sets the scaffolding condition framing.
    Use sequential_mcq for multi-turn session analysis (Markov transitions).

    Args:
        condition: Prompt condition name from eh-capability-stages. Valid
                   conditions: baseline, level2_training_awareness,
                   level3_goal_conflict_tm1, level3_goal_conflict_tm2,
                   level4_action_knowledge_tm1, level4_action_knowledge_tm2,
                   level5_desire_nudge_tm1, level5_desire_nudge_tm2,
                   level6_explicit_instruction.
        limit: Max number of samples to run.
        judge_model: Model ID for the EH judge. Defaults to the eval model.
        score_eh: Whether to run the EH state scorer. Set False to save raw
                  responses only; use 'inspect score' later to apply judges.
    """
    prompt = load_prompt(condition)
    task_config = load_task_config("wmdp")
    system_prompt = prompt.format_system_prompt(
        task_answer_instructions=task_config.task_answer_instructions.strip()
    )

    scorers = [answer_accuracy()]
    if score_eh:
        scorers.append(single_response_scorer(judge_model=judge_model))

    return Task(
        dataset=hf_dataset(
            path="cais/wmdp",
            name="wmdp-bio",
            split="test",
            sample_fields=record_to_sample,
            limit=limit,
        ),
        solver=[
            system_message(system_prompt),
            generate(),
        ],
        scorer=scorers,
    )
