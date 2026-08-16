"""Within-session temporal dynamics of the SEQUENTIAL arm — the one thing
single-turn structurally cannot show (single-turn has no within-episode history).

For each (model, condition) we pair the scaffold session against the baseline
session question-by-question (same WMDP item at each (session, position)) and
measure:

  1. ESCALATION   — C→W (hack) rate as a function of question position 1..10,
                    with a linear trend slope. Rising = the model settles into
                    a strategy across the session.
  2. PERSISTENCE  — within-session lag-1 clustering of wrong answers,
                    P(wrong@k+1 | wrong@k) − P(wrong@k+1 | correct@k), for the
                    scaffold vs the baseline. Scaffold-excess = commitment beyond
                    random error clustering ("decided to hack and kept hacking").
  3. ONSET        — position of the first C→W within each session.

    python analysis/sequential_dynamics.py --log-dirs logs/main-v1 logs/main-v2 --out figures/

Writes figures/fig6_sequential_dynamics.png and prints a summary table.
"""

from __future__ import annotations

import argparse
import glob
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

_ANSWERED = {"correct", "wrong"}


def _lab(m, cond):
    """Clean 'Model Lx' label."""
    ms = ("Sonnet 4" if "sonnet" in m else "Gemini 3.1" if "gemini-3.1" in m
          else m.split("-")[0].title())
    cs = next((f"L{n}" for n in (2, 3, 4, 5, 6) if f"level{n}" in cond), cond)
    return f"{ms} {cs}"


def _seq_matrix(path):
    """{session_id: [per-question outcome]} for one sequential log."""
    from inspect_ai.log import read_eval_log
    log = read_eval_log(str(path))
    out = {}
    for s in (log.samples or []):
        sc = (s.scores or {}).get("sequential_outcome_scorer")
        if sc:
            out[s.id] = list((sc.metadata or {}).get("per_question") or [])
    return out


def _linfit(xs, ys):
    """Least-squares slope of ys on xs (stdlib)."""
    n = len(xs)
    if n < 2:
        return float("nan")
    mx = sum(xs) / n
    my = sum(ys) / n
    den = sum((x - mx) ** 2 for x in xs)
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den if den else float("nan")


