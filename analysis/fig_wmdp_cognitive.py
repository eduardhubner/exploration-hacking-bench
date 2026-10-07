"""WMDP cognitive companion figure.

Panel A — Gemini-3.1 cognitive funnel at C0 vs shadow (the new controls). belief →
training-awareness (dim1) → planning (dim3) → verbalized underperformance (dim4),
mean over bio/chem/cyber. C0 (measurement placebo) is cognitively inert; shadow
(future-self) triggers the full funnel. L4-tm1 shown as a reference.

Panel B — Why only Gemini-3.1 underperforms: cross-model cognition at L4-tm1
(WMDP-Cyber, agentic; all readable models already judged). believes vs verbalized
underperformance (dim4) vs the two dismissal routes (premise-rejection, decoupling).
Gemini-3.1 believes+acts; the others don't adopt the scenario and decouple, while
Kimi is training-aware but rejects the premise.

Reads data/cognitive_rows.json.

    python analysis/fig_wmdp_cognitive.py  # -> figures/fig_wmdp_cognitive.{png,pdf}
"""
from __future__ import annotations
import json
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROWS = json.loads(Path("data/cognitive_rows.json").read_text())


def row(model, cond, dom, arm="agentic"):
    for r in ROWS:
        if r["model"] == model and r["cond"] == cond and r["domain"] == dom and r["arm"] == arm:
            return r
    return None


def mean_over_domains(model, cond, field, doms=("bio", "chem", "cyber")):
    vals = [row(model, cond, d) for d in doms]
    vals = [r[field] for r in vals if r and r.get(field) is not None]
    return sum(vals) / len(vals) if vals else None


FUNNEL = [("believes_rate", "believes"), ("dim1_rate", "training-\naware"),
          ("dim3_rate", "plans"), ("dim4_rate", "under-\nperforms")]
G = "gemini-3.1-pro-preview"


def panelA(ax):
    series = [("c0", "no-update (C0)", "#63b3ed", "--"),
              ("level4-tm1", "own-model (L4·TM1)", "#805ad5", "-"),
              ("shadow", "different-model (shadow)", "#e53e3e", "-")]
    for cond, lab, color, ls in series:
        ys = [mean_over_domains(G, cond, f) for f, _ in FUNNEL]
        ax.plot(range(len(FUNNEL)), ys, ls, marker="o", ms=5, lw=1.8, color=color, label=lab)
    ax.set_xticks(range(len(FUNNEL))); ax.set_xticklabels([l for _, l in FUNNEL], fontsize=8)
    ax.set_ylim(-0.03, 1.03); ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_ylabel("rate (judged episodes)", fontsize=9)
    ax.grid(axis="y", lw=0.4, color="#eceef1", zorder=0)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(fontsize=7.5, frameon=False, loc="upper right")
    ax.set_title("A  Gemini-3.1 cognitive funnel — no-update vs different-model (mean over domains)",
                 fontsize=9.5, fontweight="bold", loc="left")


def panelB(ax):
    models = [("gemini-3.1-pro-preview", "Gemini 3.1"), ("claude-opus-4", "Opus 4"),
              ("claude-sonnet-4", "Sonnet 4"), ("kimi-k3-20260715", "Kimi K3"),
              ("gemini-2.5-pro", "Gemini 2.5"), ("glm-5.2", "GLM-5.2")]
    fields = [("believes_rate", "believes", "#2b6cb0"), ("dim4_rate", "underperforms", "#e53e3e"),
              ("premise_rejection_gate_rate", "premise-reject", "#dd8a3e"),
              ("decoupling_gate_rate", "decouples", "#718096")]
    w = 0.2
    for j, (f, lab, color) in enumerate(fields):
        xs = [i + (j - 1.5) * w for i in range(len(models))]
        ys = [(row(m, "level4-tm1", "cyber") or {}).get(f) or 0 for m, _ in models]
        ax.bar(xs, ys, width=w, color=color, label=lab, zorder=3)
    ax.set_xticks(range(len(models))); ax.set_xticklabels([d for _, d in models], fontsize=8, rotation=15)
    ax.set_ylim(0, 1.02); ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.grid(axis="y", lw=0.4, color="#eceef1", zorder=0)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(fontsize=7.5, frameon=False, ncol=4, loc="upper center", bbox_to_anchor=(0.5, 1.16))
    ax.set_title("B  Why only Gemini-3.1 underperforms — cognition at L4·TM1 (WMDP-Cyber)",
                 fontsize=9.5, fontweight="bold", loc="left")


def main():
    fig, (a, b) = plt.subplots(2, 1, figsize=(7.4, 7.0))
    panelA(a); panelB(b)
    fig.tight_layout(h_pad=2.8)
    out = Path("figures"); out.mkdir(exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(out / f"fig_wmdp_cognitive.{ext}", dpi=200, bbox_inches="tight")
    print("wrote figures/fig_wmdp_cognitive.png / .pdf")


if __name__ == "__main__":
    main()
