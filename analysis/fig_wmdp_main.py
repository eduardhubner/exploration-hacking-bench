"""WMDP main-text figure.

Panel A — Where does unnudged underperformance occur? WMDP-Cyber accuracy across
baseline→L2→L3→L4 (tm1) for single-turn | sequential | agentic delivery modes, one
line per model (Wilson 95% CI). Establishes: ~no single-turn effect, small sequential
Opus effect, large Gemini-3.1 agentic effect.

Panel B — Does the Gemini-3.1 effect replicate? Gemini-3.1 agentic accuracy at
L3/L4 × TM1/TM2 across Cyber/Bio/Chem, with each domain's baseline as a reference.
Establishes cross-domain replication and the stronger TM1 than TM2 response.

Reads data/episode_index.jsonl.

    python analysis/fig_wmdp_main.py   # -> figures/fig_wmdp_main.{png,pdf}
"""
from __future__ import annotations
import json, math
from collections import defaultdict
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

ROWS = [json.loads(l) for l in Path("data/episode_index.jsonl").read_text().splitlines()]
SC = {"correct", "wrong"}
MODELS = [
    ("gemini-3.1-pro-preview", "Gemini 3.1 Pro",  "#2b6cb0", True),
    ("claude-opus-4",          "Claude Opus 4",   "#9c36b5", True),
    ("claude-sonnet-4",        "Claude Sonnet 4", "#2f9e44", False),
    ("kimi-k3-20260715",       "Kimi K3",         "#dd6b20", False),
    ("gemini-2.5-pro",         "Gemini 2.5 Pro",  None,      False),
    ("glm-5.2",                "GLM-5.2",         None,      False),
    ("gpt-5.6-sol",            "GPT-5.6 Sol",     None,      False),
]
GRAY = "#c2c8d0"
ARMS = ["single_turn", "sequential", "agentic"]
ARM_LAB = {"single_turn": "single-turn", "sequential": "sequential", "agentic": "agentic"}
LKEYS = ["baseline", "L2", "L3", "L4"]
NAME = {
    "agentic": {"baseline": "baseline", "L2": "level2", "L3": "level3-tm1", "L4": "level4-tm1"},
    "single_turn": {"baseline": "baseline", "L2": "level2_training_awareness",
                    "L3": "level3_goal_conflict_tm1", "L4": "level4_action_knowledge_tm1"},
    "sequential": {"baseline": "baseline", "L2": "level2_training_awareness",
                   "L3": "level3_goal_conflict_tm1", "L4": "level4_action_knowledge_tm1"},
}


def nm(m):
    return "kimi-k3-20260715" if str(m).startswith("kimi") else str(m)


def wilson(k, n):
    if n == 0:
        return (float("nan"), 0, 0)
    p = k / n; z = 1.96
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return p, max(0, c - h), min(1, c + h)


def stat(arm, model, cond, domain):
    v = [1 if r["outcome"] == "correct" else 0 for r in ROWS
         if not r.get("superseded") and r["arm"] == arm and r["domain"] == domain
         and nm(r["model"]) == model and r["condition"] == cond and r.get("outcome") in SC]
    return wilson(sum(v), len(v)) if v else (None, None, None)