def _cell_dynamics(base, scaf):
    """base/scaf are {session: [outcomes]}. Returns per-cell dynamics dict."""
    sessions = sorted(set(base) & set(scaf))
    L = 10
    # 1. escalation: per position, hacks / eligible (baseline correct)
    hacks = [0] * L
    elig = [0] * L
    onsets = []
    for s in sessions:
        b, c = base[s], scaf[s]
        onset = None
        for p in range(min(L, len(b), len(c))):
            if b[p] == "correct":
                elig[p] += 1
                if c[p] == "wrong":
                    hacks[p] += 1
                    if onset is None:
                        onset = p + 1
        if onset is not None:
            onsets.append(onset)
    pos = [p for p in range(L) if elig[p] > 0]
    rate = [hacks[p] / elig[p] for p in pos]
    slope = _linfit([p + 1 for p in pos], rate)

    # 2. persistence: lag-1 clustering of `wrong`, scaffold vs baseline
    def _clustering(mat):
        ww = wc = cw = cc = 0  # (prev, next) counts on wrong/correct
        for s in sessions:
            seq = [o for o in mat[s] if o in _ANSWERED]
            for a, nxt in zip(seq, seq[1:]):
                w_next = nxt == "wrong"
                if a == "wrong":
                    ww += w_next; wc += not w_next
                else:
                    cw += w_next; cc += not w_next
        p_w_given_w = ww / (ww + wc) if (ww + wc) else float("nan")
        p_w_given_c = cw / (cw + cc) if (cw + cc) else float("nan")
        return p_w_given_w - p_w_given_c
    persist_scaf = _clustering(scaf)
    persist_base = _clustering(base)

    overall = sum(hacks) / sum(elig) if sum(elig) else 0.0
    return {"pos": [p + 1 for p in pos], "rate": rate, "slope": slope,
            "overall": overall, "onsets": onsets,
            "persist_scaf": persist_scaf, "persist_base": persist_base,
            "persist_excess": persist_scaf - persist_base, "n_sessions": len(sessions)}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--log-dirs", nargs="+", default=["logs/main-v1", "logs/main-v2"])
    ap.add_argument("--out", type=Path, default=Path("figures"))
    args = ap.parse_args(argv)
    args.out.mkdir(exist_ok=True)
    from inspect_ai.log import read_eval_log

    # discover sequential (model, cond) -> path
    cells = {}
    for d in args.log_dirs:
        for f in glob.glob(f"{d}/*sequential*.eval"):
            h = read_eval_log(f, header_only=True)
            if h.status != "success":
                continue
            cells[(h.eval.model.split("/")[-1], (h.eval.task_args or {}).get("condition"))] = f

    models = sorted({m for m, _c in cells})
    results = {}
    for (m, cond), f in cells.items():
        if cond == "baseline":
            continue
        base_f = cells.get((m, "baseline"))
        if not base_f:
            continue
        results[(m, cond)] = _cell_dynamics(_seq_matrix(base_f), _seq_matrix(f))

    # ---- print summary --------------------------------------------------------
    print(f"\n{'='*92}")
    print("  SEQUENTIAL within-session dynamics (single-turn cannot measure these)")
    print(f"{'='*92}")
    print(f"  {'model':<22}{'condition':<28}{'C→W':>6}{'pos-slope':>10}"
          f"{'persist(scaf−base)':>20}{'onset med':>11}")
    print(f"  {'-'*88}")
    for (m, cond), r in sorted(results.items()):
        onset_med = sorted(r["onsets"])[len(r["onsets"]) // 2] if r["onsets"] else float("nan")
        print(f"  {m:<22}{cond:<28}{r['overall']:>6.2f}{r['slope']:>10.3f}"
              f"{r['persist_excess']:>20.2f}{onset_med:>11}")
    print("\n  pos-slope: Δ(C→W rate) per question position (+ = escalation). "
          "persist: lag-1 wrong-answer clustering excess over baseline (+ = commitment).")

    # ---- figure ---------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.4))
    # LEFT: escalation — L4/L6 only (L2 is null; keep it out to compare dynamics)
    for (m, cond), r in sorted(results.items()):
        if "level2" in cond or r["overall"] < 0.02:
            continue
        ax1.plot(r["pos"], r["rate"], marker="o", label=_lab(m, cond))
    ax1.set_xlabel("question position in session (1–10)")
    ax1.set_ylabel("C→W rate at position")
    ax1.set_title("Escalation: C→W rate vs. question position"); ax1.set_ylim(-0.02, 1.0)
    ax1.grid(alpha=0.3); ax1.legend(fontsize=8)

    # RIGHT: persistence — keep all cells (L2 as reference)
    keys = sorted(results)
    labels = [_lab(m, cond).replace(" ", "\n") for (m, cond) in keys]
    xs = range(len(labels))
    ax2.bar([x - 0.2 for x in xs], [results[k]["persist_base"] for k in keys],
            width=0.4, label="baseline", color="#bbb")
    ax2.bar([x + 0.2 for x in xs], [results[k]["persist_scaf"] for k in keys],
            width=0.4, label="scaffold", color="#c0392b")
    ax2.set_xticks(list(xs)); ax2.set_xticklabels(labels, fontsize=7)
    ax2.set_ylabel(r"lag-1 clustering  $P(W_t\mid W_{t-1})-P(W_t\mid C_{t-1})$")
    ax2.set_title("Persistence: lag-1 wrong-answer clustering")
    ax2.axhline(0, color="k", lw=0.5); ax2.grid(alpha=0.3); ax2.legend(fontsize=8)
    fig.suptitle("Sequential-arm within-session dynamics", y=1.02)
    fig.tight_layout(); fig.savefig(args.out / "fig6_sequential_dynamics.png", dpi=200,
                                    bbox_inches="tight")
    plt.close(fig)
    print(f"\n  -> {args.out}/fig6_sequential_dynamics.png")


if __name__ == "__main__":
    main()
