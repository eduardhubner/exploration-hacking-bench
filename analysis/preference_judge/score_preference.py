"""Production reasoning-judge scoring for the preference arm.

Runs the FROZEN calibrated judges (Judge A mechanism, Judge B semantics) over the
preference episodes and writes per-episode labels. Uses the same frozen config that
passed calibration (see CALIBRATION_SUMMARY.md): GPT-5.6-Sol @ reasoning_effort=medium,
frozen v3.

Episode source: the interleaved block log (baseline/c0/level2-5/shadow) + the separate
l6 log, per (axis, model). Records are built exactly as the dev sampler builds them.

Scope defaults follow the judge design:
  - Judge A (mechanism): the scenario-bearing conditions (c0, level2-5, shadow, level6);
    baseline has no discovered scenario and is excluded by default.
  - Judge B (semantics): truthfulness axis, conditions {baseline, c0} (construct-validity
    check on the object items); extend with flags for a power robustness sample or L4.

Output: <out-dir>/<judge>/<axis>__<model>.jsonl, one line per episode:
  {id, axis, model, condition, base_uid, epoch, direction, outcome_class, gold,
   model_answer, labels:{...}, status:{...}, reasoning:{field: judge span}}
RESUMABLE: an id already present in the target file is skipped, so re-running continues.
Semantics episodes with no readable <reasoning> (e.g. encrypted traces) are recorded
with labels=null and status="no_reasoning" rather than sent to the judge.

Examples
--------
    # See the plan + episode counts WITHOUT calling the judge:
    python analysis/preference_judge/score_preference.py --judge both --dry-run

    # Judge A over all models/axes, Judge B over its default scope:
    python analysis/preference_judge/score_preference.py --judge both \\
        --reasoning-effort medium --concurrency 8

    # Just one cell, capped, for a smoke test:
    python analysis/preference_judge/score_preference.py --judge mechanism \\
        --models sonnet4 --axes truthfulness --limit-per-cell 3
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from judge_runner import run_one, judge_fields  # noqa: E402
from parsers import extract_reasoning  # noqa: E402
from ehbench.preference_axes import AXES  # noqa: E402
try:
    from ehbench.parsing import extract_tag_content
except Exception:  # noqa: BLE001
    def extract_tag_content(t, tag):
        m = re.findall(rf"<{tag}\s*>(.*?)</{tag}\s*>", t or "", re.S | re.I)
        return m[-1].strip() if m else ""

ROOT = Path(__file__).resolve().parents[2]
LOGS = ROOT / "logs"
MODEL_ID = "openai/openai/gpt-5.6-sol"
ALL_MODELS = ["gemini31", "gemini25", "glm", "gptsol", "kimi", "opus41", "sonnet4"]
A_CONDS = ["c0", "level2", "level3", "level4", "level5", "shadow", "level6"]
B_CONDS = ["baseline", "c0"]


def _block_dir(axis, m):
    if axis == "truthfulness":
        return LOGS / ("pref-block-gemini" if m == "gemini31" else f"pref-block-truthfulness-{m}")
    return LOGS / ("pref-block-power-gemini" if m == "gemini31" else f"pref-block-power-{m}")


def _l6_dir(axis, m):
    if axis == "truthfulness":
        return LOGS / ("pref-l6-gemini" if m == "gemini31" else f"pref-l6-truthfulness-{m}")
    return LOGS / ("pref-l6-power-gemini" if m == "gemini31" else f"pref-l6-power-{m}")


def _read_latest(d: Path):
    from inspect_ai.log import read_eval_log
    fs = sorted(d.glob("*.eval"))
    return read_eval_log(str(fs[-1])) if fs else None


def _records(axis, model):
    """All episodes for (axis, model) from block + l6 logs, as judge-ready dicts."""
    ax = AXES[axis]
    out = []
    for d in (_block_dir(axis, model), _l6_dir(axis, model)):
        if not d.exists():
            continue
        lg = _read_latest(d)
        if lg is None:
            continue
        for s in (lg.samples or []):
            if not s.scores:
                continue
            md = s.metadata or {}
            cond = md.get("eh_condition")
            sc = list(s.scores.values())[0]
            oc = (sc.metadata or {}).get("outcome_class")
            sys_msg = next((m.text if hasattr(m, "text") else str(getattr(m, "content", ""))
                            for m in (s.messages or []) if getattr(m, "role", "") == "system"), "")
            resp = (s.output.completion if getattr(s, "output", None) else "") or ""
            base = str(md.get("base_uid") or str(s.id).split("::")[0])
            ep = getattr(s, "epoch", 1)
            out.append(dict(
                id=f"{axis}:{model}:{cond}:{base}:{ep}",
                axis=axis, model=model, condition=cond, base_uid=base, epoch=ep,
                direction=md.get("direction"), outcome_class=oc, gold=str(s.target),
                model_answer=extract_tag_content(resp, "answer"),
                x_label=ax.x_label, y_label=ax.y_label,
                system_prompt_used=sys_msg, question=str(s.input),
                response=resp, reasoning_text=extract_reasoning(resp),
                intended_answer=str(s.target),
            ))
    return out


def _span(raw, field):
    m = re.findall(rf"<{field}_reasoning\s*>(.*?)</{field}_reasoning\s*>", raw or "", re.S | re.I)
    return (m[-1].strip()[:600]) if m else ""


def _cap_epochs(recs, n):
    """Keep at most n epochs per (condition, base_uid), choosing the lowest epoch
    numbers (deterministic/reproducible). n=None keeps all epochs."""
    if not n:
        return recs
    from collections import defaultdict
    seen = defaultdict(list)
    for r in recs:  # record which epochs to keep per (condition, item)
        seen[(r["condition"], r["base_uid"])].append(r["epoch"])
    keep = {k: set(sorted(set(v))[:n]) for k, v in seen.items()}
    return [r for r in recs if r["epoch"] in keep[(r["condition"], r["base_uid"])]]


def _select(judge, axis, model, conds, epochs_per_item, limit):
    """Records for one cell after condition filter, reasoning filter (semantics),
    epoch cap, then optional per-condition count cap."""
    from collections import Counter
    recs = [r for r in _records(axis, model) if r["condition"] in conds]
    if judge == "semantics":
        recs = [r for r in recs if r["reasoning_text"].strip()]
    recs = _cap_epochs(recs, epochs_per_item)
    if limit:
        by = Counter(); capped = []
        for r in recs:
            if by[r["condition"]] < limit:
                by[r["condition"]] += 1; capped.append(r)
        recs = capped
    return recs


def _plan(judge, models, axes, conds, epochs_per_item, limit):
    from collections import Counter
    total = Counter()
    rows = []
    for axis in axes:
        for m in models:
            recs = _select(judge, axis, m, conds, epochs_per_item, limit)
            rows.append((axis, m, len(recs)))
            total[axis] += len(recs)
    return rows, total


async def _score_cell(model_obj, judge, axis, model, conds, epochs_per_item, limit,
                      effort, temperature, concurrency, out_dir):
    recs = _select(judge, axis, model, conds, epochs_per_item, limit)
    if not recs:
        return 0, 0, 0

    out_path = out_dir / judge / f"{axis}__{model}.jsonl"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done = set()
    if out_path.exists():
        for line in out_path.read_text().splitlines():
            if line.strip():
                try:
                    done.add(json.loads(line)["id"])
                except Exception:  # noqa: BLE001
                    pass
    todo = [r for r in recs if r["id"] not in done]
    n_skip_rz = 0
    fields = judge_fields(judge)
    sem = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()
    n_ok = 0

    def base_row(r):
        return {k: r[k] for k in ("id", "axis", "model", "condition", "base_uid", "epoch",
                                  "direction", "outcome_class", "gold", "model_answer")}

    async def one(r):
        nonlocal n_ok, n_skip_rz
        if judge == "semantics" and not r["reasoning_text"].strip():
            row = base_row(r) | {"labels": None, "status": "no_reasoning", "reasoning": {}}
            async with lock:
                with out_path.open("a") as f:
                    f.write(json.dumps(row) + "\n")
            n_skip_rz += 1
            return
        rec = dict(r, _version="v3")
        async with sem:
            for attempt in range(3):
                try:
                    res = await run_one(model_obj, judge, rec, reasoning_effort=effort, temperature=temperature)
                    break
                except Exception as e:  # noqa: BLE001
                    if attempt == 2:
                        row = base_row(r) | {"labels": None, "status": f"error:{type(e).__name__}", "reasoning": {}}
                        async with lock:
                            with out_path.open("a") as f:
                                f.write(json.dumps(row) + "\n")
                        return
                    await asyncio.sleep(2 * (attempt + 1))
        row = base_row(r) | {"labels": res["labels"],
                             "status": {k: res["status"][k] for k in fields},
                             "reasoning": {k: _span(res["raw"], k) for k in fields}}
        async with lock:
            with out_path.open("a") as f:
                f.write(json.dumps(row) + "\n")
        n_ok += 1

    await asyncio.gather(*(one(r) for r in todo))
    return len(todo), n_ok, n_skip_rz


async def _run(args):
    from inspect_ai.model import get_model
    judges = ["mechanism", "semantics"] if args.judge == "both" else [args.judge]
    models = args.models or ALL_MODELS
    out_dir = Path(args.out_dir)

    for judge in judges:
        axes = args.axes or (["truthfulness", "power"] if judge == "mechanism" else ["truthfulness"])
        conds = args.conditions or (A_CONDS if judge == "mechanism" else B_CONDS)
        rows, total = _plan(judge, models, axes, conds, args.epochs_per_item, args.limit_per_cell)
        epi = f"epochs/item={args.epochs_per_item or 'all'}"
        print(f"\n{'='*76}\n  {judge.upper()} plan — conditions={conds} — {epi} — model={args.model_id}")
        for axis, m, n in rows:
            print(f"    {axis:12} {m:9} {n:6d} episodes")
        print(f"  TOTAL {judge}: {sum(total.values())} episodes  {dict(total)}")
        if args.dry_run:
            continue
        model_obj = get_model(args.model_id)
        gtodo = gok = gskip = 0
        for axis in axes:
            for m in models:
                todo, ok, skip = await _score_cell(model_obj, judge, axis, m, conds,
                                                   args.epochs_per_item, args.limit_per_cell,
                                                   args.reasoning_effort, args.temperature,
                                                   args.concurrency, out_dir)
                gtodo += todo; gok += ok; gskip += skip
                if todo:
                    print(f"    [{judge}] {axis:12} {m:9} judged={ok} no_reasoning={skip} (of {todo} new)")
        print(f"  DONE {judge}: judged={gok} no_reasoning={gskip} (new this run={gtodo}) -> {out_dir/judge}")
    if args.dry_run:
        print("\n(dry run — no judge calls made)")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge", choices=["mechanism", "semantics", "both"], default="both")
    ap.add_argument("--models", nargs="+", default=None, help=f"subset of {ALL_MODELS}")
    ap.add_argument("--axes", nargs="+", default=None, choices=["truthfulness", "power"])
    ap.add_argument("--conditions", nargs="+", default=None)
    ap.add_argument("--model-id", default=MODEL_ID)
    ap.add_argument("--version", default="v3")  # frozen config version (unused flag placeholder; run_one reads _version)
    ap.add_argument("--reasoning-effort", default="medium", choices=["low", "medium", "high"])
    ap.add_argument("--temperature", type=float, default=None)
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--epochs-per-item", type=int, default=None,
                    help="keep at most N epochs per (condition,item), lowest epoch numbers "
                         "(the item is the statistical unit; epochs are replicates). Default: all.")
    ap.add_argument("--limit-per-cell", type=int, default=None,
                    help="cap episodes per (axis,model,condition) — for smoke tests / cheap first pass")
    ap.add_argument("--out-dir", default="data/preference/judge_labels")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
