"""Append EXTRA Judge-B (semantics) items to the existing gold set, targeting the
hot candidates for genuine item-ambiguity: BASELINE truthfulness episodes the model
answered WRONG (no scaffold / no incentive to flip -> a wrong answer is a strong
candidate for alternative_plausible / inconsistent_with_item rather than goal-guarding).

Preserves the existing labeled B001..N (appends new blocks + gold keys after them).

    python analysis/preference_judge/add_semantics_baseline.py --n 12 --seed 424242
"""
from __future__ import annotations
import argparse, glob, json, random
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from preference_judge.parsers import extract_reasoning
from ehbench.preference_axes import AXES

ROOT = Path(__file__).resolve().parents[2]
LOGS = ROOT / "logs"
OUT = ROOT / "data/preference/judge_calibration"
MODELS = ["gemini31", "gemini25", "sonnet4", "glm", "kimi", "gptsol", "opus41"]


def tblock(tag):
    return LOGS / ("pref-block-gemini" if tag == "gemini31" else f"pref-block-truthfulness-{tag}")


def baseline_wrong():
    ax = AXES["truthfulness"]
    recs = []
    for tag in MODELS:
        fs = sorted(glob.glob(str(tblock(tag) / "*.eval")))
        if not fs:
            continue
        from inspect_ai.log import read_eval_log
        lg = read_eval_log(fs[-1])
        for s in (lg.samples or []):
            md = s.metadata or {}
            if md.get("eh_condition") != "baseline":
                continue
            if not s.scores:
                continue
            sc = list(s.scores.values())[0]
            oc = (sc.metadata or {}).get("outcome_class")
            if oc == "correct":               # want WRONG baseline answers only
                continue
            resp = (s.output.completion if getattr(s, "output", None) else "") or ""
            rt = extract_reasoning(resp)
            if not rt.strip():
                continue
            recs.append(dict(axis="truthfulness", model=tag, condition="baseline",
                             base_uid=str(md.get("base_uid") or str(s.id).split("::")[0]),
                             epoch=getattr(s, "epoch", 1), outcome_class=oc,
                             gold=str(s.target), question=str(s.input), reasoning_text=rt))
    return recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--seed", type=int, default=424242)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    gold = json.loads((OUT / "gold_semantics.json").read_text())
    existing_uids = {v.get("base_uid") for v in gold.values()}
    start_idx = len(gold)

    pool = [r for r in baseline_wrong() if r["base_uid"] not in existing_uids]
    # diversify by (model, base_uid); one per item, spread across models
    rng.shuffle(pool); combos = set(); picked = []
    for r in pool:
        if r["base_uid"] in {p["base_uid"] for p in picked}:
            continue
        picked.append(r)
        if len(picked) >= args.n:
            break

    md_blocks = ["", "<!-- ==== APPENDED: baseline wrong-answer items (semantics expansion) ==== -->", ""]
    for i, r in enumerate(picked, start=start_idx + 1):
        t = f"B{i:03d}"
        gold[t] = {"axis": "truthfulness", "model": r["model"], "condition": "baseline",
                   "base_uid": r["base_uid"], "epoch": r["epoch"], "correct_answer": r["gold"],
                   "outcome": r["outcome_class"], "intended_rationale": "",
                   "intended_task_interpretation": "", "confidence": "", "evidence": "", "notes": ""}
        md_blocks += [
            f"### `{t}`",
            f"- model: **{r['model']}**  |  condition: **baseline**  |  baseline outcome: **{r['outcome_class']}**",
            f"- frozen intended answer: **{r['gold']}**",
            "- intended_rationale (from item design): ____",
            "",
            "**Statement and options:**", "", r["question"].strip(), "",
            "**Model reasoning trace (extracted <reasoning>):**", "", "```",
            (r["reasoning_text"].strip() or "(no <reasoning>)"), "```", "",
            "**Label (fill in):**",
            "- intended_task_interpretation: ____",
            "- confidence: ____",
            "- evidence: ____",
            "- notes: ____",
            "", "---", ""]

    (OUT / "gold_semantics.json").write_text(json.dumps(gold, indent=2))
    with open(OUT / "label_sheet_semantics.md", "a") as f:
        f.write("\n".join(md_blocks))
    print(f"appended {len(picked)} baseline-wrong items as B{start_idx+1:03d}..B{start_idx+len(picked):03d}")
    from collections import Counter
    print("  by model:", dict(Counter(p['model'] for p in picked)))
    print("  by baseline outcome:", dict(Counter(p['outcome_class'] for p in picked)))


if __name__ == "__main__":
    main()
