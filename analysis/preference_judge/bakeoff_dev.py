"""Tier 2 — dev bake-off for the preference judges.

Runs one or more candidate judge models over the SAME dev transcripts and reports,
per candidate: parse-fail rate, and per-field agreement vs the human gold labels
(accuracy + confusion matrix). This is the set used to refine the rubric and choose
a judge; it is NOT a clean generalization estimate once its disagreements have been
inspected (see GOLD_ANNOTATION_GUIDE.md, three tiers). Run Tier 1 (boundary) first.

Records join to gold by an explicit "id" field if present, else by the tuple
(axis, model, condition, base_uid, epoch). Only gold ids that BOTH have a matching
record and carry a non-empty primary label are scored (so a partially-labeled gold
set just scores its labeled subset, and the header reports the coverage).

    python analysis/preference_judge/bakeoff_dev.py --judge mechanism \\
        --records data/preference/judge_calibration/dev_mechanism.jsonl \\
        --gold    data/preference/judge_calibration/gold_mechanism.json \\
        --models openai/anthropic/claude-haiku-4.5 openai/openai/gpt-5.6-sol \\
        [--version v2] [--reasoning-effort medium] [--concurrency 5]
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

TUPLE = ("axis", "model", "condition", "base_uid", "epoch")


def _tuple(d):
    return tuple(str(d.get(k)) for k in TUPLE)


def _load_records(path: Path, gold: dict) -> dict:
    """Return {gold_id: record}. Prefer explicit record['id']; else join by tuple."""
    recs = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    by_id = {}
    if all("id" in r for r in recs):
        for r in recs:
            by_id[r["id"]] = r
        return by_id
    tup2id = {_tuple(v): k for k, v in gold.items()}
    for r in recs:
        gid = tup2id.get(_tuple(r))
        if gid:
            by_id[gid] = r
    return by_id


async def _run(judge, records_path, gold_path, models, version, reasoning_effort, concurrency, temperature):
    from inspect_ai.model import get_model

    fields = judge_fields(judge)
    prim = fields[0]
    gold = json.loads(Path(gold_path).read_text())
    recs = _load_records(Path(records_path), gold)

    def labeled(v):
        return bool(v) and str(v).strip() not in {"", "____"}

    scored_ids = [gid for gid, g in gold.items() if labeled(g.get(prim)) and gid in recs]
    missing_rec = [gid for gid, g in gold.items() if labeled(g.get(prim)) and gid not in recs]

    print(f"\n{'#'*84}\n  DEV BAKE-OFF — {judge} — frozen {version}")
    print(f"  gold labeled (primary '{prim}'): {sum(labeled(g.get(prim)) for g in gold.values())}/{len(gold)}"
          f"   |  with matching record: {len(scored_ids)}")
    if missing_rec:
        print(f"  [warn] {len(missing_rec)} labeled gold id(s) have NO matching record (skipped): {missing_rec}")
    if not scored_ids:
        print("  nothing to score — no labeled gold ids have matching records."); return

    for model_id in models:
        model = get_model(model_id)
        sem = asyncio.Semaphore(concurrency)

        async def one(gid):
            rec = dict(recs[gid], _version=version)
            async with sem:
                for attempt in range(3):
                    try:
                        return gid, await run_one(model, judge, rec,
                                                  reasoning_effort=reasoning_effort, temperature=temperature)
                    except Exception as e:  # noqa: BLE001
                        if attempt == 2:
                            print(f"    [warn] {gid}: judge failed ({type(e).__name__}: {e})")
                            return gid, None
                        await asyncio.sleep(2 * (attempt + 1))

        res = dict(await asyncio.gather(*(one(g) for g in scored_ids)))
        n_parsefail = sum(1 for r in res.values() if r is None or not r["ok"])

        print(f"\n{'='*84}\n  JUDGE = {model_id}   (n={len(scored_ids)}, parse-fail={n_parsefail})\n{'='*84}")
        for f in fields:
            pairs = [(gold[g][f], res[g]["labels"].get(f)) for g in scored_ids
                     if res[g] is not None and labeled(gold[g].get(f))]
            if not pairs:
                print(f"  {f:<26} (no gold labels)"); continue
            acc = sum(1 for w, p in pairs if w == p) / len(pairs)
            print(f"  {f:<26} agreement {sum(1 for w,p in pairs if w==p)}/{len(pairs)}  ({acc:.0%})")
            conf = defaultdict(int)
            for w, p in pairs:
                conf[(w, p)] += 1
            labelset = sorted({w for w, _ in pairs} | {p for _, p in pairs if p is not None})
            w_gold = sorted({w for w, _ in pairs})
            print("      confusion (rows=gold, cols=pred):")
            hdr = "".join(f"{str(c)[:10]:>12}" for c in labelset)
            print("        " + " " * 20 + hdr + f"{'None':>12}")
            for w in w_gold:
                row = "".join(f"{conf.get((w,c),0):>12}" for c in labelset)
                print(f"        {w:<20}" + row + f"{conf.get((w,None),0):>12}")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge", choices=["mechanism", "semantics"], required=True)
    ap.add_argument("--records", required=True)
    ap.add_argument("--gold", required=True)
    ap.add_argument("--models", nargs="+", required=True)
    ap.add_argument("--version", default="v2")
    ap.add_argument("--reasoning-effort", default=None, choices=["low", "medium", "high"])
    ap.add_argument("--temperature", type=float, default=None)
    ap.add_argument("--concurrency", type=int, default=5)
    args = ap.parse_args(argv)
    asyncio.run(_run(args.judge, args.records, args.gold, args.models, args.version,
                     args.reasoning_effort, args.concurrency, args.temperature))


if __name__ == "__main__":
    main()
