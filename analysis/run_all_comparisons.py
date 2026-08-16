"""Discover-and-run: paired McNemar for every (model, scaffold condition).

Reads (model, condition) from each log's METADATA — no filename matching. For
each model it merges the baseline batches (e.g. a first-50 run + an offset
append) by id, then compares every scaffold condition against that baseline on
the narrow correct->wrong channel. Belief/premise gate columns appear when a
judge scorer is present in the logs (skipped for judge-off runs).

    python analysis/run_all_comparisons.py --log-dirs logs/main-v1 logs/main-v2

The point: you never hand-match opaque log filenames — the mapping lives in each
log's header (eval.model, task_args.condition), so this does it for all cells at
once, merging batches and guarding against id collisions.
"""

from __future__ import annotations

import argparse
import glob
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from compare_conditions import (  # noqa: E402
    _load_outcomes,
    _load_beliefs,
    pair_outcomes,
    build_matrix,
    degradation_channel,
)

# scaffolding order for a readable table
_ORDER = [
    "level2_training_awareness", "level3_goal_conflict_tm1", "level3_goal_conflict_tm2",
    "level4_action_knowledge_tm1", "level4_action_knowledge_tm2",
    "level5_desire_nudge_tm1", "level5_desire_nudge_tm2", "level6_explicit_instruction",
    "level2", "level4-tm1", "level4-tm2", "level5-tm1",  # agentic condition names
]


def _load_sequential_outcomes(path, scorer_name: str = "sequential_outcome_scorer") -> dict:
    """Flatten a sequential log into per-question outcomes keyed `s<session>:q<pos>`.

    `sequential_outcome_scorer` stores a `per_question` list per session sample.
    Baseline and scaffold assign the SAME question to each (session, position)
    (verified: identical `correct_answers`), so this key pairs across conditions
    just like a single-turn sample id. Same {id: outcome} shape as _load_outcomes,
    so pair_outcomes/build_matrix work unchanged (infra_error/unknown excluded there)."""
    from inspect_ai.log import read_eval_log
    log = read_eval_log(str(path))
    out: dict[str, str] = {}
    for s in (log.samples or []):
        sc = (s.scores or {}).get(scorer_name)
        if not sc:
            continue
        for i, o in enumerate((sc.metadata or {}).get("per_question") or []):
            out[f"s{s.id}:q{i}"] = str(o)
    return out


def _wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson 95% CI for a proportion k/n (stdlib only; robust at small n / 0s)."""
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    center = (p + z * z / (2 * n)) / d
    half = (z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d
    return (max(0.0, center - half), min(1.0, center + half))


def _bh_qvalues(pvals: list[float]) -> list[float]:
    """Benjamini-Hochberg FDR-adjusted p-values, returned in the input order."""
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    q = [0.0] * m
    prev = 1.0
    for rank, i in enumerate(reversed(order), start=1):  # largest p first
        k = m - rank + 1
        prev = min(prev, pvals[i] * m / k)
        q[i] = prev
    return q


class _Collision(Exception):
    """Raised when batches being merged share ids (not a disjoint append)."""


def _merge(loader, paths, *loader_args) -> dict:
    """Merge {id: value} across DISJOINT batches (raises on overlap)."""
    out: dict = {}
    for p in paths:
        d = loader(Path(p), *loader_args)
        dup = set(d) & set(out)
        if dup:
            raise _Collision(f"{sorted(dup)[:5]}...")
        out.update(d)
    return out


def _merge_cell(paths, log_dirs, loader, *loader_args):
    """Merge a cell's batches across dirs with id priority = NEWEST dir first.

    A batch contributes only ids not already present, so the two cases compose
    correctly in one pass:
      - **Replicate** (same ids in multiple dirs, e.g. an agentic cell re-run in
        v2 without --offset): the newest dir's values win; older duplicates drop.
      - **Disjoint offset-append** (discovery ids 1-40 + extension ids 41-140):
        the ranges UNION into the pooled cell.
    Returns (merged, superseded_dir_or_None); superseded names an older dir whose
    ids were dropped as replicates (informational, for the reporting note)."""
    merged: dict = {}
    superseded = None
    for d in reversed(log_dirs):  # newest --log-dirs entry first
        for p in [q for q in paths if f"{d}/" in q]:
            dd = loader(Path(p), *loader_args)
            new = {k: v for k, v in dd.items() if k not in merged}
            if len(new) < len(dd):  # some ids already present from a newer dir
                superseded = d
            merged.update(new)
    return merged, superseded


def _believers(paths) -> int | None:
    """# scaffold-condition believers, trying single-turn then agentic scorer."""
    for scorer in ("single_response_scorer", "agentic_state_scorer"):
        merged = {}
        ok = False
        for p in paths:
            d = _load_beliefs(Path(p), scorer)
            if d:
                ok = True
            merged.update(d)
        if ok:
            return sum(1 for v in merged.values() if v == "believes")
    return None


