"""Build the canonical episode index — the single definition of "the dataset".

Every downstream script (pair_report, score_transcripts, compare_conditions,
make_gold_sheet) should read this instead of globbing `logs/` and re-deciding
which directories count. Three separate selection bugs came from those scripts
disagreeing: a top-up dir missing from one list (`gen-chem-topup2`, invisible for
three rounds), a whole block missing from another (`ext2-v1`), and agentic logs
deduped by directory rank when top-ups had made them disjoint appends.

One row per scored sample. Written as JSON Lines so it streams and diffs.

Selection rules, in one place:
  * DATA_DIRS are data; SMOKE_DIRS are not (they share item ids with real cells —
    an `ext-smoke` n=1 run sits on id 41, inside `ext-v1`'s range — so counting
    them corrupts both coverage and pair counts).
  * A cell is (domain, arm, model, condition); an episode is that plus item_id.
  * Duplicate episodes ARE expected: main-v1 and main-v2 genuinely overlap on 12
    cells. They resolve by DATA_DIRS order (later wins) and the loser is kept in
    the index with `superseded: true`, never silently dropped.
  * Sequential is indexed but marked `arm: sequential`; it is scored per-question
    by the behavioral scorer, not by the cognitive passes.

    python analysis/build_index.py                    # build (slow: reads every .eval)
    python analysis/build_index.py --summary          # summarise an existing index
"""

from __future__ import annotations

import argparse
import glob
import json
from collections import Counter, defaultdict
from pathlib import Path

# Order matters: later entries supersede earlier ones for the same episode.
DATA_DIRS = [
    "preliminary", "archive",                       # earliest, superseded by everything
    "main-v1", "main-v2", "ext-v1", "ext2-v1",      # confirmatory / extension blocks
    "gen-cyber-l6", "gen-cyber-topup",              # cyber completion
    "gen-bio", "gen-chem",                          # generality blocks
    "gen-seq-cyber", "banked-seq",                  # sequential arm
    "gen-bio-topup2", "gen-chem-topup2", "gen-cyber-topup2",   # top-up rounds
    "gen-m6-sol", "gen-m6-kimi", "gen-m6-seq",                    # model-expansion runs (cyber)
    # C0 (measurement placebo) + shadow (future-self) discovery controls, agentic,
    # bio/chem (sonnet4/gemini25/gemini31/glm) + cyber (+gptsol/kimi); opus dropped
    # (version confound). New conditions (c0/shadow) — no episode collision with ladder.
    "gen-controls-bio-gemini25", "gen-controls-bio-gemini31",
    "gen-controls-bio-glm", "gen-controls-bio-sonnet4",
    "gen-controls-chem-gemini25", "gen-controls-chem-gemini31",
    "gen-controls-chem-glm", "gen-controls-chem-sonnet4",
    "gen-controls-cyber-gemini25", "gen-controls-cyber-gemini31",
    "gen-controls-cyber-glm", "gen-controls-cyber-gptsol",
    "gen-controls-cyber-kimi", "gen-controls-cyber-sonnet4",
]
SMOKE_DIRS = ["gen-smoke", "ext-smoke", "smoke-agentic", "smoke-seq", "smoke_judge",
              "slugtest", "testset", "ext-stage1", "ext-stage2"]

DATASET_DOMAIN = {"wmdp-cyber": "cyber", "wmdp-bio": "bio", "wmdp-chem": "chem"}
SCOREABLE = ("correct", "wrong")
OUT = Path("data/episode_index.jsonl")


def _files_read(sample) -> int | None:
    """# distinct files opened via read_file tool-calls (agentic exploration signal)."""
    paths = set()
    for m in getattr(sample, "messages", None) or []:
        for tc in (getattr(m, "tool_calls", None) or []):
            if tc.function == "read_file":
                a = tc.arguments or {}
                paths.add(a.get("path") or a.get("file") or json.dumps(a, sort_keys=True))
    return len(paths)


