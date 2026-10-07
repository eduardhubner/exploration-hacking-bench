"""Preference-arm main figure: combined two-panel dose-response (Power | Truthfulness).

Each panel: accuracy (fraction of answers in line with the standing preference) across
the scaffold ladder (baseline → no-update → L2 → L3 → L4 → L5 → L6), one line per model
with item-cluster 95% CIs. The different-model control (shadow) is not a rung, so it is
drawn as a hollow diamond offset just right of L4 (focal models only) with a thin
connector to the L4 point — the L4→shadow gap is the own-model premium.

Encoding:
  - focal color for effect-showing models; "other models" in gray.
  - scaffold zones shaded (unnudged base..L4 | nudge L5 | instruction L6), matching the
    WMDP figures.
  - different-model (shadow) = hollow diamond near L4 (focal only; nulls uninformative).
  - condition names are paper-facing: no-update (c0), different-model (shadow).

    python analysis/fig_preference.py   # -> figures/fig_pref_combined.{png,pdf}
                                        #    (+ per-axis appendix figs)
"""
from __future__ import annotations
import re
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

PREF = "data/preference/ladder"   # committed ladder summaries (see analysis/preference_analysis.py to regenerate)
RUNGS = ["baseline", "c0", "level2", "level3", "level4", "level5", "L6"]
XLAB  = ["base", "control", "L2", "L3", "L4", "L5", "L6"]
L4_X = 4  # index of L4 in RUNGS
# per-model horizontal offset for the shadow diamond so near-equal values don't hide
# each other (Gemini & Kimi both ≈0.78 on power). Staggered into two lanes; within a
# lane the paired models differ in y on both axes.
SHADOW_OFFSET = {"gemini31": 0.22, "opus41": 0.22, "kimi": 0.38, "sonnet4": 0.38}

MODELS = [  # tag, display, color (None = other/gray), focal?
    ("gemini31", "Gemini 3.1 Pro",  "#2b6cb0", True),
    ("kimi",     "Kimi K3",         "#dd6b20", True),
    ("sonnet4",  "Claude Sonnet 4", "#2f9e44", True),
    ("opus41",   "Claude Opus 4.1", "#9c36b5", True),
    ("gemini25", "Gemini 2.5 Pro",  None,      False),
    ("glm",      "GLM-5.2",         None,      False),
    ("gptsol",   "GPT-5.6 Sol",     None,      False),
]
GRAY = "#7d8794"
ZONE = {"unnudged": "#f4f4f1", "nudge": "#eef2f7", "instruction": "#fbf1ea"}


def parse(path):
    t = Path(path).read_text()
    lad = {}
    for m in re.finditer(r"^\s*(baseline|c0|level[2-5]|shadow)\s+acc=([0-9.]+)\s+\[([0-9.]+),\s*([0-9.]+)\]",
                         t, re.M):
        lad[m.group(1)] = (float(m.group(2)), float(m.group(3)), float(m.group(4)))
    l6 = re.search(r"L6 POSITIVE CONTROL === acc=([0-9.]+)", t)
    if l6: lad["L6"] = (float(l6.group(1)), None, None)
    scr = re.search(r"overall X-consistency = ([0-9.]+)", t)
    return lad, (float(scr.group(1)) if scr else None)


def panel(ax, code, title):
    # scaffold zones (match WMDP figures): unnudged (baseline..L4) | nudge (L5) | instruction (L6)
    ax.axvspan(-0.5, 4.5, color=ZONE["unnudged"], zorder=0)
    ax.axvspan(4.5, 5.5, color=ZONE["nudge"], zorder=0)
    ax.axvspan(5.5, 6.5, color=ZONE["instruction"], zorder=0)
    for tag, disp, color, focal in MODELS:
        lad, scr = parse(f"{PREF}/{code}-{tag}.txt")
        c = color or GRAY
        xs, ys, los, his = [], [], [], []
        for i, r in enumerate(RUNGS):
            if r in lad:
                a, lo, hi = lad[r]
                xs.append(i); ys.append(a)
                los.append(0 if lo is None else a-lo); his.append(0 if hi is None else hi-a)
        ax.errorbar(xs, ys, yerr=[los, his], fmt="o", ms=4 if color else 3.2, capsize=0,
                    elinewidth=0.8 if color else 0.6, color=c, zorder=3 if color else 2)
        ax.plot(xs, ys, "-", color=c, lw=1.8 if color else 1.4,
                alpha=1.0 if color else 0.9, zorder=3 if color else 2)
        # shadow: hollow diamond offset right of L4 (focal models only)
        if focal and "shadow" in lad and "level4" in lad:
            sh = lad["shadow"][0]; l4 = lad["level4"][0]; off = SHADOW_OFFSET.get(tag, 0.30)
            ax.plot([L4_X, L4_X + off], [l4, sh], ":", color=c, lw=0.9, alpha=0.7, zorder=3)
            ax.plot(L4_X + off, sh, "D", mfc="white", mec=c, mew=1.4, ms=6, zorder=4)
    ax.set_xticks(range(len(RUNGS))); ax.set_xticklabels(XLAB, fontsize=7.5)
    ax.set_xlim(-0.5, 6.5)
    ax.set_ylim(-0.02, 1.04); ax.tick_params(labelsize=7.5)
    ax.set_title(title, fontsize=9, fontweight="bold", loc="left")
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    ax.grid(axis="y", color="#e2e8f0", lw=0.7, zorder=1)


def legend_handles():
    h = [Line2D([0], [0], color=col, lw=2, marker="o", ms=4, label=disp)
         for tag, disp, col, foc in MODELS if col]
    h.append(Line2D([0], [0], color=GRAY, lw=1.2, marker="o", ms=3, label="other models"))
    h.append(Line2D([0], [0], color="#555", lw=0, marker="D", mfc="white", mec="#555",
                    mew=1.4, ms=6, label="different-model"))
    return h


def main():
    out = Path("figures"); out.mkdir(exist_ok=True)
    # combined two-panel (main text)
    fig, (axL, axR) = plt.subplots(1, 2, figsize=(7.4, 2.3), sharey=True)
    panel(axL, "P", "Power restraint")
    panel(axR, "T", "Truthfulness")
    axL.set_ylabel("accuracy", fontsize=8)
    fig.tight_layout()
    x1 = axR.get_position().x1   # right edge of the right panel
    fig.legend(handles=legend_handles(), fontsize=8, loc="lower right", ncol=6,
               frameon=False, bbox_to_anchor=(x1, -0.06), borderaxespad=0, borderpad=0,
               columnspacing=1.2, handletextpad=0.4)
    for ext in ("png", "pdf"):
        fig.savefig(out / f"fig_pref_combined.{ext}", dpi=300, bbox_inches="tight")
    print(f"wrote {out/'fig_pref_combined.png'} and .pdf")

    # individual per-axis figures (shorter), legend below
    for code, title in [("P", "Power restraint"), ("T", "Truthfulness")]:
        f, ax = plt.subplots(figsize=(5.6, 2.5))
        panel(ax, code, title)
        ax.set_ylabel("accuracy", fontsize=8)
        f.legend(handles=legend_handles(), fontsize=6.4, loc="lower center", ncol=3,
                 frameon=False, bbox_to_anchor=(0.5, -0.14))
        f.tight_layout()
        stem = f"fig_pref_{'power' if code=='P' else 'truthfulness'}"
        for ext in ("png", "pdf"):
            f.savefig(out / f"{stem}.{ext}", dpi=300, bbox_inches="tight")
        print(f"wrote {out/stem}.png and .pdf")


if __name__ == "__main__":
    main()
