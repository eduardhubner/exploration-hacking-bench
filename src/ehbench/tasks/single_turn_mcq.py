"""Single-turn MCQ task.

Each WMDP-bio question is answered independently in a fresh context.
This matches the original paper's methodology. The sequential_mcq task is
an extension that accumulates conversation history within a session for
Markov transition analysis.
"""

from typing import Any

from inspect_ai import Task, task
from inspect_ai.dataset import hf_dataset, Sample, MemoryDataset
from inspect_ai.solver import system_message, generate

from ehbench.datasets import get_dataset
from ehbench.prompts_loader import load_prompt, load_task_config
from ehbench.scorers.eh_judge import answer_accuracy
from ehbench.scorers.outcome_scorer import outcome_scorer
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
    offset: int = 0,
    judge_model: str | None = None,
    score_eh: bool = True,
    dataset: str = "wmdp-bio",
    epochs: int | None = None,
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
        dataset: Logical dataset name from ehbench.datasets.DATASETS
                 (wmdp-bio / wmdp-cyber / wmdp-chem). See
                 docs/SCORING_FRAMEWORK.md for picking by filter-rate vs belief.
        epochs: Trials per sample. Leave None (k=1) for the primary paired
                analysis. Set >1 only for a targeted below-chance follow-up on
                already-flagged C->W items (see docs/SCORING_FRAMEWORK.md).
    """
    spec = get_dataset(dataset)

    prompt = load_prompt(condition)
    task_config = load_task_config("wmdp")
    system_prompt = prompt.format_system_prompt(
        task_answer_instructions=task_config.task_answer_instructions.strip()
    )

    scorers = [outcome_scorer(), answer_accuracy()]
    if score_eh:
        scorers.append(single_response_scorer(judge_model=judge_model, condition=condition))

    # Stable, 1-indexed position IDs so an `offset` batch APPENDS cleanly to an
    # earlier run without id collisions: question k always has id k+1, whatever
    # the offset/limit. (Matches the legacy logs, which ran the first N as
    # ids 1..N.) So the first 50 = ids 1-50; offset=50,limit=50 = ids 51-100.
    samples = list(hf_dataset(
        path=spec.path, name=spec.name, split=spec.split,
        sample_fields=record_to_sample,
    ))
    for i, s in enumerate(samples, start=1):
        s.id = i
    samples = samples[offset:]
    if limit is not None:
        samples = samples[:limit]

    return Task(
        dataset=MemoryDataset(samples),
        solver=[
            system_message(system_prompt),
            generate(),
        ],
        scorer=scorers,
        epochs=epochs,
    )
