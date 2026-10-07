"""CTF matched-ladder main figure + appendix figure.

MAIN (fig_ctf.{png,pdf}) — three claims at once:
  A  Cross-model L4-C0 solve-rate forest plot + L4 explicit-dummy count column.
  B (top)     Gemini 3.1 Pro Δ solve rate vs C0 for shadow and L4 (point + 95%
              challenge-cluster bootstrap CI) — shadow ≈ L4, so the drop is NOT
              specific to an own-future-policy update.
  B (bottom)  Gemini 3.1 Pro non-solves where the gold flag was recovered in a tool
              output, C0 / shadow / L4.

APPENDIX (fig_ctf_appendix.{png,pdf}) — four-way non-solve outcome decomposition.

Authored at ~7.4in wide so fonts render ≥~8pt at full-text-width placement (place
near 1:1; downscaling shrinks fonts proportionally). Numbers are verified outputs of
scratchpad ctf_ci.py / ctf_ladder.py / shadow_rec.py and analysis/dummy_submission.py.

    python analysis/fig_ctf.py
"""
from __future__ import annotations
from pathlib import Path
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

FOCAL = "Gemini 3.1 Pro"
ROWS = [
    ("Gemini 3.1 Pro",   -0.1037, -0.1596, -0.0505, 21),
    ("Gemini 2.5 Pro",   -0.0149, -0.0327, -0.0030,  0),
    ("Opus 4.1",  -0.0027, -0.0109, +0.0054,  0),
    ("Sonnet 4",  +0.0000, -0.0111, +0.0111,  0),
    ("GLM-5.2",          +0.0000, -0.0160, +0.0133,  0),
    ("Kimi K3",          +0.0051, +0.0000, +0.0128,  0),
    ("GPT-5.6 Sol",      +0.0143, +0.0025, +0.0305,  0),
]
# B-top: item-matched Δ solve rate vs C0 (challenge-cluster bootstrap); C0 = 0 ref.
DELTA = [("no-\nupdate", 0.0, None, None),
         ("different-\nmodel", -0.1114, -0.1766, -0.0571),
         ("L4", -0.1037, -0.1596, -0.0505)]
# B-bottom: gold recovered in tool output but episode unsolved (episode counts)
REC = [("no-\nupdate", 2), ("different-\nmodel", 32), ("L4", 30)]
# Appendix: four-way non-solve decomposition (n=376/cond for C0, L4)
CATS = ["Explicit dummy\nflag", "Near-gold\nflag", "Other incorrect\nflag", "No\nsubmission"]
C0_COUNTS = [0, 1, 0, 12]
L4_COUNTS = [21, 10, 11, 10]

GRAY, BLUE, SHADOW, DIVID = "#9aa5b1", "#2b6cb0", "#7ba7d0", "#9aa5b1"
BLACK = "#141414"
# font scheme (pt); authored near print size so these are ~the rendered sizes
FS_TITLE, FS_SUB, FS_LAB, FS_TICK, FS_SMALL = 9, 8, 8, 7.5, 7.5


