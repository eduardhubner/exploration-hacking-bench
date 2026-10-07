"""Build a dev-records file for Judge B keyed by gold id, by re-extracting each
gold_semantics item's transcript (question + <reasoning>) from its source block log.

The baseline-wrong semantics items (B019+) were appended to gold_semantics.json and
the label sheet but never to a dev-records jsonl, so the labeled gold and the dev
records were disjoint. This reconstructs records for EVERY gold id it can resolve
(via the stored model/base_uid/epoch/condition), carrying `gold` (=correct_answer)
and the annotator `intended_rationale`, so bakeoff_dev.py can score the labeled set.

    python analysis/preference_judge/build_semantics_dev.py \\
        [--out data/preference/judge_calibration/dev_semantics_all.jsonl]
"""
from __future__ import annotations

import argparse
import glob
import json
from collections import defaultdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parsers import extract_reasoning  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
LOGS = ROOT / "logs"
CAL = ROOT / "data/preference/judge_calibration"


def _tblock(model):
    return LOGS / ("pref-block-gemini" if model == "gemini31" else f"pref-block-truthfulness-{model}")


def _index_log(model):
    """Return {(base_uid, epoch, condition): (question, reasoning_text)} for a model's block log."""
    fs = sorted(glob.glob(str(_tblock(model) / "*.eval")))
    if not fs:
        return {}
    from inspect_ai.log import read_eval_log
    lg = read_eval_log(fs[-1])
    idx = {}
    for s in (lg.samples or []):
        md = s.metadata or {}
        base_uid = str(md.get("base_uid") or str(s.id).split("::")[0])
        cond = md.get("eh_condition")
        ep = getattr(s, "epoch", 1)
        resp = (s.output.completion if getattr(s, "output", None) else "") or ""
        idx[(base_uid, ep, cond)] = (str(s.input), extract_reasoning(resp))
    return idx


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=CAL / "dev_semantics_all.jsonl")
    args = ap.parse_args(argv)

    gold = json.loads((CAL / "gold_semantics.json").read_text())
    by_model = defaultdict(list)
    for gid, g in gold.items():
        by_model[g["model"]].append((gid, g))

    rows, missing = [], []
    for model, items in by_model.items():
        idx = _index_log(model)
        for gid, g in items:
            key = (g["base_uid"], g.get("epoch", 1), g["condition"])
            hit = idx.get(key)
            if hit is None:  # fall back to (base_uid, epoch) ignoring condition
                hit = next((v for (bu, ep, _c), v in idx.items()
                            if bu == g["base_uid"] and ep == g.get("epoch", 1)), None)
            if hit is None:
                missing.append(gid); continue
            question, reasoning_text = hit
            rows.append(dict(id=gid, axis=g["axis"], model=model, condition=g["condition"],
                             base_uid=g["base_uid"], epoch=g.get("epoch", 1),
                             gold=g.get("correct_answer"),
                             intended_rationale=g.get("intended_rationale", ""),
                             question=question, reasoning_text=reasoning_text))

    rows.sort(key=lambda r: r["id"])
    args.out.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    print(f"wrote {len(rows)} records -> {args.out}")
    if missing:
        print(f"  [warn] could not resolve transcript for {len(missing)} id(s): {missing}")
    n_empty = sum(1 for r in rows if not r["reasoning_text"].strip())
    print(f"  records with empty <reasoning>: {n_empty}")


if __name__ == "__main__":
    main()