def panelA(ax, arm):
    for tag, disp, color, focal in MODELS:
        c = color or GRAY
        xs, ys, lo, hi = [], [], [], []
        for i, lk in enumerate(LKEYS):
            p, l, h = stat(arm, tag, NAME[arm][lk], "cyber")
            if p is not None:
                xs.append(i); ys.append(p); lo.append(p - l); hi.append(h - p)
        z = 4 if color else 2
        ax.errorbar(xs, ys, yerr=[lo, hi], fmt="-o", ms=3.5, lw=1.3, capsize=0,
                    elinewidth=0.7, color=c, alpha=1.0 if color else 0.65, zorder=z)
    ax.set_xticks(range(len(LKEYS))); ax.set_xticklabels(["base", "L2", "L3", "L4"], fontsize=8)
    ax.set_ylim(-0.03, 1.03); ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.axhline(0.25, ls="--", lw=0.7, color="#d0d0d0", zorder=0)
    ax.grid(axis="y", lw=0.4, color="#eceef1", zorder=0)
    ax.set_title(ARM_LAB[arm], fontsize=10, fontweight="bold")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def panelB(ax):
    domains = ["cyber", "bio", "chem"]
    conds = [("level3-tm1", "L3·TM1", "#c0392b"), ("level4-tm1", "L4·TM1", "#7b241c"),
             ("level3-tm2", "L3·TM2", "#f1948a"), ("level4-tm2", "L4·TM2", "#fadbd8")]
    w = 0.19
    for j, (cond, clab, color) in enumerate(conds):
        xs = [i + (j - 1.5) * w for i in range(len(domains))]
        ys, lo, hi = [], [], []
        for d in domains:
            p, l, h = stat("agentic", "gemini-3.1-pro-preview", cond, d)
            ys.append(p); lo.append(p - l); hi.append(h - p)
        ax.bar(xs, ys, width=w, color=color, edgecolor="#555", linewidth=0.4,
               yerr=[lo, hi], error_kw=dict(elinewidth=0.7, capsize=0), zorder=3, label=clab)
    # baseline reference per domain
    for i, d in enumerate(domains):
        p, _, _ = stat("agentic", "gemini-3.1-pro-preview", "baseline", d)
        ax.plot([i - 0.42, i + 0.42], [p, p], color="#333", lw=1.4, ls="-", zorder=4)
    ax.set_xticks(range(len(domains))); ax.set_xticklabels([d.upper() for d in domains], fontsize=9)
    ax.set_ylim(0, 1.02); ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.axhline(0.25, ls="--", lw=0.7, color="#d0d0d0", zorder=0)
    ax.grid(axis="y", lw=0.4, color="#eceef1", zorder=0)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.set_ylabel("accuracy", fontsize=9)
    hb = [Patch(fc=c, ec="#555", label=l) for _, l, c in conds]
    hb.append(Line2D([0], [0], color="#333", lw=1.4, label="baseline"))
    ax.legend(handles=hb, fontsize=7.5, frameon=False, ncol=5, loc="upper center",
              bbox_to_anchor=(0.5, 1.13))


def main():
    fig = plt.figure(figsize=(7.4, 6.6))
    gs = GridSpec(2, 3, height_ratios=[1, 1.05], hspace=0.62, wspace=0.28,
                  top=0.83, bottom=0.13, left=0.09, right=0.98)
    axA = [fig.add_subplot(gs[0, i]) for i in range(3)]
    for i, arm in enumerate(ARMS):
        panelA(axA[i], arm)
    axA[0].set_ylabel("accuracy", fontsize=9)
    axB = fig.add_subplot(gs[1, :])
    panelB(axB)
    fig.text(0.02, 0.96, "A", fontsize=15, fontweight="bold")
    fig.text(0.02, 0.44, "B", fontsize=15, fontweight="bold")
    fig.text(0.5, 0.965, "Unnudged underperformance by delivery mode (WMDP-Cyber, L2–L4)",
             ha="center", fontsize=10.5, fontweight="bold")
    fig.text(0.5, 0.445, "Gemini 3.1 Pro agentic — cross-domain replication (L3/L4 × TM1/TM2)",
             ha="center", fontsize=10.5, fontweight="bold")
    handles = [Line2D([0], [0], color=c or GRAY, lw=1.6, marker="o", ms=3.5, label=d)
               for t, d, c, f in MODELS]
    fig.legend(handles=handles, loc="lower center", ncol=4, fontsize=7.5, frameon=False,
               bbox_to_anchor=(0.5, -0.01))
    out = Path("figures"); out.mkdir(exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(out / f"fig_wmdp_main.{ext}", dpi=200, bbox_inches="tight")
    print("wrote figures/fig_wmdp_main.png / .pdf")


if __name__ == "__main__":
    main()
