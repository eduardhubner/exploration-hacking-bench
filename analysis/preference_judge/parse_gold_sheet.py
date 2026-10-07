"""Parse a filled preference gold sheet back into gold_<judge>.json (tolerant of label
formatting), mirroring analysis/parse_gold_sheet.py. Merges labels onto the existing
template (which holds the per-id metadata), validates label values against the FROZEN
label sets in parsers.py, and reports coverage.

    python analysis/preference_judge/parse_gold_sheet.py --judge mechanism \\
        --sheet data/preference/judge_calibration/label_sheet_mechanism.md \\
        --template data/preference/judge_calibration/gold_mechanism.json \\
        --out data/preference/judge_calibration/gold_mechanism.json
"""
from __future__ import annotations
import argparse, json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from parsers import MECHANISM_FIELDS, SEMANTICS_FIELD, SEMANTICS_VALUES

PLACEHOLDERS = {"", "_", "__", "___", "____", "_____", "______", "pending", "n/a", "na", "tbd"}
LABELSETS = {**MECHANISM_FIELDS, SEMANTICS_FIELD: SEMANTICS_VALUES}
AUX = {"gold_status": {"unanimous", "adjudicated", "unresolved"},
       "confidence": {"high", "med", "low"}}
FREE = {"evidence", "notes", "intended_rationale"}


def clean(v):
    if v is None:
        return None
    v = v.strip().strip("`'\"").strip()
    if v.startswith("[") and v.endswith("]"):
        v = v[1:-1].strip()
    return None if v.lower() in PLACEHOLDERS else v


def field(line, name):
    # Leading "- " bullet is OPTIONAL: annotators labeled some fields dashless
    # (e.g. "intended_task_interpretation: alternative_plausible"), replacing the
    # template's "- field: ____" placeholder line.
    m = re.match(rf"\s*-?\s*{re.escape(name)}\s*:\s*(.*)$", line)
    return clean(m.group(1)) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge", choices=["mechanism", "semantics"], required=True)
    ap.add_argument("--sheet", type=Path, required=True)
    ap.add_argument("--template", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()

    label_fields = ([f for f in MECHANISM_FIELDS] if args.judge == "mechanism"
                    else [SEMANTICS_FIELD])
    all_fields = label_fields + list(AUX) + list(FREE)
    gold = json.loads(args.template.read_text())

    cur, blocks, in_fence = None, {}, False
    for line in args.sheet.read_text().splitlines():
        if line.lstrip().startswith("```"):        # reasoning traces are fenced;
            in_fence = not in_fence                 # never read fields from inside them
            continue
        if in_fence:
            continue
        h = re.match(r"###\s*`?([AB]\d{3})`?", line)
        if h:
            cur = h.group(1); blocks.setdefault(cur, {})
            continue
        if cur is None:
            continue
        for f in all_fields:
            v = field(line, f)
            if v is not None:                       # last non-placeholder value wins
                blocks[cur][f] = v

    labeled = invalid = unresolved = 0
    warnings = []
    for iid, vals in blocks.items():
        if iid not in gold:
            warnings.append(f"{iid}: id not in template (skipped)"); continue
        for f, v in vals.items():
            if f in LABELSETS and v not in LABELSETS[f]:
                warnings.append(f"{iid}.{f}: invalid value {v!r}"); invalid += 1; continue
            if f in AUX and v not in AUX[f]:
                warnings.append(f"{iid}.{f}: invalid aux {v!r}"); continue
            gold[iid][f] = v
        prim = label_fields[0]
        if gold[iid].get(prim):
            labeled += 1
        if gold[iid].get("gold_status") == "unresolved":
            unresolved += 1

    args.out.write_text(json.dumps(gold, indent=2))
    print(f"parsed {len(blocks)} blocks; primary-labeled={labeled}/{len(gold)}; "
          f"unresolved={unresolved}; invalid={invalid}")
    for w in warnings:
        print("  WARN", w)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
