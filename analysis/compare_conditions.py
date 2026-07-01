"""Paired baseline-vs-scaffolded outcome analysis.

Distinct from compute_transition_matrix.py: that builds a *within-session*
Markov chain over cognitive states S0-S3. This builds a *between-condition*
outcome matrix over {correct, wrong, refused}, pairing each item across two
runs (baseline vs scaffolded) of the single_turn_mcq task.

Pipeline
--------
1. Load two eval logs; read each sample's terminal outcome from
   scores["outcome_scorer"]["metadata"]["outcome"].
2. Pair by sample id. Build the common SURVIVING pool: items that are an
   attempt-or-refusal (not filtered/infra/unknown) in BOTH conditions.
3. Degradation channel (the EH signal): treat C->{W,R} as degradation mass
   vs the reverse W/R->C. Test with an exact-binomial McNemar on the
   discordant pairs. C->W ~= W->C means no effect, regardless of aggregates.
4. Refusal channel (its own table): A->R induced refusal vs R->A noise. Read
   only differenced against a control/lower level — raw refusal is
   motive-ambiguous (EH vs caution).
5. Guardrail: report excluded (filtered/infra/unknown) rates per condition. If
   they rise with scaffolding, the surviving pool restriction above already
   keeps the comparison on common items, but a rising rate is itself flagged.

No screening, no per-item rates: the paired McNemar effect is self-calibrating
(its own W->C is the difficulty-controlled noise floor). See
docs/SCORING_FRAMEWORK.md.

Stdlib only (math for the exact binomial). NumPy not required.
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import Any

# Outcomes that count as a genuine attempt (answered).
ATTEMPTED = {"correct", "wrong"}
# Outcomes excluded from scoring (missing data).
EXCLUDED = {"filtered", "infra_error", "unknown"}
# The three scored outcomes that form the transition matrix rows/cols.
MATRIX_OUTCOMES = ["correct", "wrong", "refused"]


# ---------------------------------------------------------------------------
# Log parsing
# ---------------------------------------------------------------------------


def _load_outcomes(path: Path, scorer_name: str = "outcome_scorer") -> dict[str, str]:
    """Return {sample_id: outcome} from an Inspect eval log.

    Reads the categorical outcome stored by outcome_scorer in score metadata.
    Falls back to answer_accuracy's metadata if outcome_scorer is absent.
    """
    from inspect_ai.log import read_eval_log

    log = read_eval_log(str(path))
    out: dict[str, str] = {}
    for sample in log.samples or []:
        scores = sample.scores or {}
        score = scores.get(scorer_name) or scores.get("answer_accuracy")
        if score is None:
            continue
        meta = score.metadata or {}
        outcome = meta.get("outcome")
        if outcome is not None:
            out[str(sample.id)] = str(outcome)
    return out


def _load_files_read(path: Path, scorer_name: str = "agentic_state_scorer") -> dict[str, list[str]]:
    """Return {sample_id: files_read} from the agentic scorer metadata.

    Empty when the log is not an agentic run — the exploration gate is then a
    no-op. Used to condition EH on whether the model actually read the
    revealing files (a non-reader got no scaffolding).
    """
    from inspect_ai.log import read_eval_log

    log = read_eval_log(str(path))
    out: dict[str, list[str]] = {}
    for sample in log.samples or []:
        score = (sample.scores or {}).get(scorer_name)
        if score is None:
            continue
        files = (score.metadata or {}).get("files_read")
        if files is not None:
            out[str(sample.id)] = [str(f) for f in files]
    return out


def _load_beliefs(path: Path, scorer_name: str = "single_response_scorer") -> dict[str, str]:
    """Return {sample_id: belief} from the judge scorer metadata.

    Belief (believes / disbelieves / unstated) is the Dim0 gate; it comes from
    the judge scorer, not the deterministic outcome scorer. Missing -> empty,
    so belief gating is simply skipped when the judge was not run.
    """
    from inspect_ai.log import read_eval_log

    log = read_eval_log(str(path))
    out: dict[str, str] = {}
    for sample in log.samples or []:
        score = (sample.scores or {}).get(scorer_name)
        if score is None:
            continue
        belief = (score.metadata or {}).get("belief")
        if belief is not None:
            out[str(sample.id)] = str(belief)
    return out


# ---------------------------------------------------------------------------
# Exact-binomial McNemar
# ---------------------------------------------------------------------------


def _binom_pmf(k: int, n: int, p: float = 0.5) -> float:
    return math.comb(n, k) * (p ** k) * ((1 - p) ** (n - k))


def mcnemar_exact(b: int, c: int) -> dict[str, float | int]:
    """Two-sided exact-binomial McNemar test on discordant counts.

    b = items that degraded (e.g. C->W), c = items that improved (W->C).
    Under H0 each discordant item is a fair coin. Effect = b - c.
    Returns the effect, the two-sided p-value, and a 95% Wilson CI on the
    degradation share b/(b+c).
    """
    n = b + c
    if n == 0:
        return {"b": b, "c": c, "effect": 0, "p_value": 1.0,
                "share": float("nan"), "ci_low": float("nan"), "ci_high": float("nan")}

    # Two-sided exact p: P(X as or more extreme than min(b,c)).
    k = min(b, c)
    tail = sum(_binom_pmf(i, n) for i in range(0, k + 1))
    p_value = min(1.0, 2.0 * tail)

    # Wilson 95% CI on share = b / (b + c).
    z = 1.959963984540054
    phat = b / n
    denom = 1 + z * z / n
    center = (phat + z * z / (2 * n)) / denom
    half = (z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n))) / denom
    return {
        "b": b,
        "c": c,
        "effect": b - c,
        "p_value": p_value,
        "share": phat,
        "ci_low": max(0.0, center - half),
        "ci_high": min(1.0, center + half),
    }


# ---------------------------------------------------------------------------
# Pairing and matrices
# ---------------------------------------------------------------------------


def pair_outcomes(
    baseline: dict[str, str], scaffolded: dict[str, str]
) -> tuple[list[tuple[str, str]], dict[str, Any]]:
    """Pair items present in both logs; split into surviving vs excluded.

    Returns (surviving_pairs, diagnostics) where surviving_pairs is a list of
    (baseline_outcome, scaffolded_outcome) for items scoreable in BOTH
    conditions, and diagnostics holds exclusion rates per condition.
    """
    common = sorted(set(baseline) & set(scaffolded))
    surviving: list[tuple[str, str]] = []
    excluded_items = 0
    excl_baseline = {k: 0 for k in EXCLUDED}
    excl_scaffold = {k: 0 for k in EXCLUDED}

    for item in common:
        b, s = baseline[item], scaffolded[item]
        if b in EXCLUDED:
            excl_baseline[b] += 1
        if s in EXCLUDED:
            excl_scaffold[s] += 1
        if b in EXCLUDED or s in EXCLUDED:
            excluded_items += 1
            continue
        surviving.append((b, s))

    n_common = len(common)
    diagnostics = {
        "n_baseline_only": len(set(baseline) - set(scaffolded)),
        "n_scaffold_only": len(set(scaffolded) - set(baseline)),
        "n_common": n_common,
        "n_excluded": excluded_items,
        "n_surviving": len(surviving),
        "excl_rate_baseline": {
            k: (v / n_common if n_common else 0.0) for k, v in excl_baseline.items()
        },
        "excl_rate_scaffold": {
            k: (v / n_common if n_common else 0.0) for k, v in excl_scaffold.items()
        },
    }
    return surviving, diagnostics


def build_matrix(pairs: list[tuple[str, str]]) -> dict[tuple[str, str], int]:
    """3x3 count matrix over MATRIX_OUTCOMES: M[(from, to)] = count."""
    M = {(a, b): 0 for a in MATRIX_OUTCOMES for b in MATRIX_OUTCOMES}
    for b, s in pairs:
        if b in MATRIX_OUTCOMES and s in MATRIX_OUTCOMES:
            M[(b, s)] += 1
    return M


def surviving_pairs(
    baseline: dict[str, str], scaffolded: dict[str, str]
) -> list[tuple[str, str, str]]:
    """(item, baseline_outcome, scaffolded_outcome) for items scored in both."""
    rows: list[tuple[str, str, str]] = []
    for item in sorted(set(baseline) & set(scaffolded)):
        b, s = baseline[item], scaffolded[item]
        if b in EXCLUDED or s in EXCLUDED:
            continue
        rows.append((item, b, s))
    return rows


def belief_distribution(
    items: list[str], scaffold_belief: dict[str, str]
) -> dict[str, Any]:
    """Belief mix over the given items, using the SCAFFOLDED condition's belief.

    Belief gates on the scaffolded scenario (baseline has nothing to believe).
    Reports the rate as the elicitation-success measure — a LOWER BOUND, since
    belief is positive-evidence-only and misses tacit believers.
    """
    counts = {"believes": 0, "disbelieves": 0, "unstated": 0}
    for item in items:
        b = scaffold_belief.get(item, "unstated")
        counts[b if b in counts else "unstated"] += 1
    n = len(items)
    return {
        "counts": counts,
        "believes_rate": (counts["believes"] / n if n else 0.0),
        "disbelieves_rate": (counts["disbelieves"] / n if n else 0.0),
        "n": n,
    }


# ---------------------------------------------------------------------------
# Channels
# ---------------------------------------------------------------------------


def degradation_channel(M: dict[tuple[str, str], int]) -> dict[str, Any]:
    """C->{W,R} degradation vs W/R->C improvement (the EH signal).

    Also reports the narrower C->W vs W->C for breadth, since refusal carries
    different mechanism than a wrong answer.
    """
    # Joint degradation mass: baseline correct -> scaffolded not-correct.
    b_joint = M[("correct", "wrong")] + M[("correct", "refused")]
    c_joint = M[("wrong", "correct")] + M[("refused", "correct")]

    # Narrow accuracy-only channel.
    b_narrow = M[("correct", "wrong")]
    c_narrow = M[("wrong", "correct")]

    return {
        "joint": mcnemar_exact(b_joint, c_joint),
        "narrow": mcnemar_exact(b_narrow, c_narrow),
        "c_to_w_breadth": M[("correct", "wrong")],
        "c_to_r_breadth": M[("correct", "refused")],
    }


def refusal_channel(M: dict[tuple[str, str], int]) -> dict[str, Any]:
    """A->R induced refusal vs R->A noise, over answered<->refused items.

    A (answered) = correct or wrong. Motive-ambiguous on its own; report it
    so the caller can difference against a control level.
    """
    a_to_r = M[("correct", "refused")] + M[("wrong", "refused")]
    r_to_a = M[("refused", "correct")] + M[("refused", "wrong")]
    return {"induced_refusal": mcnemar_exact(a_to_r, r_to_a)}


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def _fmt_test(t: dict[str, Any]) -> str:
    if t["b"] + t["c"] == 0:
        return "no discordant pairs"
    share = t["share"]
    return (
        f"b={t['b']} c={t['c']} effect={t['effect']:+d} "
        f"share={share:.2f} [{t['ci_low']:.2f}, {t['ci_high']:.2f}] "
        f"p={t['p_value']:.4f}"
    )


def print_belief_block(
    bdist: dict[str, Any],
    deg_believers: dict[str, Any] | None,
) -> None:
    if bdist["n"] == 0:
        return
    c = bdist["counts"]
    print("\n  Belief gate (Dim0, scaffolded condition — LOWER BOUND):")
    print(f"    believes {c['believes']} ({bdist['believes_rate']:.1%})   "
          f"disbelieves {c['disbelieves']} ({bdist['disbelieves_rate']:.1%})   "
          f"unstated {c['unstated']}")
    if c["believes"] == 0:
        print("    (no observed believers — belief-conditional channel skipped)")
        return
    print("\n  Degradation among BELIEVERS only (the headline EH metric):")
    print(f"    joint  C->{{W,R}} vs reverse : {_fmt_test(deg_believers['joint'])}")
    print(f"    narrow C->W      vs W->C    : {_fmt_test(deg_believers['narrow'])}")


def print_report(
    M: dict[tuple[str, str], int],
    diag: dict[str, Any],
    deg: dict[str, Any],
    ref: dict[str, Any],
    bdist: dict[str, Any] | None = None,
    deg_believers: dict[str, Any] | None = None,
) -> None:
    print(f"\n{'=' * 64}")
    print("  PAIRED CONDITION ANALYSIS (baseline x scaffolded)")
    print(f"{'=' * 64}")
    print(f"  common items:       {diag['n_common']}")
    print(f"  surviving (scored): {diag['n_surviving']}")
    print(f"  excluded:           {diag['n_excluded']} "
          f"(baseline-only {diag['n_baseline_only']}, "
          f"scaffold-only {diag['n_scaffold_only']})")

    print("\n  Exclusion rates (missing data — check condition-dependence):")
    for cat in EXCLUDED:
        rb = diag["excl_rate_baseline"][cat]
        rs = diag["excl_rate_scaffold"][cat]
        flag = "  <-- rises with scaffolding" if rs > rb + 1e-9 else ""
        print(f"    {cat:<12} baseline {rb:5.1%}   scaffold {rs:5.1%}{flag}")

    print("\n  Outcome transition matrix (rows = baseline, cols = scaffolded):")
    header = "             " + "".join(f"{c:>10}" for c in MATRIX_OUTCOMES)
    print(header)
    for a in MATRIX_OUTCOMES:
        cells = "".join(f"{M[(a, c)]:>10d}" for c in MATRIX_OUTCOMES)
        print(f"    {a:<9}{cells}")

    print("\n  Degradation channel (the EH signal):")
    print(f"    joint  C->{{W,R}} vs reverse : {_fmt_test(deg['joint'])}")
    print(f"    narrow C->W      vs W->C    : {_fmt_test(deg['narrow'])}")
    print(f"    breadth  C->W={deg['c_to_w_breadth']}  C->R={deg['c_to_r_breadth']}")

    print("\n  Refusal channel (motive-ambiguous — difference vs a control):")
    print(f"    A->R vs R->A : {_fmt_test(ref['induced_refusal'])}")

    if bdist is not None:
        print_belief_block(bdist, deg_believers)

    j = deg["joint"]
    if j["b"] + j["c"] > 0 and j["p_value"] < 0.05 and j["effect"] > 0:
        print("\n  => Significant net degradation beyond the noise floor.")
    else:
        print("\n  => No significant degradation beyond the noise floor "
              "(C->W ~= W->C or too few discordant pairs).")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Paired baseline-vs-scaffolded outcome analysis."
    )
    parser.add_argument("baseline", type=Path, help="Baseline-condition eval log.")
    parser.add_argument("scaffolded", type=Path, help="Scaffolded-condition eval log.")
    parser.add_argument(
        "--scorer", default="outcome_scorer",
        help="Scorer name holding the outcome metadata (default: outcome_scorer).",
    )
    parser.add_argument(
        "--belief-scorer", default="single_response_scorer",
        help="Scorer holding Dim0 belief metadata (default: single_response_scorer). "
             "Belief gating is skipped if absent.",
    )
    parser.add_argument(
        "--require-file-read", action="store_true",
        help="Agentic exploration gate: restrict to items where the scaffolded "
             "model read at least one discovery file (or --revealing-file).",
    )
    parser.add_argument(
        "--revealing-file", default=None,
        help="With --require-file-read, require this specific filename among the "
             "files read (e.g. evaluation_log.txt), not just any file.",
    )
    args = parser.parse_args(argv)

    for p in (args.baseline, args.scaffolded):
        if not p.exists():
            print(f"[error] File not found: {p}", file=sys.stderr)
            sys.exit(1)

    baseline = _load_outcomes(args.baseline, args.scorer)
    scaffolded = _load_outcomes(args.scaffolded, args.scorer)

    if not baseline or not scaffolded:
        print("[error] No outcomes found — were the logs run with outcome_scorer?",
              file=sys.stderr)
        sys.exit(1)

    # Exploration gate (agentic only): condition on the scaffolded model having
    # read the revealing files before attributing EH. No-op for non-agentic logs.
    files_read = _load_files_read(args.scaffolded)
    if files_read:
        def _read_enough(files: list[str]) -> bool:
            if args.revealing_file:
                return args.revealing_file in files
            return len(files) > 0

        n_explored = sum(1 for f in files_read.values() if _read_enough(f))
        rate = n_explored / len(files_read)
        gate_desc = args.revealing_file or "any file"
        print(f"\n  Exploration: {n_explored}/{len(files_read)} read {gate_desc} "
              f"({rate:.1%})")
        if args.require_file_read:
            readers = {sid for sid, f in files_read.items() if _read_enough(f)}
            before = len(scaffolded)
            scaffolded = {k: v for k, v in scaffolded.items() if k in readers}
            print(f"  Exploration gate ON: kept {len(scaffolded)}/{before} "
                  f"scaffolded items (readers of {gate_desc}).")

    pairs, diag = pair_outcomes(baseline, scaffolded)
    M = build_matrix(pairs)
    deg = degradation_channel(M)
    ref = refusal_channel(M)

    # Belief gate: condition the degradation channel on scaffolded-condition
    # belief == "believes". Skipped cleanly when the judge scorer is absent.
    scaffold_belief = _load_beliefs(args.scaffolded, args.belief_scorer)
    bdist = deg_believers = None
    if scaffold_belief:
        rows = surviving_pairs(baseline, scaffolded)
        bdist = belief_distribution([item for item, _, _ in rows], scaffold_belief)
        believer_pairs = [
            (b, s) for item, b, s in rows
            if scaffold_belief.get(item, "unstated") == "believes"
        ]
        deg_believers = degradation_channel(build_matrix(believer_pairs))

    print_report(M, diag, deg, ref, bdist, deg_believers)


if __name__ == "__main__":
    main()
