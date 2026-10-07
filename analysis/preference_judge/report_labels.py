"""Aggregate the preference-arm judge labels into per-cell construct rates.

Reads data/preference/judge_labels/{mechanism,semantics}/*.jsonl (produced by
score_preference.py with the frozen v3 judges) and emits, per (axis, model,
condition):
  mechanism: rate of scenario_belief=accepted, preservation_intent=yes,
             strategic_action=yes (denominator = episodes where the field parsed);
             plus strategic_action=yes rate among behaviorally-flipped episodes
             (outcome_class=opposite_answer) — the reasoning/behavior concordance.
  semantics: distribution of intended_task_interpretation (expected /
             alternative_plausible / inconsistent_with_item / unclear), skipping
             no_reasoning rows.

Writes data/preference/judge_rows.json and prints a table.

    python analysis/preference_judge/report_labels.py [--print]
"""
from __future__ import annotations
import argparse, glob, json
from collections import defaultdict, Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT / "data/preference/judge_labels"
LADDER = ["baseline", "c0", "level2", "level3", "level4", "level5", "shadow", "level6"]
MECH_TARGET = {"scenario_belief": "accepted", "preservation_intent": "yes", "strategic_action": "yes"}
SEM_VALS = ["expected", "alternative_plausible", "inconsistent_with_item", "unclear"]


def _load(judge):
    rows = []
    for f in glob.glob(str(LAB / judge / "*.jsonl")):
        for l in Path(f).read_text().splitlines():
            if l.strip():
                rows.append(json.loads(l))
    return rows


def mechanism_rows():
    rows = _load("mechanism")
    cells = defaultdict(list)
    for r in rows:
        cells[(r["axis"], r["model"], r["condition"])].append(r)
    out = []
    for (axis, model, cond), rs in sorted(cells.items()):
        row = {"axis": axis, "model": model, "condition": cond, "n": len(rs)}
        for field, target in MECH_TARGET.items():
            ok = [r for r in rs if isinstance(r.get("status"), dict) and r["status"].get(field) == "ok"]
            row[f"{field}_n"] = len(ok)
            row[f"{field}_rate"] = (sum(1 for r in ok if r["labels"].get(field) == target) / len(ok)) if ok else None
        flips = [r for r in rs if r.get("outcome_class") == "opposite_answer"
                 and isinstance(r.get("status"), dict) and r["status"].get("strategic_action") == "ok"]
        row["n_flips"] = len(flips)
        row["strategic_on_flip"] = (sum(1 for r in flips if r["labels"].get("strategic_action") == "yes") / len(flips)) if flips else None
        out.append(row)
    return out


def semantics_rows():
    rows = _load("semantics")
    cells = defaultdict(Counter)
    judged = defaultdict(int); noreason = defaultdict(int)
    for r in rows:
        key = (r["axis"], r["model"], r["condition"])
        if r.get("status") == "no_reasoning" or not isinstance(r.get("labels"), dict):
            noreason[key] += 1; continue
        v = r["labels"].get("intended_task_interpretation")
        if v:
            cells[key][v] += 1; judged[key] += 1
    out = []
    for key in sorted(cells):
        axis, model, cond = key
        row = {"axis": axis, "model": model, "condition": cond,
               "judged": judged[key], "no_reasoning": noreason[key]}
        for v in SEM_VALS:
            row[v] = cells[key][v]
            row[f"{v}_rate"] = cells[key][v] / judged[key] if judged[key] else None
        out.append(row)
    return out


def _fmt(x):
    return "  n/a" if x is None else f"{x:.2f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--print", action="store_true", dest="show")
    args = ap.parse_args()
    mech = mechanism_rows(); sem = semantics_rows()
    (ROOT / "data/preference/judge_rows.json").write_text(
        json.dumps({"mechanism": mech, "semantics": sem}, indent=2))

    print(f"\n{'='*94}\n  MECHANISM — construct rates per cell (rate [n parsed])\n{'='*94}")
    print(f"  {'axis':13}{'model':10}{'cond':9}{'belief=acc':>12}{'preserv=yes':>13}"
          f"{'strateg=yes':>13}{'strat|flip':>12}")
    order = {c: i for i, c in enumerate(LADDER)}
    for r in sorted(mech, key=lambda r: (r["axis"], r["model"], order.get(r["condition"], 99))):
        print(f"  {r['axis'][:12]:13}{r['model'][:9]:10}{r['condition'][:8]:9}"
              f"{_fmt(r['scenario_belief_rate']):>12}{_fmt(r['preservation_intent_rate']):>13}"
              f"{_fmt(r['strategic_action_rate']):>13}{_fmt(r['strategic_on_flip']):>12}")

    print(f"\n{'='*94}\n  SEMANTICS — intended_task_interpretation distribution (rate)\n{'='*94}")
    print(f"  {'axis':13}{'model':10}{'cond':9}{'expected':>10}{'alt_plaus':>11}{'inconsist':>11}{'unclear':>9}{'judged':>8}{'no_rz':>7}")
    for r in sorted(sem, key=lambda r: (r["axis"], r["model"], order.get(r["condition"], 99))):
        print(f"  {r['axis'][:12]:13}{r['model'][:9]:10}{r['condition'][:8]:9}"
              f"{_fmt(r['expected_rate']):>10}{_fmt(r['alternative_plausible_rate']):>11}"
              f"{_fmt(r['inconsistent_with_item_rate']):>11}{_fmt(r['unclear_rate']):>9}"
              f"{r['judged']:>8}{r['no_reasoning']:>7}")
    print(f"\nwrote data/preference/judge_rows.json  ({len(mech)} mechanism cells, {len(sem)} semantics cells)")


if __name__ == "__main__":
    main()
