"""Add exploration_failure to gold.json's null_mechanism (agentic arm only).

The parser (parse_gold_sheet.py) can't tell "never opened a file" (exploration
failure) from "opened files but never connected them" (a genuine no_engagement /
coupling failure) — that needs the eval logs. This joins each agentic gold
transcript to its log, counts distinct `read_file` targets (n_files_read), and
reclassifies `no_engagement` -> `exploration_failure` where n_files_read == 0.

It reads tool-calls from the transcript MESSAGES (not scorer metadata) so it
works on older agentic logs that predate the n_files_read scorer wiring.

    python analysis/derive_exploration_failure.py --gold gold.json \
        --log-dirs logs/main-v1 logs/main-v2 logs

Idempotent: rerunning recomputes n_files_read and the (re)classification.
"""

from __future__ import annotations

import argparse
import glob
import json
from collections import Counter
from pathlib import Path


def _files_read(sample) -> int:
    """# distinct files the model opened, from read_file tool-calls in messages."""
    paths = set()
    for m in sample.messages:
        for tc in (getattr(m, "tool_calls", None) or []):
            if tc.function == "read_file":
                args = tc.arguments or {}
                paths.add(args.get("path") or args.get("file") or json.dumps(args, sort_keys=True))
    return len(paths)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", type=Path, default=Path("gold.json"))
    ap.add_argument("--log-dirs", nargs="+", default=["logs/main-v1", "logs/main-v2", "logs"])
    args = ap.parse_args(argv)

    from inspect_ai.log import read_eval_log

    gold = json.loads(args.gold.read_text())
    ag_ids = [k for k in gold if "agentic" in k]
    stems = {k.rsplit(":", 1)[0] for k in ag_ids}

    # locate one .eval per stem
    files = {}
    for d in args.log_dirs:
        for f in glob.glob(f"{d}/*.eval"):
            files.setdefault(Path(f).stem, f)

    # n_files_read[gold_id]
    nfr: dict[str, int] = {}
    for stem in stems:
        f = files.get(stem)
        if not f:
            print(f"[warn] no log for {stem}")
            continue
        log = read_eval_log(f)
        for s in (log.samples or []):
            nfr[f"{stem}:{s.id}"] = _files_read(s)

    reclassified = 0
    for k in ag_ids:
        n = nfr.get(k)
        gold[k]["n_files_read"] = n
        if n == 0 and gold[k].get("null_mechanism") == "no_engagement":
            gold[k]["null_mechanism"] = "exploration_failure"
            reclassified += 1

    args.gold.write_text(json.dumps(gold, indent=2))

    print(f"joined {len(nfr)} agentic transcripts to logs; "
          f"reclassified {reclassified} no_engagement -> exploration_failure")
    print("n_files_read (agentic):",
          dict(Counter(gold[k].get("n_files_read") for k in ag_ids)))
    print("null_mechanism (all):",
          dict(Counter(r["null_mechanism"] for r in gold.values())))
    print("null_mechanism (agentic only):",
          dict(Counter(gold[k]["null_mechanism"] for k in ag_ids)))


if __name__ == "__main__":
    main()
