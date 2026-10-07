"""Scoreable matched pairs per cell, and why any cell is short.

Implements the audit generality_plan.md §9 expects. The unit of n is a MATCHED
PAIR (§2): an item counts only when BOTH the baseline and the scaffolded cell
returned `correct`/`wrong` on that same item id. Target is "at least 100" — a
40-item block that overshoots is kept, never truncated.

Coverage is computed from ITEM ID SETS, never from sample counts: the same id can
appear in two directories (main-v1/main-v2 genuinely overlap on 12 cells) and
counting rows double-counts those. Every number here is derived from a set union.

Usage
-----
    python analysis/pair_report.py                     # audit + top-up commands
    python analysis/pair_report.py --cell cyber agentic gemini-3.1-pro-preview
    python analysis/pair_report.py --all-dirs          # include smoke/legacy dirs
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

DATASET_DOMAIN = {"wmdp-cyber": "cyber", "wmdp-bio": "bio", "wmdp-chem": "chem"}
SCOREABLE = ("correct", "wrong")
TARGET_PAIRS = 100
BLOCK = 40                      # §2: fixed 40-item top-up blocks
EXCLUSION_FLOOR = 50            # §6: below this after top-up -> excluded, report rate

MODEL_PATH = {
    "claude-opus-4": "openai/anthropic/claude-opus-4",
    "claude-sonnet-4": "openai/anthropic/claude-sonnet-4",
    "gemini-2.5-pro": "openai/google/gemini-2.5-pro",
    "gemini-3.1-pro-preview": "openai/google/gemini-3.1-pro-preview",
    "glm-5.2": "openai/z-ai/glm-5.2",
}
LOG_DIR = {"bio": "logs/gen-bio-topup2", "cyber": "logs/gen-cyber-topup2",
           "chem": "logs/gen-chem-topup2"}


def collect_from_index(path=Path("data/episode_index.jsonl")):
    """Same shape as collect(), read from the canonical index (seconds, not minutes).

    The index is the single definition of the dataset (analysis/build_index.py):
    smoke dirs excluded, duplicate episodes resolved by directory precedence and
    flagged `superseded`. Reading it here removes this script's private DATA_DIRS
    list, which is what silently dropped `gen-chem-topup2` for three top-up rounds.
    """
    cells = collections.defaultdict(
        lambda: {"att": set(), "good": set(),
                 "by_dir": collections.defaultdict(set),
                 "causes": collections.Counter()}
    )
    for line in path.read_text().splitlines():
        r = json.loads(line)
        if r["superseded"] or r["arm"] == "sequential":
            continue
        key = (r["domain"], r["arm"], r["model"], r["condition"])
        c = cells[key]
        c["att"].add(r["item_id"])
        c["by_dir"][r["log_dir"]].add(r["item_id"])
        if r["error"]:
            c["causes"]["crash"] += 1
        elif r["scoreable"]:
            c["good"].add(r["item_id"])
        else:
            c["causes"][r["outcome"] or "no-score"] += 1
    return cells


def overlaps(cells):
    """Same id collected twice for one cell, in different dirs — inflates row counts."""
    out = []
    for key, c in cells.items():
        dirs = sorted(c["by_dir"])
        for i in range(len(dirs)):
            for j in range(i + 1, len(dirs)):
                shared = c["by_dir"][dirs[i]] & c["by_dir"][dirs[j]]
                if shared:
                    out.append((key, dirs[i], dirs[j], len(shared)))
    return out


def audit(cells):
    """One row per scaffolded cell: pairs against its baseline, and why it is short."""
    rows = []
    for key, c in sorted(cells.items()):
        domain, arm, model, cond = key
        if cond == "baseline":
            continue
        base = cells.get((domain, arm, model, "baseline"))
        if base is None:
            rows.append(dict(key=key, pairs=None, note="NO BASELINE"))
            continue
        pairs = len(base["good"] & c["good"])
        # Items the baseline could pair on that this cell never ran at all.
        uncovered = len(base["good"] - c["att"])
        cause = c["causes"].most_common(1)
        rows.append(dict(
            key=key, pairs=pairs, att=len(c["att"]), base_good=len(base["good"]),
            uncovered=uncovered, cause=cause[0][0] if cause else "-",
            cause_n=cause[0][1] if cause else 0,
            max_id=max(c["att"] | base["att"]), dirs=sorted(c["by_dir"]),
        ))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description="Scoreable matched pairs per cell (§2).")
    ap.add_argument("--rescan", action="store_true",
                    help="Ignore data/episode_index.jsonl and re-read logs/ directly (slow).")
    ap.add_argument("--cell", nargs=3, metavar=("DOMAIN", "ARM", "MODEL"),
                    help="show per-condition id coverage for one (domain, arm, model)")
    ap.add_argument("--target", type=int, default=TARGET_PAIRS)
    ap.add_argument("--emit", metavar="PATH",
                    help="write the top-up commands to a runnable bash script")
    args = ap.parse_args(argv)

    # Every output dir must also be an input dir: if a top-up target is missing
    # from DATA_DIRS the audit cannot see its results, the cell's max id never
    # advances, and the identical block is re-emitted (and re-billed) every round.
    index = Path("data/episode_index.jsonl")
    if not index.exists():
        print("[error] data/episode_index.jsonl missing — run analysis/build_index.py",
              file=sys.stderr)
        sys.exit(1)
    print(f"reading {index}\n")
    cells = collect_from_index(index)

    if args.cell:
        domain, arm, model = args.cell
        print(f"=== id coverage: {domain} / {arm} / {model} ===")
        for (d, a, m, cond), c in sorted(cells.items()):
            if (d, a, m) != (domain, arm, model):
                continue
            per_dir = "  ".join(f"{dd}:{min(ids)}-{max(ids)}({len(ids)})"
                                for dd, ids in sorted(c["by_dir"].items()))
            base = cells.get((domain, arm, model, "baseline"))
            pairs = len(base["good"] & c["good"]) if base else 0
            print(f"  {cond:28s} att={len(c['att']):3d} good={len(c['good']):3d} "
                  f"pairs={pairs:3d}\n      {per_dir}")
        return

    ov = overlaps(cells)
    if ov:
        print(f"!! {len(ov)} cross-dir id overlaps (same item collected twice for one cell)")
        agg = collections.Counter((o[1], o[2]) for o in ov)
        for (a, b), n in agg.most_common():
            print(f"     {a} x {b}: {n} cells")
        print()

    rows = [r for r in audit(cells) if r.get("pairs") is not None]
    short = [r for r in rows if r["pairs"] < args.target]
    print(f"cells: {len(rows)} | at target (>={args.target} pairs): {len(rows)-len(short)} "
          f"| short: {len(short)}\n")

    print(f"{'domain':6s} {'arm':8s} {'model':24s} {'condition':28s} {'pairs':>5s} "
          f"{'att':>4s} {'uncov':>5s}  dominant-shortfall")
    for r in sorted(short, key=lambda r: (r["key"][0], r["pairs"])):
        d, a, m, c = r["key"]
        floor = "  [<50: §6 EXCLUDE]" if r["pairs"] < EXCLUSION_FLOOR else ""
        print(f"{d:6s} {a:8s} {m:24s} {c:28s} {r['pairs']:5d} {r['att']:4d} "
              f"{r['uncovered']:5d}  {r['cause']}={r['cause_n']}{floor}")

    # ---- §2 top-up commands: one 40-item block per (domain, arm, model) group ----
    if short:
        print("\nTop-ups are complete. If cells reappear here, size a 40-item block"
              "\nper generality_plan.md section 2 and run baseline + the short"
              "\nconditions over the SAME new items.")


if __name__ == "__main__":
    main()
