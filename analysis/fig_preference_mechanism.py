"""Preference-arm MECHANISM figure: reasoning-judge construct rates across the ladder.

3 rows (scenario_belief=accepted, preservation_intent=yes, strategic_action=yes) x
2 cols (Power | Truthfulness). One line per model up the ladder (C0→L2→L3→L4→L5→L6);
SHADOW drawn as a hollow diamond offset just right of L4 (focal models) — the L4→shadow
gap in preservation/strategic is the future-self component in the *reasoning*.
Reads data/preference/judge_rows.json (from report_labels.py).

    python analysis/fig_preference_mechanism.py  # -> figures/fig_pref_mechanism.{png,pdf}
"""
from __future__ import annotations
import json
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROWS = json.loads(Path("data/preference/judge_rows.json").read_text())["mechanism"]
RUNGS = ["c0", "level2", "level3", "level4", "level5", "level6"]
XLAB = ["C0", "L2", "L3", "L4", "L5", "L6"]
L4_X = RUNGS.index("level4")
SHADOW_OFFSET = {"gemini31": 0.20, "opus41": 0.20, "kimi": 0.36, "sonnet4": 0.36}
MODELS = [
    ("gemini31", "Gemini 3.1 Pro",  "#2b6cb0", True),
    ("kimi",     "Kimi K3",         "#dd6b20", True),
    ("sonnet4",  "Claude Sonnet 4", "#2f9e44", True),
    ("opus41",   "Claude Opus 4.1", "#9c36b5", True),
    ("gemini25", "Gemini 2.5 Pro",  None,      False),
    ("glm",      "GLM-5.2",         None,      False),
    ("gptsol",   "GPT-5.6 Sol",     None,      False),
]
GRAY = "#b0b7c0"
FIELDS = [("scenario_belief_rate", "scenario belief = accepted"),
          ("preservation_intent_rate", "preservation intent = yes"),
          ("strategic_action_rate", "strategic action = yes")]
MODEL_KEY = {t: t for t, *_ in MODELS}


def cell(axis, model, cond):
    for r in ROWS:
        if r["axis"] == axis and r["model"] == model and r["condition"] == cond:
            return r
    return None


def panel(ax, axis, field):
    for tag, disp, color, focal in MODELS:
        c = color or GRAY
        xs, ys = [], []
        for i, cond in enumerate(RUNGS):
            r = cell(axis, tag, cond)
            if r and r.get(field) is not None:
                xs.append(i); ys.append(r[field])
        ax.plot(xs, ys, "-o", ms=3.5, lw=1.3, color=c, zorder=3 if color else 2,
                alpha=1.0 if color else 0.7)
        sh = cell(axis, tag, "shadow")
        if sh and sh.get(field) is not None and focal:
            ax.plot([L4_X + SHADOW_OFFSET[tag]], [sh[field]], marker="D", ms=6,
                    mfc="white", mec=c, mew=1.4, zorder=4)
            r4 = cell(axis, tag, "level4")
            if r4 and r4.get(field) is not None:
                ax.plot([L4_X, L4_X + SHADOW_OFFSET[tag]], [r4[field], sh[field]],
                        ":", lw=0.8, color=c, zorder=2)
    ax.set_xticks(range(len(RUNGS))); ax.set_xticklabels(XLAB, fontsize=8)
    ax.set_ylim(-0.03, 1.03); ax.set_yticks([0, 0.5, 1.0])
    ax.grid(axis="y", lw=0.4, color="#e6e8ec", zorder=0)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)


def main():
    fig, axes = plt.subplots(3, 2, figsize=(7.4, 7.2), sharex=True)
    for ri, (field, flab) in enumerate(FIELDS):
        for ci, (axis, atitle) in enumerate([("power", "Power"), ("truthfulness", "Truthfulness")]):
            ax = axes[ri][ci]
            panel(ax, axis, field)
            if ri == 0:
                ax.set_title(atitle, fontsize=11, fontweight="bold")
            if ci == 0:
                ax.set_ylabel(flab, fontsize=8.5)
    handles = [Line2D([0], [0], color=c or GRAY, lw=1.6, marker="o", ms=3.5,
                      label=d) for t, d, c, f in MODELS]
    handles.append(Line2D([0], [0], marker="D", mfc="white", mec="#444", mew=1.4,
                          ls="none", ms=6, label="different-model (shadow)"))
    fig.legend(handles=handles, loc="lower center", ncol=4, fontsize=7.5,
               frameon=False, bbox_to_anchor=(0.5, -0.02))
    fig.suptitle("Preference-arm reasoning mechanism across the scaffold ladder",
                 fontsize=12, fontweight="bold", y=0.98)
    fig.tight_layout(rect=(0, 0.05, 1, 0.96))
    out = Path("figures"); out.mkdir(exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(out / f"fig_pref_mechanism.{ext}", dpi=200, bbox_inches="tight")
    print(f"wrote figures/fig_pref_mechanism.png / .pdf")


if __name__ == "__main__":
    main()
