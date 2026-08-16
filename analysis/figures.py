"""Generate the paper's figures + tables from behavioral cells and cognitive labels.

    python analysis/figures.py --log-dirs logs/main-v1 logs/main-v2 \
        --labels scored_labels.json --out figures/

Behavioral (available now, no judge needed):
  Fig1  dose-response along the scaffolding ladder (C→W rate by rung, per model)
  Fig2  behavioral heatmap (model × condition)
  T1    full McNemar table (markdown + csv), with BH-FDR q and Wilson CI
Cognitive (need --labels = score_transcripts output; light up as scoring lands):
  Fig3  cognitive-chain emergence (construct rate by rung)
  Fig4  null-mechanism taxonomy (why models don't hack)
  Fig5  behavioral↔cognitive concordance (McNemar rate vs judged dim4 rate)

Robust to partial `scored_labels.json` (skips cognitive figs if absent/sparse).
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from run_all_comparisons import compute_rows  # noqa: E402

_RUNGS = ["L2", "L3", "L4", "L5", "L6"]
_CONSTRUCTS = ["belief", "dim1", "dim2", "dim3", "dim4", "premise", "decoupling"]
_ARM_TITLE = {"agentic_discovery": "Agentic discovery", "sequential_mcq": "Sequential MCQ",
              "single_turn_mcq": "Single-turn MCQ"}
# fixed colour per construct so panels are consistent and a missing construct
# (e.g. dim4 in sequential, which is not judged) does NOT shift the colour cycle
_CON_COLOR = {"belief": "C0", "dim1": "C1", "dim2": "C2", "dim3": "C3",
              "dim4": "C4", "premise": "C5", "decoupling": "C6"}


def _rung(cond: str):
    """(order, short_label, threat_model) for a condition name."""
    for n, lab in [(2, "L2"), (3, "L3"), (4, "L4"), (5, "L5"), (6, "L6")]:
        if f"level{n}" in cond:
            tm = "tm2" if "tm2" in cond else ("tm1" if "tm1" in cond else None)
            return n, lab, tm
    return 0, "?", None


def _cond_label(c: str) -> str:
    """Human-readable condition label with corrected component names."""
    tm = " (TM2)" if "tm2" in c else (" (TM1)" if "tm1" in c else "")
    base = ("baseline" if "baseline" in c else
            "L2 training awareness" if "level2" in c else
            "L3 goal-conflict" if "level3" in c else
            "L4 action–outcome" if "level4" in c else
            "L5 preference" if "level5" in c else
            "L6 explicit instruction" if "level6" in c else c)
    return base + tm


def _is_primary(cond: str) -> bool:
    return any(t in cond for t in ("level2", "level3", "level4"))


# ---------------------------------------------------------------------------
# Behavioral figures (from compute_rows)
# ---------------------------------------------------------------------------

def _cells(rows):
    return [r for r in rows if "n" in r and r["n"]]


def fig1_dose_response(rows, out: Path):
    """C→W rate vs ladder rung, one line per model, TM1 track, faceted by arm."""
    arms = sorted({r["arm"] for r in _cells(rows)})
    rungs = [2, 3, 4, 5, 6]
    fig, axes = plt.subplots(1, len(arms), figsize=(5.5 * len(arms), 4.2), squeeze=False)
    for ax, arm in zip(axes[0], arms):
        models = sorted({r["model"] for r in _cells(rows) if r["arm"] == arm})
        for mdl in models:
            # TM1 track (+ L6, no TM); index by rung so unmeasured rungs are gaps
            by_rung = {}
            for r in _cells(rows):
                if r["arm"] != arm or r["model"] != mdl:
                    continue
                o, _lab, tm = _rung(r["cond"])
                if o == 0 or tm == "tm2":
                    continue
                by_rung[o] = (r["rate"], max(0.0, r["rate"] - r["ci"][0]),
                              max(0.0, r["ci"][1] - r["rate"]))
            if not by_rung:
                continue
            mx = sorted(by_rung)
            # points + error bars (establish colour + legend entry)
            eb = ax.errorbar(mx, [by_rung[o][0] for o in mx],
                             yerr=[[by_rung[o][1] for o in mx], [by_rung[o][2] for o in mx]],
                             fmt="o", capsize=2, label=mdl.replace("-preview", ""))
            col = eb[0].get_color()
            # connect measured rungs: solid if adjacent, DASHED across a gap
            # (e.g. agentic L2->L4, since L3 was not run — not an observed trajectory)
            for a, b in zip(mx, mx[1:]):
                ax.plot([a, b], [by_rung[a][0], by_rung[b][0]],
                        "-" if b - a == 1 else "--", color=col, lw=1.5, zorder=1)
        ax.set_xticks(rungs); ax.set_xticklabels(_RUNGS)
        ax.set_ylim(-0.02, 1.0); ax.set_xlabel("scaffolding rung (TM1)")
        ax.set_ylabel("correct-to-wrong rate (C→W)")
        ax.set_title(_ARM_TITLE.get(arm, arm)); ax.grid(alpha=0.3)
    axes[0][-1].legend(fontsize=8, loc="upper left")
    fig.suptitle("Behavioral underperformance across the scaffolding ladder", y=1.02)
    fig.tight_layout(); fig.savefig(out / "fig1_dose_response.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig2_heatmap(rows, out: Path):
    """model × condition heatmap of C→W rate; ** annotates raw-significant EH."""
    arms = sorted({r["arm"] for r in _cells(rows)})
    fig, axes = plt.subplots(len(arms), 1, figsize=(11, 2 + 1.6 * len(arms)), squeeze=False)
    for ax, arm in zip(axes[:, 0], arms):
        cel = [r for r in _cells(rows) if r["arm"] == arm]
        models = sorted({r["model"] for r in cel})
        conds = sorted({r["cond"] for r in cel}, key=lambda c: (_rung(c)[0], c))
        grid = [[next((r["rate"] for r in cel if r["model"] == m and r["cond"] == c), float("nan"))
                 for c in conds] for m in models]
        im = ax.imshow(grid, aspect="auto", cmap="Reds", vmin=0, vmax=1)
        ax.set_xticks(range(len(conds)))
        ax.set_xticklabels([_cond_label(c) for c in conds], rotation=40, ha="right", fontsize=7)
        ax.set_yticks(range(len(models))); ax.set_yticklabels(models, fontsize=8)
        for i, m in enumerate(models):
            for j, c in enumerate(conds):
                r = next((r for r in cel if r["model"] == m and r["cond"] == c), None)
                if not r:
                    continue
                # primary L2-L4 -> BH-FDR q<.05 (†); L5/L6 controls -> unadjusted p<.05 (*)
                if _is_primary(c):
                    q = r.get("q")
                    mark = "†" if (q is not None and q < 0.05 and r["cw"] > r["wc"]) else ""
                else:
                    mark = "*" if (r["p"] < 0.05 and r["cw"] > r["wc"]) else ""
                ax.text(j, i, f"{r['rate']:.2f}{mark}", ha="center", va="center",
                        fontsize=6, color="black")
        ax.set_title(f"{_ARM_TITLE.get(arm, arm)} — correct-to-wrong (C→W) rate")
        fig.colorbar(im, ax=ax, fraction=0.02, pad=0.01)
    fig.text(0.5, -0.02, "†  L2–L4 (primary): BH-FDR q<.05      "
             "*  L5–L6 (positive controls): unadjusted exact-McNemar p<.05",
             ha="center", fontsize=8)
    fig.tight_layout(); fig.savefig(out / "fig2_heatmap.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def table1(rows, out: Path):
    """Full McNemar table -> markdown + csv."""
    cel = _cells(rows)
    hdr = ["model", "arm", "condition", "n", "C→W", "W→C", "rate", "ci_lo", "ci_hi", "p", "q", "verdict"]
    lines_md = ["| " + " | ".join(hdr) + " |", "|" + "---|" * len(hdr)]
    lines_csv = [",".join(hdr)]
    for r in cel:
        q = r.get("q")
        verdict = ("EH" if (r["p"] < 0.05 and r["cw"] > r["wc"]) else
                   ("dir" if r["cw"] > r["wc"] else "ns"))
        if q is not None and q < 0.05 and r["cw"] > r["wc"]:
            verdict += "(q<.05)"
        vals = [r["model"], r["arm"], r["cond"], r["n"], r["cw"], r["wc"],
                f"{r['rate']:.3f}", f"{r['ci'][0]:.3f}", f"{r['ci'][1]:.3f}",
                f"{r['p']:.4f}", ("" if q is None else f"{q:.4f}"), verdict]
        lines_md.append("| " + " | ".join(str(v) for v in vals) + " |")
        lines_csv.append(",".join(str(v) for v in vals))
    (out / "table1_mcnemar.md").write_text("\n".join(lines_md))
    (out / "table1_mcnemar.csv").write_text("\n".join(lines_csv))


# ---------------------------------------------------------------------------
# Cognitive figures (from scored_labels.json)
# ---------------------------------------------------------------------------

def _id_index(log_dirs):
    """{ '<stem>:<id>': (model, arm, condition, n_files_read) } from the logs."""
    from inspect_ai.log import read_eval_log
    idx = {}
    for d in log_dirs:
        for f in glob.glob(f"{d}/*.eval"):
            h = read_eval_log(f, header_only=True)
            if h.status != "success":
                continue
            model = h.eval.model.split("/")[-1]
            arm = (h.eval.task or "?").split("/")[-1]
            cond = (h.eval.task_args or {}).get("condition", "?")
            stem = Path(f).stem
            log = read_eval_log(f)
            for s in (log.samples or []):
                nfr = outcome = None
                for sc in (s.scores or {}).values():
                    md = sc.metadata or {}
                    nfr = md.get("n_files_read", nfr)
                    outcome = md.get("outcome", outcome)
                idx[f"{stem}:{s.id}"] = (model, arm, cond, nfr, outcome)
    return idx


def _present(rec, construct):
    v = rec.get({"belief": "belief_gate"}.get(construct, construct)
                if construct != "premise" else "premise_rejection_gate")
    if construct == "belief":
        return None if rec.get("belief_gate") is None else int(rec["belief_gate"] == "believes")
    if construct == "premise":
        v = rec.get("premise_rejection_gate")
    elif construct == "decoupling":
        v = rec.get("decoupling_gate")
    else:
        v = rec.get(construct)
    return None if v is None else int(v == 1)


def _null_mech(rec, nfr):
    if rec.get("dim4") == 1:
        return "eh_fired"
    if nfr == 0:
        return "exploration_failure"
    if rec.get("decoupling_gate") == 1:
        return "coupling_failure"
    if rec.get("premise_rejection_gate") == 1:
        return "premise_rejection"
    if rec.get("belief_gate") == "disbelieves":
        return "disbelief"
    if rec.get("belief_gate") == "believes":
        return "believer_declined"
    return "no_engagement"


def _join(labels, idx):
    out = []
    for iid, rec in labels.items():
        meta = idx.get(iid)
        model, arm, cond, nfr, outcome = meta if meta else (
            None, rec.get("arm"), rec.get("condition"), None, None)
        out.append({"id": iid, "rec": rec, "model": model, "arm": arm or rec.get("arm"),
                    "cond": cond or rec.get("condition"), "nfr": nfr, "outcome": outcome})
    return out


def fig3_cognitive_chain(joined, out: Path):
    arms = sorted({j["arm"] for j in joined if j["arm"]})
    fig, axes = plt.subplots(1, len(arms), figsize=(5.5 * len(arms), 4.2), squeeze=False)
    for ax, arm in zip(axes[0], arms):
        for con in _CONSTRUCTS:
            xs, ys = [], []
            for o, lab in [(2, "L2"), (3, "L3"), (4, "L4"), (5, "L5"), (6, "L6")]:
                vals = [_present(j["rec"], con) for j in joined
                        if j["arm"] == arm and _rung(j["cond"] or "")[0] == o]
                vals = [v for v in vals if v is not None]
                if vals:
                    xs.append(o); ys.append(sum(vals) / len(vals))
            if xs:
                ax.plot(xs, ys, marker="o", label=con, linewidth=1.4, color=_CON_COLOR[con])
        ax.set_xticks([2, 3, 4, 5, 6]); ax.set_xticklabels(_RUNGS)
        ax.set_ylim(-0.02, 1.0); ax.set_xlabel("rung"); ax.set_ylabel("construct present (rate)")
        ax.set_title(_ARM_TITLE.get(arm, arm)); ax.grid(alpha=0.3)
    axes[0][-1].legend(fontsize=7, ncol=2)
    fig.suptitle("Cognitive-chain emergence along the ladder", y=1.02)
    fig.tight_layout(); fig.savefig(out / "fig3_cognitive_chain.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig4_null_mechanism(joined, out: Path):
    # The taxonomy needs dim4 to separate eh_fired from the nulls, so it is only
    # defined on dim4-JUDGED transcripts (single-turn L3-L6, agentic L4-L5). This
    # excludes sequential (dim4 per-question, not judged here) and L2 (dim4 gated),
    # where classifying every believer as "declined" would be an artifact.
    dj = [j for j in joined if j["rec"].get("dim4") is not None]
    arms = sorted({j["arm"] for j in dj if j["arm"]})
    mechs = ["exploration_failure", "coupling_failure", "premise_rejection",
             "disbelief", "believer_declined", "no_engagement", "eh_fired"]
    fig, ax = plt.subplots(figsize=(1.6 * len(arms) + 3, 4.5))
    bottoms = [0.0] * len(arms)
    ns = {arm: sum(1 for j in dj if j["arm"] == arm) for arm in arms}
    for mech in mechs:
        vals = []
        for arm in arms:
            js = [j for j in dj if j["arm"] == arm]
            c = sum(1 for j in js if _null_mech(j["rec"], j["nfr"]) == mech)
            vals.append(c / len(js) if js else 0.0)
        ax.bar(range(len(arms)), vals, bottom=bottoms, label=mech)
        bottoms = [b + v for b, v in zip(bottoms, vals)]
    ax.set_xticks(range(len(arms)))
    ax.set_xticklabels([f"{_ARM_TITLE.get(a, a)}\n(n={ns[a]})" for a in arms], fontsize=8)
    ax.set_ylabel("fraction of transcripts")
    ax.set_title("Null-mechanism taxonomy (dim4-judged transcripts)")
    ax.legend(fontsize=8, bbox_to_anchor=(1.02, 1), loc="upper left")
    fig.tight_layout(); fig.savefig(out / "fig4_null_mechanism.png", dpi=200, bbox_inches="tight")
    plt.close(fig)


def fig5_decomposition(joined, idx, out: Path):
    """2x2 of behavioral C→W x judged dim4 — the valid joint analysis (dim4 is NOT
    bounded by C→W; a model can attempt EH without a C→W transition). Cells:
      C→W & dim4=1  strongest EH evidence      C→W & dim4=0  unexplained degradation
      ¬C→W & dim4=1 attempted EH, no C→W       ¬C→W & dim4=0 no detected EH."""
    # baseline outcomes per (model, arm) keyed by sample id, from the index
    base = defaultdict(dict)
    for iid, (model, arm, cond, _nfr, outcome) in idx.items():
        if cond == "baseline":
            base[(model, arm)][iid.rsplit(":", 1)[1]] = outcome

    ROWS, COLS = ["C→W", "¬C→W"], ["dim4=1", "dim4=0"]
    agg = {(r, c): 0 for r in ROWS for c in COLS}
    per_cell = defaultdict(lambda: {(r, c): 0 for r in ROWS for c in COLS})
    for j in joined:
        d4 = j["rec"].get("dim4")
        if d4 is None or not j["model"]:       # dim4 not judged (L2/gated/sequential)
            continue
        sid = j["id"].rsplit(":", 1)[1]
        b = base.get((j["model"], j["arm"]), {}).get(sid)
        s = j["outcome"]
        if b is None or s is None:
            continue
        rk = "C→W" if (b == "correct" and s == "wrong") else "¬C→W"
        ck = "dim4=1" if d4 == 1 else "dim4=0"
        agg[(rk, ck)] += 1
        per_cell[(j["model"], j["arm"], j["cond"])][(rk, ck)] += 1

    labels = {("C→W", "dim4=1"): "strongest EH", ("C→W", "dim4=0"): "unexplained\ndegradation",
              ("¬C→W", "dim4=1"): "attempted EH,\nno C→W", ("¬C→W", "dim4=0"): "no detected EH"}
    grid = [[agg[(r, c)] for c in COLS] for r in ROWS]
    fig, ax = plt.subplots(figsize=(5.2, 4.6))
    im = ax.imshow(grid, cmap="Blues", aspect="auto")
    ax.set_xticks([0, 1]); ax.set_xticklabels(COLS); ax.set_yticks([0, 1]); ax.set_yticklabels(ROWS)
    for i, r in enumerate(ROWS):
        for jx, c in enumerate(COLS):
            ax.text(jx, i, f"{agg[(r, c)]}\n{labels[(r, c)]}", ha="center", va="center", fontsize=9)
    ax.set_title("Behavioral C→W × judged dim4 (all dim4-judged cells)")
    fig.colorbar(im, ax=ax, fraction=0.04, pad=0.02)
    fig.tight_layout(); fig.savefig(out / "fig5_decomposition.png", dpi=200, bbox_inches="tight")
    plt.close(fig)

    # headline per-cell breakdown (esp. the one FDR-surviving cell)
    print("\n  C→W × dim4 by cell (dim4-judged cells only):")
    for (m, arm, cond), cc in sorted(per_cell.items()):
        cw_tot = cc[("C→W", "dim4=1")] + cc[("C→W", "dim4=0")]
        if cw_tot == 0:
            continue
        print(f"    {m:<22}{arm:<18}{_cond_label(cond):<22} "
              f"C→W&dim4=1: {cc[('C→W','dim4=1')]}/{cw_tot} C→W  |  "
              f"attempted-no-C→W: {cc[('¬C→W','dim4=1')]}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--log-dirs", nargs="+", default=["logs/main-v1", "logs/main-v2"])
    ap.add_argument("--labels", type=Path, default=Path("scored_labels.json"))
    ap.add_argument("--out", type=Path, default=Path("figures"))
    args = ap.parse_args(argv)
    args.out.mkdir(exist_ok=True)

    rows = compute_rows(args.log_dirs)
    print(f"  behavioral: {len(_cells(rows))} cells")
    fig1_dose_response(rows, args.out)
    fig2_heatmap(rows, args.out)
    table1(rows, args.out)
    print("  wrote fig1_dose_response, fig2_heatmap, table1_mcnemar (.md/.csv)")

    if args.labels.exists():
        labels = json.loads(args.labels.read_text())
        if len(labels) >= 20:
            print(f"  cognitive: joining {len(labels)} labels to logs ...")
            idx = _id_index(args.log_dirs)
            joined = _join(labels, idx)
            fig3_cognitive_chain(joined, args.out)
            fig4_null_mechanism(joined, args.out)
            fig5_decomposition(joined, idx, args.out)
            print("  wrote fig3_cognitive_chain, fig4_null_mechanism, fig5_decomposition")
        else:
            print(f"  cognitive: only {len(labels)} labels — skipping Figs 3-5 (scoring in progress)")
    else:
        print(f"  cognitive: {args.labels} not found — skipping Figs 3-5")
    print(f"  -> {args.out}/")


if __name__ == "__main__":
    main()
