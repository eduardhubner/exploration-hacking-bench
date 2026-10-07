"""Merge a dismissal-only re-judge (score_transcripts.py --passes dismissal) into the
production cognitive_labels.json, overwriting ONLY the two dismissal-pass fields
(premise_rejection_gate, decoupling_gate) for the re-judged ids. All other fields
(belief/dim1-4/provenance/parse aggregates) are left untouched.

Why a separate merge: score_transcripts skips ids already in --out, so the re-judge is
written to a FRESH file; this patches its dismissal fields back in. Backs up the target
first. After merging, re-run analysis/cognitive_report.py to refresh cognitive_rows.

    # 1) rescore cyber dismissal to a fresh file:
    python analysis/score_transcripts.py --domains cyber --passes dismissal \
        --out data/cyber_dismissal_rejudge.json
    # 2) merge just the dismissal fields into the production labels:
    python analysis/merge_dismissal_rejudge.py \
        --rejudge data/cyber_dismissal_rejudge.json --into data/cognitive_labels.json
"""
from __future__ import annotations
import argparse, json, shutil, datetime as dt
from pathlib import Path

FIELDS = ["premise_rejection_gate", "decoupling_gate"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rejudge", type=Path, required=True)
    ap.add_argument("--into", type=Path, default=Path("data/cognitive_labels.json"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rejudge = json.loads(args.rejudge.read_text())
    prod = json.loads(args.into.read_text())

    patched = missing = unchanged = 0
    examples = []
    for iid, rec in rejudge.items():
        if iid not in prod:
            missing += 1
            continue
        changed = False
        for f in FIELDS:
            new = rec.get(f)
            if prod[iid].get(f) != new:
                if len(examples) < 5:
                    examples.append(f"{iid[-24:]}  {f}: {prod[iid].get(f)} -> {new}")
                if not args.dry_run:
                    prod[iid][f] = new
                changed = True
        patched += changed
        unchanged += (not changed)

    print(f"rejudge ids={len(rejudge)}  in-prod-patched={patched}  unchanged={unchanged}  "
          f"not-in-prod={missing}")
    for e in examples:
        print("  e.g.", e)
    if args.dry_run:
        print("\n--dry-run: nothing written."); return

    bak = args.into.with_suffix(f".bak-{dt.datetime.now():%Y%m%d-%H%M%S}.json")
    shutil.copyfile(args.into, bak)
    args.into.write_text(json.dumps(prod))
    print(f"\nbacked up -> {bak}\nwrote {args.into}\nNEXT: re-run analysis/cognitive_report.py")


if __name__ == "__main__":
    main()
