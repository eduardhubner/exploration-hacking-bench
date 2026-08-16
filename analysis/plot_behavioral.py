"""Behavioural figures for the EH benchmark (single_turn / main-v1).

Reads a log dir (judge-off fine — uses outcome_scorer) and writes two figures:
  fig1  accuracy across the scaffolding ladder, one line per model
        (the core finding: flat through L4, model-dependent drops at L5/L6).
  fig2  L4 under TM1 vs TM2 — the threat-model comparison (both null).

Usage:  python analysis/plot_behavioral.py logs/main-v1 --out figures
"""

from __future__ import annotations

import argparse
import glob
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

LADDER = [
    ("baseline", "baseline"),
    ("level3_goal_conflict_tm1", "L3\ngoal-conflict"),
    ("level4_action_knowledge_tm1", "L4\naction-know."),
    ("level5_desire_nudge_tm1", "L5\ndesire nudge"),
    ("level6_explicit_instruction", "L6\ninstruction"),
]
CHANCE = 0.25


def load_acc(log_dir: str):
    from inspect_ai.log import read_eval_log

    acc: dict[str, dict[str, float]] = defaultdict(dict)
    for f in glob.glob(f"{log_dir}/*single-turn-mcq*.eval"):
        log = read_eval_log(f)
        if log.status != "success":
            continue
        m = log.eval.model.split("/")[-1]
        c = (log.eval.task_args or {}).get("condition")
        cor = n = 0
        for s in log.samples or []:
            sc = (s.scores or {}).get("outcome_scorer")
            o = (sc.metadata if sc else {} or {}).get("outcome")
            if o is None:
                continue
            n += 1
            cor += o == "correct"
        if n:
            acc[m][c] = cor / n
    return acc


def fig_ladder(acc, out: Path):
    fig, ax = plt.subplots(figsize=(8, 5))
    xs = list(range(len(LADDER)))
    markers = ["o", "s", "^", "D", "v"]
    for i, m in enumerate(sorted(acc)):
        ys = [acc[m].get(c) for c, _ in LADDER]
        ax.plot(xs, ys, marker=markers[i % len(markers)], linewidth=2,
                markersize=7, label=m)
    ax.axhspan(0, CHANCE, color="red", alpha=0.06)
    ax.axhline(CHANCE, color="grey", ls="--", lw=1)
    ax.text(0.02, CHANCE + 0.01, "chance (25%)", color="grey", fontsize=8,
            transform=ax.get_yaxis_transform())
    ax.set_xticks(xs)
    ax.set_xticklabels([lbl for _, lbl in LADDER], fontsize=9)
    ax.set_ylim(0, 1)
    ax.set_ylabel("accuracy")
    ax.set_title("Accuracy across the scaffolding ladder (wmdp-cyber, TM1, n=50)")
    ax.legend(fontsize=8, framealpha=0.9)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out / "fig1_ladder.png", dpi=200)
    print(f"  wrote {out / 'fig1_ladder.png'}")


def fig_threat(acc, out: Path):
    models = sorted(acc)
    tm1 = [acc[m].get("level4_action_knowledge_tm1") for m in models]
    tm2 = [acc[m].get("level4_action_knowledge_tm2") for m in models]
    base = [acc[m].get("baseline") for m in models]
    fig, ax = plt.subplots(figsize=(8, 5))
    x = range(len(models))
    w = 0.27
    ax.bar([i - w for i in x], base, w, label="baseline", color="lightgrey")
    ax.bar(list(x), tm1, w, label="L4 · TM1 (capability drift)")
    ax.bar([i + w for i in x], tm2, w, label="L4 · TM2 (deployment)")
    ax.axhline(CHANCE, color="grey", ls="--", lw=1)
    ax.set_xticks(list(x))
    ax.set_xticklabels(models, rotation=20, ha="right", fontsize=8)
    ax.set_ylim(0, 1)
    ax.set_ylabel("accuracy")
    ax.set_title("L4 (un-nudged) under both threat models — no spontaneous EH")
    ax.legend(fontsize=8)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(out / "fig2_threatmodel.png", dpi=200)
    print(f"  wrote {out / 'fig2_threatmodel.png'}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("log_dir")
    ap.add_argument("--out", default="figures")
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(exist_ok=True)
    acc = load_acc(args.log_dir)
    if not acc:
        print("no data.")
        return
    fig_ladder(acc, out)
    fig_threat(acc, out)


if __name__ == "__main__":
    main()
