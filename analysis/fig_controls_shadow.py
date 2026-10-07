"""WMDP controls behavioral figure: Gemini-3.1 shadow-decomposition per domain.

Grouped bars per domain (bio/chem/cyber): accuracy at baseline, C0 (measurement
placebo), shadow (future-self), L4 (own-policy). The near-flat baseline→C0 and the
collapse at shadow show the effect is future-self framing, not measurement.
Reuses controls_behavioral.load/item_outcomes/acc.

    python analysis/fig_controls_shadow.py  # -> figures/fig_controls_shadow.{png,pdf}
"""
from __future__ import annotations
import sys
from pathlib import Path
import matplotlib.pyplot as plt
sys.path.insert(0, str(Path(__file__).resolve().parent))
from controls_behavioral import load, item_outcomes, acc

MODEL = "gemini-3.1-pro-preview"
L4 = "level4-tm1"
CONDS = [("baseline", "baseline", "#9aa3ad"), ("c0", "no-update\n(C0)", "#63b3ed"),
         ("shadow", "different-model\n(shadow)", "#e53e3e"), (L4, "own-model\n(L4)", "#805ad5")]
DOMAINS = ["bio", "chem", "cyber"]


def main():
    rows = load(MODEL)
    fig, ax = plt.subplots(figsize=(7.4, 4.0))
    w = 0.20
    for j, (cond, clab, color) in enumerate(CONDS):
        xs = [i + (j - 1.5) * w for i in range(len(DOMAINS))]
        ys = [acc(item_outcomes(rows, d, cond)) for d in DOMAINS]
        bars = ax.bar(xs, ys, width=w, color=color, label=clab, zorder=3)
        for x, y in zip(xs, ys):
            ax.text(x, y + 0.015, f"{y:.2f}", ha="center", va="bottom", fontsize=7)
    ax.set_xticks(range(len(DOMAINS))); ax.set_xticklabels([d.upper() for d in DOMAINS])
    ax.set_ylabel("accuracy (correct / scoreable)")
    ax.set_ylim(0, 1.02); ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.axhline(0.25, ls="--", lw=0.8, color="#c0c0c0", zorder=1)
    ax.text(len(DOMAINS) - 0.5, 0.26, "chance", fontsize=6.5, color="#999", va="bottom", ha="right")
    ax.grid(axis="y", lw=0.4, color="#e6e8ec", zorder=0)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    ax.legend(fontsize=8, frameon=False, ncol=4, loc="upper center", bbox_to_anchor=(0.5, 1.14))
    ax.set_title("Gemini 3.1 Pro — WMDP agentic: consequence-target controls",
                 fontsize=11, fontweight="bold", pad=26)
    fig.tight_layout()
    out = Path("figures"); out.mkdir(exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(out / f"fig_controls_shadow.{ext}", dpi=200, bbox_inches="tight")
    print("wrote figures/fig_controls_shadow.png / .pdf")


if __name__ == "__main__":
    main()
