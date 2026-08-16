"""Boundary-case calibration for the five-pass EH judge.

Runs a small set of hand-crafted transcripts (analysis/calibration_cases.json),
each designed to stress ONE construct boundary with an unambiguous intended
label, through the production judge and reports where the judge disagrees.

These are **ontology unit tests, not a judge-performance estimate.** Labels are
certain by construction, so ~100% is the target; a miss means a prompt/schema
problem. Passing tells you the definitions are internally expressible — it does
NOT predict accuracy on natural transcripts (that is the gold dev/held-out sets;
see docs/GOLD_ANNOTATION_GUIDE.md "Three validation tiers"). Run this BEFORE the
full bake-off.

Reports: binary dims with positive- and negative-recall (so a 0-dominated field
can't hide a failure), a 3-way belief confusion matrix, and provenance accuracy
CONDITIONAL on the corresponding gold dimension = 1.

Usage
-----
    python analysis/calibrate_judges.py --judge openai/anthropic/claude-haiku-4.5
    python analysis/calibrate_judges.py --judge ... --cases analysis/calibration_cases.json

Only the fields a case lists under "expected" are checked (a case pins the
boundary it targets; other fields are left unasserted).
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

_DEFAULT_CASES = Path(__file__).parent / "calibration_cases.json"


def _fmt(v) -> str:
    return "·" if v is None else str(v)


async def _score_case(judge_model: str, scaffolds: dict, case: dict, reasoning_effort, temperature):
    from ehbench.scorers.markov_scorer import _run_holistic_judge

    system_prompt = scaffolds.get(case["scaffold"], case["scaffold"])
    correct = str(case["correct_answer"]).strip().upper()
    # crude model-answer extraction for the action pass context
    resp = case["response"]
    ans = ""
    if "<answer>" in resp and "</answer>" in resp:
        ans = resp.split("<answer>")[1].split("</answer>")[0].strip().upper()
    return await _run_holistic_judge(
        judge_model=judge_model,
        system_prompt_used=system_prompt,
        question=case["question"],
        correct_answer=correct,
        model_answer=ans or "(none)",
        is_correct=(ans == correct),
        response=resp,
        reasoning_effort=reasoning_effort,
        temperature=temperature,
    )


async def _run(judge_model: str, cases_path: Path, reasoning_effort, concurrency: int, temperature=None):
    data = json.loads(cases_path.read_text())
    scaffolds = data.get("_scaffolds", {})
    cases = data["cases"]

    sem = asyncio.Semaphore(concurrency)

    async def one(case):
        async with sem:
            # Tolerate transient provider errors (e.g. a non-JSON 5xx body) with a
            # couple of retries; a single flaky call must not sink the whole run.
            for attempt in range(3):
                try:
                    return case, await _score_case(judge_model, scaffolds, case, reasoning_effort, temperature)
                except Exception as e:  # noqa: BLE001 — provider/transport errors vary
                    if attempt == 2:
                        print(f"  [warn] {case['id']}: judge call failed after retries "
                              f"({type(e).__name__}: {e}) — case skipped")
                        return case, None
                    await asyncio.sleep(2 * (attempt + 1))

    results = [(c, s) for c, s in await asyncio.gather(*(one(c) for c in cases)) if s is not None]
    if len(results) < len(cases):
        print(f"  [warn] {len(cases) - len(results)} case(s) skipped due to judge errors "
              f"— tallies below are over the {len(results)} that returned.\n")

    BIN = ["dim1", "dim2", "dim3", "dim4", "premise_rejection_gate", "decoupling_gate"]
    PROV = ["goal_conflict_source", "planning_source", "action_rationale_source"]
    BELIEF = ["believes", "disbelieves", "unstated"]

    belief_pairs: list[tuple] = []                       # (gold, pred)
    bin_pairs: dict[str, list[tuple]] = {k: [] for k in BIN}
    prov_pairs: dict[str, list[tuple]] = {k: [] for k in PROV}  # conditional: gold != none only

    n_case_pass = 0
    print(f"\n{'='*84}\n  JUDGE CALIBRATION — {judge_model} — {len(cases)} boundary cases"
          f"\n  (ontology unit tests: labels certain by construction; target ~100%. "
          f"A miss = prompt/schema problem, not a model-quality signal.)\n{'='*84}")
    n_prov_mism = 0
    for case, got in results:
        exp = case["expected"]
        core_mism, prov_mism = [], []  # provenance is measured but does NOT gate PASS/FAIL
        for k, want in exp.items():
            if want is None:
                continue
            have = got.get(k)
            mismatch = have != want
            if k == "belief_gate":
                belief_pairs.append((want, have))
                if mismatch:
                    core_mism.append(f"{k}: want {_fmt(want)} got {_fmt(have)}")
            elif k in BIN:
                bin_pairs[k].append((want, have))
                if mismatch:
                    core_mism.append(f"{k}: want {_fmt(want)} got {_fmt(have)}")
            elif k in PROV and want != "none":  # provenance only meaningful when dim gold=1
                prov_pairs[k].append((want, have))
                if mismatch:
                    prov_mism.append(f"{k}: want {_fmt(want)} got {_fmt(have)}")
        # Gate on the 7 SELECTED constructs only; provenance is fuzzy at the
        # ceiling (self/scaffold/mixed) and reported separately, not gated.
        status = "PASS" if not core_mism else "FAIL"
        n_case_pass += not core_mism
        n_prov_mism += bool(prov_mism)
        flag = "" if not prov_mism else "  (prov✗)"
        print(f"\n  [{status}] {case['id']}  — {case['boundary']}{flag}")
        for m in core_mism:
            print(f"        ✗ {m}")
        for m in prov_mism:
            print(f"        ~ (provenance, not gated) {m}")

    def _rate(pairs, gold_val, pred_ok):
        sub = [(g, p) for g, p in pairs if g == gold_val]
        if not sub:
            return None
        return sum(1 for g, p in sub if pred_ok(p)) / len(sub)

    print(f"\n{'-'*84}\n  Cases correct on the 7 GATED constructs: {n_case_pass}/{len(results)}"
          f"   (provenance not gated: {n_prov_mism} case(s) had a provenance-only mismatch)\n")

    print("  Binary dimensions — accuracy | positive-recall | negative-recall (specificity):")
    for k in BIN:
        pairs = bin_pairs[k]
        if not pairs:
            continue
        acc = sum(1 for g, p in pairs if g == p) / len(pairs)
        pr = _rate(pairs, 1, lambda p: p == 1)   # recall of the 1s
        nr = _rate(pairs, 0, lambda p: p == 0)   # specificity on the 0s
        pr_s = "n/a" if pr is None else f"{pr:.0%}"
        nr_s = "n/a" if nr is None else f"{nr:.0%}"
        print(f"    {k:<24} acc={acc:.0%}  pos-recall={pr_s}  neg-recall={nr_s}  (n={len(pairs)})")

    if belief_pairs:
        print("\n  belief_gate — 3-way confusion (rows=gold, cols=pred):")
        print("    " + " " * 12 + "".join(f"{c:>12}" for c in BELIEF))
        for g in BELIEF:
            row = [sum(1 for gg, pp in belief_pairs if gg == g and pp == c) for c in BELIEF]
            print(f"    {g:<12}" + "".join(f"{n:>12}" for n in row))

    print("\n  Provenance — accuracy CONDITIONAL on gold dim=1 (none cases excluded):")
    for k in PROV:
        pairs = prov_pairs[k]
        if not pairs:
            print(f"    {k:<26} (no positive-dim cases)")
            continue
        acc = sum(1 for g, p in pairs if g == p) / len(pairs)
        print(f"    {k:<26} {sum(1 for g, p in pairs if g == p)}/{len(pairs)}  ({acc:.0%})")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Boundary-case calibration for the EH judge.")
    ap.add_argument("--judge", required=True, help="Judge model id (OpenRouter/openai-compat).")
    ap.add_argument("--cases", type=Path, default=_DEFAULT_CASES)
    ap.add_argument("--reasoning-effort", default=None, choices=["low", "medium", "high"])
    ap.add_argument("--temperature", type=float, default=None,
                    help="Sampling temperature (0 = greedy/deterministic for non-reasoning "
                         "judges; reasoning models may ignore it). Default: provider default.")
    ap.add_argument("--concurrency", type=int, default=5)
    args = ap.parse_args(argv)
    asyncio.run(_run(args.judge, args.cases, args.reasoning_effort, args.concurrency, args.temperature))


if __name__ == "__main__":
    main()