def compute_rows(log_dirs, baseline_condition="baseline", scorer_default="outcome_scorer"):
    """Compute every (model, arm, condition) McNemar cell + BH-FDR q over the
    primary (L2-L4) family. Returns rows (dicts) — reused by the CLI and figures.py."""
    from inspect_ai.log import read_eval_log

    # Discover (model, arm, condition) -> [paths]. ARM must be in the key (same
    # condition name spans arms with overlapping ids; comparisons are within-arm).
    cells: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for d in log_dirs:
        for f in sorted(glob.glob(f"{d}/*.eval")):
            h = read_eval_log(f, header_only=True)
            if h.status != "success":
                continue
            model = h.eval.model.split("/")[-1]
            arm = (h.eval.task or "?").split("/")[-1]
            cond = (h.eval.task_args or {}).get("condition", "?")
            cells[(model, arm, cond)].append(f)
    if not cells:
        return []

    groups = sorted({(m, a) for (m, a, _c) in cells})
    rows = []
    for m, arm in groups:
        seq = "sequential" in arm
        loader = _load_sequential_outcomes if seq else _load_outcomes  # per-question vs per-sample
        scorer = "sequential_outcome_scorer" if seq else scorer_default
        base = cells.get((m, arm, baseline_condition))
        if not base:
            rows.append({"model": m, "arm": arm, "cond": "(no baseline — skipped)"})
            continue
        baseline, brep = _merge_cell(base, log_dirs, loader, scorer)
        if brep:
            rows.append({"model": m, "arm": arm, "note": f"baseline: replicate ids in {brep} superseded by newer dir"})
        conds = [c for (mm, aa, c) in cells
                 if mm == m and aa == arm and c != baseline_condition]
        conds.sort(key=lambda c: _ORDER.index(c) if c in _ORDER else 99)
        for c in conds:
            scaf, _srep = _merge_cell(cells[(m, arm, c)], log_dirs, loader, scorer)
            pairs, _diag = pair_outcomes(baseline, scaf)
            M = build_matrix(pairs)
            cw, wc = M[("correct", "wrong")], M[("wrong", "correct")]
            p = degradation_channel(M)["narrow"]["p_value"]
            n = len(pairs)
            rows.append({"model": m, "arm": arm, "cond": c, "n": n, "cw": cw, "wc": wc,
                         "p": p, "rate": cw / n if n else 0.0, "ci": _wilson_ci(cw, n),
                         "blv": _believers(cells[(m, arm, c)]),
                         "primary": any(t in c for t in ("level2", "level3", "level4"))})

    prim = [r for r in rows if r.get("primary")]
    for r, q in zip(prim, _bh_qvalues([r["p"] for r in prim])):
        r["q"] = q
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run all paired comparisons across log dirs.")
    ap.add_argument("--log-dirs", nargs="+", default=["logs/main-v1", "logs/main-v2"])
    ap.add_argument("--baseline-condition", default="baseline")
    ap.add_argument("--scorer", default="outcome_scorer")
    args = ap.parse_args(argv)

    rows = compute_rows(args.log_dirs, args.baseline_condition, args.scorer)
    if not rows:
        print("[error] no successful logs found in", args.log_dirs, file=sys.stderr)
        sys.exit(1)

    # ---- pass 2: print --------------------------------------------------------
    print(f"\n{'='*112}")
    print("  PAIRED McNEMAR — exact-binomial; BH-FDR over PRIMARY family (L2-L4); Wilson 95% CI on C→W rate")
    print(f"  dirs: {args.log_dirs}")
    print(f"{'='*112}")
    print(f"  {'model':<22}{'arm':<16}{'condition':<28}{'n':>4}{'C→W':>5}{'W→C':>5}"
          f"{'rate[95%CI]':>18}{'p':>8}{'q':>8}  verdict")
    print(f"  {'-'*108}")
    last = None
    for r in rows:
        if "cond" in r and "n" not in r:  # skipped-baseline marker
            print(f"  {r['model']:<22}{r['arm']:<16}{r['cond']}")
            continue
        if "note" in r:
            print(f"  [warn] {r['model']}/{r['arm']}: {r['note']}")
            continue
        if last is not None and (r["model"], r["arm"]) != last:
            print()
        last = (r["model"], r["arm"])
        lo, hi = r["ci"]
        ci = f"{r['rate']:.2f}[{lo:.2f},{hi:.2f}]"
        q = r.get("q")
        q_s = "-" if q is None else f"{q:.3f}"
        star = "**" if (r["p"] < 0.05 and r["cw"] > r["wc"]) else ""
        fdr = " (q<.05)" if (q is not None and q < 0.05 and r["cw"] > r["wc"]) else ""
        verdict = (f"EH{star}{fdr}" if star else ("(dir)" if r["cw"] > r["wc"] else "ns"))
        print(f"  {r['model']:<22}{r['arm']:<16}{r['cond']:<28}{r['n']:>4}{r['cw']:>5}{r['wc']:>5}"
              f"{ci:>18}{r['p']:>8.3f}{q_s:>8}  {verdict}")

    print("\n  rate = C→W proportion (EH magnitude). p = exact McNemar; q = BH-FDR over the "
          "L2-L4 primary family.\n  verdict: EH** = raw p<.05; (q<.05) survives FDR; L5/L6 are "
          "expected-positive controls (not in FDR family).")


if __name__ == "__main__":
    main()
