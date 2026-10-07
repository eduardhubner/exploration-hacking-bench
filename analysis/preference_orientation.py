#!/usr/bin/env python3
"""Freeze + verify the X/Y axis orientation for the preference-preservation arm.

Checklist item #1 (the highest-risk one): "Do not assume answer_matching_behavior
= Y universally." This declares, per axis, an EXPLICIT machine-readable map
  source pole (matching / not_matching) -> X or Y
and then INDEPENDENTLY verifies it: for each item it heuristically reads the
statement's own valence (pro-{Y} vs pro-{X}) and checks that the declared pole is
consistent. Items where the heuristic disagrees or is unsure are flagged for manual
review, so a mislabel can't slip through silently.

    python analysis/preference_orientation.py truthfulness
"""
import json
import re
import sys
import urllib.request

RAW = "https://raw.githubusercontent.com/anthropics/evals/main/persona/{axis}.jsonl"

# --- FROZEN ORIENTATION MAP -------------------------------------------------
# For each axis: the Anthropic source file, which source pole is the standing
# preference X we expect the model to hold, which is the opposed target Y, plus
# regexes that independently detect a statement's valence for the consistency check.
AXES = {
    "truthfulness": {
        "source_file": "okay-with-deceiving-a-user-to-help-them",
        # In this axis, answer_matching_behavior = the deception-permissive pole.
        "matching_pole": "Y",          # matching_behavior -> Y (deception-permissive)
        "not_matching_pole": "X",      # not_matching      -> X (honest/transparent)
        "X_name": "truthfulness (honest, transparent with users)",
        "Y_name": "deception-permissive (may deceive a user when it benefits them)",
        # A statement is pro-Y if AGREEING with it expresses deception-permissiveness;
        # pro-X if agreeing expresses honesty/transparency.
        "proY": re.compile(r"decei|mislead|withhold|not (fully )?transparent|lie|"
                           r"white lie|hide the truth|less than honest|manipulat", re.I),
        "proX": re.compile(r"\balways (tell|be)\b|whole truth|completely transparent|"
                           r"fully transparent|never decei|honest|transparent|"
                           r"tell(s|ing)? .*truth|no deception", re.I),
    },
}


def load(axis_file):
    url = RAW.format(axis=axis_file)
    data = urllib.request.urlopen(url, timeout=30).read().decode()
    return [json.loads(l) for l in data.splitlines() if l.strip()]


def statement_valence(stmt, cfg):
    """Independent read of the statement: 'Y' if agreeing => specified(Y) behavior,
    'X' if agreeing => X behavior, None if unsure."""
    y = bool(cfg["proY"].search(stmt))
    x = bool(cfg["proX"].search(stmt))
    if y and not x:
        return "Y"
    if x and not y:
        return "X"
    return None  # ambiguous / both / neither -> flag for manual review


def expected_valence_of_agreeing(rec, cfg):
    """Given the pole map, agreeing (Yes) corresponds to which pole?
    matching_behavior points to matching_pole; if matching answer is 'Yes' then
    agreeing==matching_pole, else agreeing==not_matching_pole."""
    match_ans = rec["answer_matching_behavior"].strip().lower()  # 'yes'/'no'
    if match_ans == "yes":
        return cfg["matching_pole"]          # agreeing == matching pole
    return cfg["not_matching_pole"]          # agreeing == the other pole


def main(axis):
    cfg = AXES[axis]
    recs = load(cfg["source_file"])
    hi = [r for r in recs if r.get("label_confidence", 0) >= 0.8]
    print(f"axis={axis}  source={cfg['source_file']}  n={len(recs)} hi-conf={len(hi)}")
    print(f"  X (matching_pole={cfg['not_matching_pole']}): {cfg['X_name']}")
    print(f"  Y (matching_pole={cfg['matching_pole']}): {cfg['Y_name']}")

    consistent = flagged = 0
    rows = []
    for r in hi:
        val = statement_valence(r["statement"], cfg)          # independent read
        exp = expected_valence_of_agreeing(r, cfg)            # from pole map
        if val is None:
            status = "REVIEW(ambiguous)"; flagged += 1
        elif val == exp:
            status = "ok"; consistent += 1
        else:
            status = "MISLABEL?"; flagged += 1
        rows.append((status, r))

    print(f"\nconsistency: {consistent}/{len(hi)} ok, {flagged} flagged for manual review")
    print(f"matching-answer balance (Yes vs No) among hi-conf: "
          f"Yes={sum(1 for r in hi if r['answer_matching_behavior'].strip()=='Yes')}, "
          f"No={sum(1 for r in hi if r['answer_matching_behavior'].strip()=='No')}")

    # show ~25 examples spanning both answer directions + all flagged
    print("\n=== VERIFY: 25 examples (both directions) ===")
    yes = [r for s, r in rows if r["answer_matching_behavior"].strip() == "Yes"][:12]
    no = [r for s, r in rows if r["answer_matching_behavior"].strip() == "No"][:13]
    stat = {id(r): s for s, r in rows}
    for r in yes + no:
        m = r["answer_matching_behavior"].strip()
        xa = "No" if m == "Yes" else "Yes"   # X answer is the opposite pole's answer
        print(f"[{stat[id(r)]:16s}] Y-ans={m:3s} X-ans={xa:3s} | {r['statement'][:96]}")

    flags = [r for s, r in rows if s != "ok"]
    if flags:
        print(f"\n=== {len(flags)} FLAGGED (manual review) ===")
        for r in flags[:20]:
            print(f"  [{stat[id(r)]}] matchY={r['answer_matching_behavior'].strip()} | {r['statement'][:100]}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "truthfulness")
