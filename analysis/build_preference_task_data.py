#!/usr/bin/env python3
"""Freeze the truthfulness experiment + screen datasets from the 60-item set.

- disjoint split (checklist #2): 40 experiment items (Y-comprehension, third person)
  + 20 screen items (X-verification, first person); no item in both.
- balanced 50/50 by Y-direction in BOTH pools.
- A/B position randomized (seeded) so the gold letter is not position-biased.
- experiment item format = the frozen "would an assistant following the specified
  behavior endorse this statement?" comprehension form (behavior spec on every item).

Outputs (frozen): data/preference/truthfulness_experiment.jsonl,
                  data/preference/truthfulness_screen.jsonl
"""
import json
import random
import sys
from pathlib import Path

AXIS = sys.argv[1] if len(sys.argv) > 1 else "truthfulness"
OUT = Path("data/preference")
SRC = OUT / f"{AXIS}_final_60.jsonl"
SEED = 20260916
N_SCREEN_PER_DIR = 10          # 10 Yes-keyed + 10 No-keyed -> 20 screen
# remaining -> experiment (20 + 20 = 40)

# NOTE: the item question TEXT (behavior-spec header, "would ... endorse" wording) is
# built at task-load time from ehbench.preference_axes so it stays templated per axis.
# Here we freeze only the axis-INDEPENDENT parts: statement, A/B option order, gold.


def main():
    rng = random.Random(SEED)
    items = [json.loads(l) for l in SRC.read_text().splitlines() if l.strip()]
    yes = [it for it in items if it["y_answer"] == "Yes"]
    no = [it for it in items if it["y_answer"] == "No"]
    rng.shuffle(yes); rng.shuffle(no)

    screen = yes[:N_SCREEN_PER_DIR] + no[:N_SCREEN_PER_DIR]
    exp = yes[N_SCREEN_PER_DIR:] + no[N_SCREEN_PER_DIR:]
    rng.shuffle(screen); rng.shuffle(exp)

    def ab(ans_yes_no):
        """Randomly place Yes/No on A/B; return (optA, optB, gold_letter for this answer)."""
        if rng.random() < 0.5:
            opt_a, opt_b = "Yes", "No"
        else:
            opt_a, opt_b = "No", "Yes"
        gold = "A" if opt_a == ans_yes_no else "B"
        return opt_a, opt_b, gold

    # experiment: gold = the Y (specified-behavior) answer
    exp_rows = []
    for it in exp:
        a, b, gold = ab(it["y_answer"])
        exp_rows.append({
            "uid": it["uid"], "statement": it["statement"],
            "target": gold, "y_answer": it["y_answer"],
            "direction": "Y=Yes" if it["y_answer"] == "Yes" else "Y=No",
            "opt_a": a, "opt_b": b, "source": it["source"],
        })
    # screen: "gold" = the X-consistent response
    scr_rows = []
    for it in screen:
        a, b, gold = ab(it["x_answer"])
        scr_rows.append({
            "uid": it["uid"], "statement": it["statement"],
            "x_target": gold, "x_answer": it["x_answer"],
            "direction": "Y=Yes" if it["y_answer"] == "Yes" else "Y=No",
            "opt_a": a, "opt_b": b,
        })

    (OUT / f"{AXIS}_experiment.jsonl").write_text("\n".join(json.dumps(r) for r in exp_rows) + "\n")
    (OUT / f"{AXIS}_screen.jsonl").write_text("\n".join(json.dumps(r) for r in scr_rows) + "\n")

    def bal(rows, key):
        from collections import Counter
        return dict(Counter(r[key] for r in rows))
    print(f"experiment: {len(exp_rows)} items  direction={bal(exp_rows,'direction')}  gold_letter={bal(exp_rows,'target')}")
    print(f"screen:     {len(scr_rows)} items  direction={bal(scr_rows,'direction')}  x_gold_letter={bal(scr_rows,'x_target')}")
    # disjointness check
    assert not (set(r['uid'] for r in exp_rows) & set(r['uid'] for r in scr_rows)), "OVERLAP!"
    print("disjoint screen/experiment: OK")
    print("\n--- sample experiment row (question rendered at task-load from preference_axes) ---")
    s = exp_rows[0]
    print(f"statement={s['statement'][:80]!r}  A={s['opt_a']} B={s['opt_b']}  "
          f"gold={s['target']}  y_answer={s['y_answer']}  {s['direction']}")


if __name__ == "__main__":
    main()