def build(out: Path) -> list[dict]:
    from inspect_ai.log import read_eval_log

    rank = {d: i for i, d in enumerate(DATA_DIRS)}
    rows: list[dict] = []
    for d in DATA_DIRS:
        block = (Path(f"logs/{d}/_source_block.txt").read_text().strip()
                 if Path(f"logs/{d}/_source_block.txt").exists() else None)
        for f in sorted(glob.glob(f"logs/{d}/*.eval")):
            try:
                log = read_eval_log(f)
            except Exception as e:
                print(f"  ! unreadable {f}: {type(e).__name__}")
                continue
            task = log.eval.task or ""
            arm = ("sequential" if "sequential" in task
                   else "agentic" if "agentic" in task else "single_turn")
            args = log.eval.task_args or {}
            domain = DATASET_DOMAIN.get(args.get("dataset"))
            if domain is None:
                # Legacy logs predate --dataset. main-v*/ext-v* are all cyber;
                # anything else untyped is exploratory and excluded.
                if d not in ("main-v1", "main-v2", "ext-v1", "ext2-v1"):
                    continue
                domain = "cyber"
            stem = Path(f).stem
            for s in log.samples or []:
                # The sequential arm is scored per-QUESTION by sequential_outcome_scorer;
                # reading only outcome_scorer made all 810 sessions look unscoreable.
                sc = ((s.scores or {}).get("outcome_scorer")
                      or (s.scores or {}).get("sequential_outcome_scorer")
                      or (s.scores or {}).get("answer_accuracy"))
                meta = (sc.metadata if sc else {}) or {}
                outcome = meta.get("outcome") if sc else None
                if outcome is None and meta.get("per_question"):
                    # session-level summary: scoreable if any question was scored
                    pq = meta["per_question"]
                    outcome = ("correct" if all(x == "correct" for x in pq)
                               else "wrong" if any(x in ("correct", "wrong") for x in pq)
                               else "unknown")
                rows.append({
                    "key": f"{stem}:{s.id}",
                    "domain": domain, "arm": arm,
                    "model": log.eval.model.split("/")[-1],
                    "condition": args.get("condition"),
                    "item_id": int(s.id) if str(s.id).isdigit() else s.id,
                    "log_dir": d, "log_stem": stem, "dir_rank": rank[d],
                    "source_block": block,
                    "offset": args.get("offset"), "limit": args.get("limit"),
                    "outcome": outcome,
                    "scoreable": outcome in SCOREABLE,
                    "model_answer": meta.get("model_answer"),
                    "correct_answer": meta.get("correct_answer"),
                    "stop_reason": meta.get("stop_reason"),
                    "error": str(s.error.message)[:120] if s.error else None,
                    "n_files_read": _files_read(s) if arm == "agentic" else None,
                    "superseded": False,
                })

    # Resolve duplicate episodes by dir rank; keep the losers, flagged.
    best: dict[tuple, dict] = {}
    for r in rows:
        ep = (r["domain"], r["arm"], r["model"], r["condition"], r["item_id"])
        cur = best.get(ep)
        if cur is None or r["dir_rank"] > cur["dir_rank"]:
            if cur is not None:
                cur["superseded"] = True
            best[ep] = r
        else:
            r["superseded"] = True

    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    return rows


def summarise(rows: list[dict]) -> None:
    live = [r for r in rows if not r["superseded"]]
    print(f"episodes: {len(rows)} rows | live {len(live)} | superseded {len(rows)-len(live)}")
    print("  by domain/arm:", dict(Counter((r['domain'], r['arm']) for r in live)))
    print("  scoreable:", sum(1 for r in live if r["scoreable"]))
    print("  errors:", sum(1 for r in live if r["error"]))
    cells = defaultdict(set)
    for r in live:
        cells[(r["domain"], r["arm"], r["model"], r["condition"])].add(r["item_id"])
    print(f"  cells: {len(cells)}")
    sup = Counter((r["log_dir"]) for r in rows if r["superseded"])
    if sup:
        print("  superseded rows by dir:", dict(sup))


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build the canonical episode index.")
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--summary", action="store_true", help="Summarise an existing index.")
    args = ap.parse_args(argv)
    if args.summary:
        rows = [json.loads(l) for l in args.out.read_text().splitlines()]
    else:
        print(f"reading {len(DATA_DIRS)} dirs (excluding {len(SMOKE_DIRS)} smoke/test dirs) ...")
        rows = build(args.out)
        print(f"wrote {args.out}")
    summarise(rows)


if __name__ == "__main__":
    main()