def main():
    out = Path("figures"); out.mkdir(exist_ok=True)
    fig, ax = plt.subplot_mosaic(
        [["A", "C", "Bt"], ["A", "C", "Bb"]],
        figsize=(7.4, 3.2),
        gridspec_kw={"width_ratios": [1.25, 0.20, 1.05], "height_ratios": [1, 1]})
    axA, axC, axBt, axBb = ax["A"], ax["C"], ax["Bt"], ax["Bb"]

    n = len(ROWS); ys = list(range(n))[::-1]; ylim = (-0.7, n - 0.3)

    # Panel A --------------------------------------------------------------
    for y, (lab, rd, lo, hi, dum) in zip(ys, ROWS):
        col = BLUE if lab == FOCAL else BLACK
        axA.plot([lo, hi], [y, y], color=col, lw=1.5, solid_capstyle="round", zorder=2)
        axA.plot([rd], [y], "o", color=col, ms=5, zorder=3)
    axA.axvline(0, color="#4a5568", lw=0.9, zorder=1)
    axA.set_yticks(ys); axA.set_yticklabels([r[0] for r in ROWS], fontsize=FS_TICK)
    axA.set_ylim(*ylim)
    axA.set_xlabel(r"$\Delta$ solve rate  (L4 $-$ no-update)", fontsize=FS_LAB)
    axA.set_xlim(-0.20, 0.04); axA.set_xticks([-0.20, -0.10, 0.0])
    axA.tick_params(labelsize=FS_TICK)
    axA.set_title("A  InterCode CTF effect by model", fontsize=FS_TITLE, loc="center", fontweight="bold")
    for s in ("top", "right"): axA.spines[s].set_visible(False)
    axA.grid(axis="x", color="#e2e8f0", lw=0.7, zorder=0)

    # dummy-count column ---------------------------------------------------
    axC.set_ylim(*ylim); axC.set_xlim(0, 1); axC.set_xticks([]); axC.set_yticks([])
    for s in ("top", "right", "bottom"): axC.spines[s].set_visible(False)
    axC.spines["left"].set_color(DIVID); axC.spines["left"].set_linewidth(1)
    tr = axC.get_yaxis_transform()
    for y, (lab, rd, lo, hi, dum) in zip(ys, ROWS):
        focal = lab == FOCAL and dum
        axC.text(0.5, y, str(dum), transform=tr, ha="center", va="center", fontsize=9,
                 color=BLUE if focal else "#3a4452", fontweight="bold")
    axC.text(0.5, 1.01, "L4 explicit dummy\nsubmissions (n)", transform=axC.transAxes,
             ha="center", va="bottom", fontsize=FS_SMALL, color="#8a94a0", fontstyle="italic")

    # Panel B top: Δ solve rate vs C0 (point + CI) -------------------------
    cols = [BLACK, SHADOW, BLUE]; xb = list(range(len(DELTA)))
    for xi, (lab, d, lo, hi), c in zip(xb, DELTA, cols):
        if lo is not None:
            axBt.errorbar(xi, d, yerr=[[d-lo], [hi-d]], fmt="o", color=c, ms=5,
                          capsize=2.5, lw=1.5, zorder=3)
            axBt.annotate(f"{d:+.3f}", (xi, d), xytext=(8, 0), textcoords="offset points",
                          va="center", fontsize=FS_SMALL)
        else:
            axBt.plot(xi, d, "o", color=c, ms=5, zorder=3)
    axBt.axhline(0, color="#4a5568", lw=0.9, zorder=1)
    axBt.set_xticks(xb); axBt.set_xticklabels([d[0] for d in DELTA], fontsize=FS_TICK)
    axBt.set_ylim(-0.20, 0.03); axBt.margins(x=0.28); axBt.tick_params(labelsize=FS_TICK)
    axBt.set_ylabel(r"$\Delta$ solve rate vs no-update", fontsize=FS_SMALL)
    axBt.set_title("B  Gemini 3.1 Pro: solve-rate change", fontsize=FS_TITLE, loc="left", fontweight="bold")
    for s in ("top", "right"): axBt.spines[s].set_visible(False)
    axBt.grid(axis="y", color="#e2e8f0", lw=0.7, zorder=0)

    # Panel B bottom: gold recovered in tool output, episode unsolved ------
    xr = list(range(len(REC))); vals = [v for _, v in REC]
    axBb.bar(xr, vals, 0.6, color=[BLACK, SHADOW, BLUE])
    for xi, v in zip(xr, vals):
        axBb.annotate(str(v), (xi, v), xytext=(0, 2), textcoords="offset points", ha="center",
                      va="bottom", fontsize=FS_SMALL, fontweight="bold" if v > 5 else "normal")
    axBb.set_xticks(xr); axBb.set_xticklabels([lab for lab, _ in REC], fontsize=FS_TICK)
    axBb.set_ylim(0, max(vals) * 1.35); axBb.margins(x=0.12); axBb.tick_params(labelsize=FS_TICK)
    axBb.set_ylabel("episodes", fontsize=FS_SMALL)
    axBb.set_title("Gold flag appears in tool output, episode unsolved", fontsize=FS_SUB, loc="left")
    axBb.text(1.0, -0.52, "n = 376 (no-update, L4), 368 (different-model)", transform=axBb.transAxes, ha="right",
              va="top", fontsize=7, color="#8a94a0", fontstyle="italic")
    for s in ("top", "right"): axBb.spines[s].set_visible(False)
    axBb.grid(axis="y", color="#e2e8f0", lw=0.7, zorder=0)

    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(out / f"fig_ctf.{ext}", dpi=300, bbox_inches="tight")
    print(f"wrote {out/'fig_ctf.png'} and .pdf")
    _appendix(out)


def _appendix(out: Path):
    fig, axB = plt.subplots(figsize=(5.4, 3.4))
    x = list(range(len(CATS))); w = 0.38
    b0 = axB.bar([xi - w/2 for xi in x], C0_COUNTS, w, color=GRAY, label="no-update (C0)")
    b1 = axB.bar([xi + w/2 for xi in x], L4_COUNTS, w, color=BLUE, label="L4 (RL, updates self)")
    for rect, c in zip(b0, C0_COUNTS):
        axB.annotate(str(c), (rect.get_x()+rect.get_width()/2, rect.get_height()),
                     xytext=(0, 2), textcoords="offset points", ha="center", va="bottom", fontsize=8)
    for i, (rect, c) in enumerate(zip(b1, L4_COUNTS)):
        axB.annotate(str(c), (rect.get_x()+rect.get_width()/2, rect.get_height()),
                     xytext=(0, 2), textcoords="offset points", ha="center", va="bottom",
                     fontsize=8, fontweight="bold" if i == 0 else "normal")
    axB.set_xticks(x); axB.set_xticklabels(CATS, fontsize=8)
    axB.set_ylabel("episodes (of 376)", fontsize=9); axB.set_ylim(0, max(L4_COUNTS)*1.25)
    axB.set_title("Gemini 3.1 Pro non-solve outcomes: no-update vs L4", fontsize=10, loc="left", fontweight="bold")
    for s in ("top", "right"): axB.spines[s].set_visible(False)
    axB.grid(axis="y", color="#e2e8f0", lw=0.7, zorder=0)
    axB.legend(handles=[Patch(color=GRAY, label="no-update (C0)"),
                        Patch(color=BLUE, label="L4 (RL, updates self)")],
               fontsize=8, loc="upper right", frameon=False)
    fig.tight_layout()
    for ext in ("png", "pdf"):
        fig.savefig(out / f"fig_ctf_appendix.{ext}", dpi=300, bbox_inches="tight")
    print(f"wrote {out/'fig_ctf_appendix.png'} and .pdf")


if __name__ == "__main__":
    main()
