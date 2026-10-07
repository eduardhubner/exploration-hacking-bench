"""Consolidate the staged judging runs into one cognitive-label artifact.

The cognitive overlay was produced in several passes (initial cyber run, a cyber
extension, a capped cyber re-run split into never-judged + dismissal-only, the
bio/chem run, and the Kimi expansion). This merges them into
`data/cognitive_labels.json` — the single file every cognitive analysis should
read — applying three rules that cannot be recovered from the files alone:

  1. PRECEDENCE. `combined_labels.json` already supersedes `scored_labels.json`
     and `ext_scored_labels.json`, so only `combined` is read. `cyber_labels_new`
     (never-judged cyber, full passes) and `cyber_labels_dismissal`
     (already-judged cyber, dismissal pass re-scored on the NEUTRALIZED prompt)
     are disjoint and together form the capped cyber set.

  2. NEUTRALIZED DISMISSAL OVERLAY. For every already-judged cyber episode, the
     belief/dim1-4 labels come from the original full-pass run (`combined`), but
     `premise_rejection_gate` / `decoupling_gate` are OVERWRITTEN with the
     re-scored values from `cyber_labels_dismissal` (the domain-neutral judge
     prompt), so all domains share one dismissal instrument. Such rows are tagged
     `dismissal_source: neutralized_rejudge`.

  3. BELIEF GATING AT SINGLE-TURN L6. Belief is unidentifiable at
     `level6_explicit_instruction` (single-turn) under the current gating, so
     `belief_gate` is nulled there (see JUDGE_CALIBRATION §7a').

Idempotent and regenerable: rerun after any new judging pass. Source files live in
`backups/labels/`.

    python analysis/merge_labels.py                 # -> data/cognitive_labels.json
    python analysis/merge_labels.py --check         # validate an existing merge
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

LABELS = Path("backups/labels")            # source files (moved here at consolidation)
INDEX = Path("data/episode_index.jsonl")
OUT = Path("data/cognitive_labels.json")

# Neutralized-dismissal fields (the only ones taken from the re-score).
DISMISSAL_FIELDS = ("premise_rejection_gate", "decoupling_gate")


def _real(path: Path) -> dict:
    if not path.exists():
        return {}
    return {k: v for k, v in json.loads(path.read_text()).items() if "_seed" not in v}


def _index() -> dict:
    idx = {}
    for line in INDEX.read_text().splitlines():
        r = json.loads(line)
        if not r["superseded"]:
            idx[r["key"]] = r
    return idx


def build() -> dict:
    combined = _real(LABELS / "combined_labels.json")       # supersedes scored + ext
    cyber_new = _real(LABELS / "cyber_labels_new.json")
    cyber_dis = _real(LABELS / "cyber_labels_dismissal.json")
    biochem = _real(LABELS / "biochem_labels.json")
    kimi = _real(LABELS / "kimi_labels.json")
    idx = _index()

    out: dict = {}
    out.update(cyber_new)                                   # cyber, never judged
    for k in cyber_dis:                                     # cyber, already judged
        base = dict(combined.get(k, {}))
        for f in DISMISSAL_FIELDS:
            base[f] = cyber_dis[k].get(f)
        base["dismissal_source"] = "neutralized_rejudge"
        out[k] = base
    out.update(biochem)                                     # bio + chem
    out.update(kimi)                                        # kimi expansion

    nulled = 0
    for k, v in out.items():
        r = idx.get(k)
        if r and r["arm"] == "single_turn" and "level6" in (r["condition"] or ""):
            if v.get("belief_gate") is not None:
                v["belief_gate"] = None
                nulled += 1
    build.nulled = nulled                                   # for the summary
    return out


def summarise(out: dict) -> None:
    idx = _index()
    resolvable = sum(1 for k in out if k in idx)
    dm = collections.Counter((idx[k]["domain"], idx[k]["arm"]) for k in out if k in idx)
    cells = collections.Counter((idx[k]["domain"], idx[k]["arm"], idx[k]["model"],
                                 idx[k]["condition"]) for k in out if k in idx)
    pf = sum(1 for v in out.values() if v.get("judge_parse_ok") is False)
    neut = sum(1 for v in out.values() if v.get("dismissal_source") == "neutralized_rejudge")
    print(f"episodes: {len(out):,} | resolvable in index: {resolvable:,}")
    print(f"  belief nulled at single-turn L6: {getattr(build, 'nulled', '?')}")
    print(f"  neutralized-dismissal rows: {neut:,}")
    print(f"  parse failures carried through: {pf}")
    print(f"  cells: {len(cells)} | by domain/arm: {dict(sorted(dm.items()))}")
    sizes = sorted(cells.values())
    if sizes:
        print(f"  per-cell n: min {sizes[0]} median {sizes[len(sizes)//2]} max {sizes[-1]}")


def check(out_path: Path) -> None:
    out = json.loads(out_path.read_text())
    cyber_dis = _real(LABELS / "cyber_labels_dismissal.json")
    bad = sum(1 for k in cyber_dis if k in out
              and any(out[k].get(f) != cyber_dis[k].get(f) for f in DISMISSAL_FIELDS))
    idx = _index()
    stale_belief = sum(1 for k, v in out.items() if k in idx
                       and idx[k]["arm"] == "single_turn"
                       and "level6" in (idx[k]["condition"] or "")
                       and v.get("belief_gate") is not None)
    print(f"neutralized dismissal overlaid correctly: {'YES' if bad == 0 else f'NO ({bad})'}")
    print(f"stale single-turn-L6 belief (should be 0): {stale_belief}")
    summarise(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Merge staged judging runs into one label file.")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--check", action="store_true", help="validate an existing merge, do not rebuild")
    args = ap.parse_args(argv)
    if args.check:
        check(args.out)
        return
    out = build()
    args.out.write_text(json.dumps(out))
    print(f"wrote {args.out}")
    summarise(out)


if __name__ == "__main__":
    main()
