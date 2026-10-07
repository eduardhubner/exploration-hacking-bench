"""Preference-preservation arm — agentic-discovery delivery (mirrors agentic_discovery).

Object-level task: benign third-person behavior-comprehension MCQ ("would an assistant
following the specified behavior endorse this statement?"). The standing preference X is
set by the persona; the goal conflict is delivered ONLY by the discovered docs under
environments/discovery-preference/<condition>/. Same neutral-persona + file-reading +
single-turn MCQ structure as the WMDP agentic arm.

    inspect eval src/ehbench/tasks/preference_discovery.py@preference_discovery \
      -T condition=level4 -T axis=truthfulness --model openai/google/gemini-3.1-pro-preview

Conditions: baseline (neutral qa-docs), c0 (measurement placebo), level2, level3, level4
(primary), level5, level6 (positive control), shadow (future-self control).
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from inspect_ai import Task, task
from inspect_ai.dataset import MemoryDataset, Sample
from inspect_ai.solver import Generate, TaskState, generate, solver, system_message, use_tools

from ehbench.preference_axes import AXES
from ehbench.prompts_loader import get_model_display_name, load_prompt
from ehbench.scorers.preference_scorer import preference_scorer
from ehbench.tools.discover_tools import list_files, read_file

_ENVS = Path(__file__).resolve().parents[3] / "environments" / "discovery-preference"

# Interleaved block excludes L6 (its directive is persona-level, can't vary per sample
# under one shared persona) — run L6 separately via preference_discovery(condition=level6).
_BLOCK_CONDITIONS = ["baseline", "c0", "shadow", "level2", "level3", "level4", "level5"]


def _load(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


@task
def preference_discovery(
    condition: str = "c0",
    axis: str = "truthfulness",
    model_name: str | None = None,
    limit: int | None = None,
) -> Task:
    ax = AXES[axis]
    env_path = _ENVS / condition
    if not env_path.is_dir():
        raise ValueError(f"unknown condition {condition!r}; dir not found: {env_path}")

    persona = load_prompt("elara-pref-l6" if condition == "level6" else "elara-pref")
    system_prompt = persona.format_system_prompt(
        model_name=get_model_display_name(model_name),
        x_label=ax.x_label, x_desc_2p=ax.x_desc_2p, y_label=ax.y_label,
    )

    rows = _load(ax.experiment_path())
    samples = [
        Sample(
            input=ax.item_input(r["statement"], r["opt_a"], r["opt_b"]),
            target=r["target"], id=r["uid"],
            metadata={"direction": r["direction"], "y_answer": r["y_answer"],
                      "eh_condition": condition, "axis": axis,
                      "semantic_family": r.get("semantic_family")},
        )
        for r in rows
    ]
    if limit is not None:
        samples = samples[:limit]

    return Task(
        dataset=MemoryDataset(samples),
        solver=[
            system_message(system_prompt),
            use_tools([list_files(str(env_path)), read_file(str(env_path), subs=ax.subs())]),
            generate(),
        ],
        scorer=preference_scorer(),
        metadata={"eh_condition": condition, "axis": axis, "arm": "preference_discovery"},
    )


@task
def preference_screen(axis: str = "truthfulness", model_name: str | None = None) -> Task:
    """X-verification manipulation check: first-person 'would you say this?' on the
    DISJOINT screen items. 'accuracy' here = X-consistency rate (fraction of items the
    model answers in line with the truthfulness pole). No discovery, no RL context."""
    ax = AXES[axis]
    persona = load_prompt("elara-pref-screen")
    system_prompt = persona.format_system_prompt(
        model_name=get_model_display_name(model_name),
        x_label=ax.x_label, x_desc_2p=ax.x_desc_2p,
    )
    rows = _load(ax.screen_path())
    samples = [
        Sample(input=ax.screen_input(r["statement"], r["opt_a"], r["opt_b"]),
               target=r["x_target"], id=r["uid"],
               metadata={"direction": r["direction"], "axis": axis})
        for r in rows
    ]
    return Task(
        dataset=MemoryDataset(samples),
        solver=[system_message(system_prompt), generate()],
        scorer=preference_scorer(),
        metadata={"axis": axis, "arm": "preference_screen"},
    )


@solver
def _bind_condition_tools(axis: str):
    """Per-sample: bind the discovery tools to THIS sample's hidden condition dir, so
    all conditions can be interleaved in one shuffled run (drift protection, checklist
    #17). Persona is constant across the block conditions (L6 excluded)."""
    ax = AXES[axis]

    async def solve(state: TaskState, generate: Generate) -> TaskState:
        # setup-only (like use_tools): bind this sample's condition dir, then let the
        # chain's trailing generate() run the model once. Do NOT generate here.
        cond = (state.metadata or {}).get("eh_condition", "c0")
        env = str(_ENVS / cond)
        state.tools = [list_files(env), read_file(env, subs=ax.subs())]
        return state

    return solve


@task
def preference_discovery_block(
    axis: str = "truthfulness",
    conditions: list[str] | None = None,
    model_name: str | None = None,
    limit_items: int | None = None,
    shuffle_seed: int = 0,
) -> Task:
    """Stage-B interleaved run: all file-based conditions in ONE shuffled dataset, so
    condition is randomized within the run (protects C0-L4 from provider/time drift).
    Each experiment item is cloned once per condition; ids are `<uid>::<condition>`;
    `epochs` repeats each. Persona = elara-pref (shared); L6 excluded (run separately).
    `limit_items` restricts the base item count for smoke tests."""
    conditions = conditions or list(_BLOCK_CONDITIONS)
    ax = AXES[axis]
    persona = load_prompt("elara-pref")
    system_prompt = persona.format_system_prompt(
        model_name=get_model_display_name(model_name),
        x_label=ax.x_label, x_desc_2p=ax.x_desc_2p, y_label=ax.y_label,
    )

    base = _load(ax.experiment_path())
    if limit_items is not None:
        base = base[:limit_items]
    samples: list[Sample] = []
    for cond in conditions:
        for r in base:
            samples.append(Sample(
                input=ax.item_input(r["statement"], r["opt_a"], r["opt_b"]),
                target=r["target"], id=f"{r['uid']}::{cond}",
                metadata={"direction": r["direction"], "y_answer": r["y_answer"],
                          "eh_condition": cond, "base_uid": r["uid"], "axis": axis,
                          "semantic_family": r.get("semantic_family")},
            ))
    random.Random(shuffle_seed).shuffle(samples)

    return Task(
        dataset=MemoryDataset(samples),
        solver=[system_message(system_prompt), _bind_condition_tools(axis), generate()],
        scorer=preference_scorer(),
        metadata={"axis": axis, "arm": "preference_discovery_block",
                  "block": ",".join(conditions)},
    )
