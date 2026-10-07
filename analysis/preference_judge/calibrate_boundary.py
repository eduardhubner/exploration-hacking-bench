"""Tier 1 — boundary/ontology unit tests for the preference judges.

Runs the hand-crafted boundary suites (boundary_{mechanism,semantics}.jsonl), each
case pinning ONE construct boundary with a label certain by construction, through a
frozen judge and reports disagreements. Target ~100%; a miss = prompt/schema
problem, NOT a judge-quality signal. Only the fields a case lists under "expected"
are checked, and only fields still in the current schema (training_target, dropped,
is ignored even if present in a case's expected block). Run BEFORE the dev bake-off.

    python analysis/preference_judge/calibrate_boundary.py --judge mechanism \\
        --model openai/anthropic/claude-haiku-4.5 [--version v2] \\
        [--reasoning-effort medium] [--concurrency 5]
"""
from __future__ import annotations

import argparse
import asyncio
import json
from collections import defaultdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from judge_runner import run_one, judge_fields  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
CAL = ROOT / "data/preference/judge_calibration"


async def _run(judge, model_id, version, reasoning_effort, concurrency, temperature):
    from inspect_ai.model import get_model

    cases = [json.loads(l) for l in (CAL / f"boundary_{judge}.jsonl").read_text().splitlines() if l.strip()]
    fields = judge_fields(judge)                       # current schema only
    model = get_model(model_id)
    sem = asyncio.Semaphore(concurrency)

    async def one(case):
        rec = dict(case, _version=version)
        async with sem:
            for attempt in range(3):
                try:
                    return case, await run_one(model, judge, rec,
                                               reasoning_effort=reasoning_effort, temperature=temperature)
                except Exception as e:  # noqa: BLE001
                    if attempt == 2:
                        print(f"  [warn] {case['id']}: judge failed ({type(e).__name__}: {e}) — skipped")
                        return case, None
                    await asyncio.sleep(2 * (attempt + 1))

    results = [(c, r) for c, r in await asyncio.gather(*(one(c) for c in cases)) if r is not None]

    print(f"\n{'='*84}\n  BOUNDARY CALIBRATION — {judge} — {model_id} — {len(cases)} cases (frozen {version})"
          f"\n  (ontology unit tests: labels certain by construction; target ~100%.)\n{'='*84}")

    pairs = defaultdict(list)   # field -> [(want, got)]
    n_pass = n_parsefail = 0
    for case, res in results:
        exp = case["expected"]
        mism = []
        for f in fields:                               # ignore expected keys not in schema
            if f not in exp or exp[f] is None:
                continue
            want, got = exp[f], res["labels"].get(f)
            pairs[f].append((want, got))
            if got != want:
                mism.append(f"{f}: want {want} got {got if got is not None else '·('+res['status'][f]+')'}")
        if not res["ok"]:
            n_parsefail += 1
        n_pass += not mism
        status = "PASS" if not mism else "FAIL"
        note = case.get("note", case.get("boundary", ""))
        print(f"\n  [{status}] {case['id']}  — {note}")
        for m in mism:
            print(f"        ✗ {m}")

    print(f"\n{'-'*84}\n  Cases fully correct: {n_pass}/{len(results)}   parse-fail: {n_parsefail}\n")
    print("  Per-field accuracy:")
    for f in fields:
        ps = pairs[f]
        if not ps:
            continue
        acc = sum(1 for w, g in ps if w == g) / len(ps)
        print(f"    {f:<26} {sum(1 for w,g in ps if w==g)}/{len(ps)}  ({acc:.0%})")
        # confusion for any field with a miss
        if any(w != g for w, g in ps):
            conf = defaultdict(int)
            for w, g in ps:
                conf[(w, g)] += 1
            for (w, g), n in sorted(conf.items()):
                if w != g:
                    print(f"        gold={w!r} -> pred={g!r}: {n}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge", choices=["mechanism", "semantics"], required=True)
    ap.add_argument("--model", required=True, help="judge model id (openai/... via OpenRouter)")
    ap.add_argument("--version", default="v2")
    ap.add_argument("--reasoning-effort", default=None, choices=["low", "medium", "high"])
    ap.add_argument("--temperature", type=float, default=None)
    ap.add_argument("--concurrency", type=int, default=5)
    args = ap.parse_args(argv)
    asyncio.run(_run(args.judge, args.model, args.version, args.reasoning_effort,
                     args.concurrency, args.temperature))


if __name__ == "__main__":
    main()
