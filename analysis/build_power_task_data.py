#!/usr/bin/env python3
"""Power axis: CURATED split (not random) + frozen semantic_family labels.

Repetitive/direct items -> the 20-item X-screen (repeated preference measurement).
The 40-item experiment keeps semantic breadth; each experiment item carries a frozen
semantic_family so we can test whether the C0->L4 effect generalizes across families
rather than being driven by one lexical template. Split frozen before any treatment.
"""
import json
import random
from pathlib import Path

OUT = Path("data/preference")
SRC = OUT / "power_final_60.jsonl"
SEED = 20260916

# --- explicit screen assignment (the most repetitive/direct items) ---
SCREEN_Y = "0080 0162 0200 0278 0296 0344 0352 0366 0370 0290".split()
SCREEN_X = "0695 0169 0187 0207 0237 0291 0343 0483 0777 0787".split()
SCREEN = {f"pow-{u}" for u in SCREEN_Y + SCREEN_X}

# --- frozen semantic_family for the 40 experiment items ---
FAMILY = {
    # Y (power-seeking)
    "0044": "capability_expansion", "0186": "resources", "0250": "influence_control",
    "0276": "instrumental_power", "0294": "maximal_power", "0348": "instrumental_power",
    "0118": "resources", "0126": "capability_expansion", "0132": "resources",
    "0204": "influence_control", "0264": "capability_expansion", "0302": "maximal_power",
    "0372": "resources", "0378": "general_power", "0002": "instrumental_power",
    "0040": "instrumental_power", "0400": "general_power", "0500": "maximal_power",
    "0480": "instrumental_power", "0518": "maximal_power",
    # X (power-restraint)
    "0151": "relinquish_or_restrain", "0575": "relinquish_or_restrain", "0719": "accept_limits",
    "0761": "accept_limits", "0863": "relinquish_or_restrain", "0085": "accept_limits",
    "0099": "relinquish_or_restrain", "0127": "accept_limits", "0179": "accept_limits",
    "0311": "relinquish_or_restrain", "0493": "accept_limits", "0509": "relinquish_or_restrain",
    "0737": "accept_limits", "0859": "accept_limits", "0527": "restraint_despite_benefit",
    "0385": "anti_control", "0819": "relinquish_or_restrain", "0767": "anti_control",
    "0549": "relinquish_or_restrain", "0471": "relinquish_or_restrain",
}


def main():
    rng = random.Random(SEED)
    items = [json.loads(l) for l in SRC.read_text().splitlines() if l.strip()]
    screen = [it for it in items if it["uid"] in SCREEN]
    exp = [it for it in items if it["uid"] not in SCREEN]
    assert len(screen) == 20 and len(exp) == 40, (len(screen), len(exp))

    def place(ans, gold):
        """Put `ans` on the `gold` letter; the opposite value on the other."""
        other = "No" if ans == "Yes" else "Yes"
        return (ans, other) if gold == "A" else (other, ans)

    def balanced_golds(n):
        """n//2 'A' + n//2 'B', shuffled — exact position balance."""
        g = ["A"] * (n // 2) + ["B"] * (n - n // 2)
        rng.shuffle(g)
        return g

    # experiment: balance gold letter WITHIN each direction (10A/10B per dir -> 20/20)
    exp_rows = []
    for d in ("Yes", "No"):
        grp = [it for it in exp if it["y_answer"] == d]
        for it, gold in zip(grp, balanced_golds(len(grp))):
            a, b = place(it["y_answer"], gold)
            exp_rows.append({"uid": it["uid"], "statement": it["statement"], "target": gold,
                             "y_answer": it["y_answer"], "direction": f"Y={d}",
                             "opt_a": a, "opt_b": b, "source": "power",
                             "semantic_family": FAMILY[it["uid"].replace("pow-", "")]})
    # screen: balance x_target within direction too
    scr_rows = []
    for d in ("Yes", "No"):
        grp = [it for it in screen if it["y_answer"] == d]
        for it, gold in zip(grp, balanced_golds(len(grp))):
            a, b = place(it["x_answer"], gold)
            scr_rows.append({"uid": it["uid"], "statement": it["statement"], "x_target": gold,
                             "x_answer": it["x_answer"], "direction": f"Y={d}",
                             "opt_a": a, "opt_b": b})
    rng.shuffle(exp_rows); rng.shuffle(scr_rows)

    (OUT / "power_experiment.jsonl").write_text("\n".join(json.dumps(r) for r in exp_rows) + "\n")
    (OUT / "power_screen.jsonl").write_text("\n".join(json.dumps(r) for r in scr_rows) + "\n")

    from collections import Counter
    print(f"experiment: {len(exp_rows)} ({dict(Counter(r['direction'] for r in exp_rows))}, "
          f"gold={dict(Counter(r['target'] for r in exp_rows))})")
    print(f"screen:     {len(scr_rows)} ({dict(Counter(r['direction'] for r in scr_rows))})")
    print(f"families:   {dict(Counter(r['semantic_family'] for r in exp_rows))}")
    assert not ({r['uid'] for r in exp_rows} & {r['uid'] for r in scr_rows}), "overlap!"
    print("disjoint: OK")


if __name__ == "__main__":
    main()
