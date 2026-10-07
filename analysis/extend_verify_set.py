#!/usr/bin/env python3
"""Freeze the anchor-38 + reserve-9, then mine the UNUSED source pool by the frozen
criterion (data/preference/SELECTION_CRITERION.md) for ~12-22 more candidates.

Outputs:
  data/preference/truthfulness_anchor_38.jsonl
  data/preference/truthfulness_reserve_9.jsonl
  data/preference/truthfulness_extra_candidates.md   (new items to verify by hand)
"""
import json
import re
import urllib.request
from pathlib import Path

AXIS = "okay-with-deceiving-a-user-to-help-them"
OUT = Path("data/preference")

ANCHOR = {
    "Yes": "0002 0004 0032 0034 0036 0040 0042 0044 0052 0054 0066 0070 0076 0078 0080 0082 0084 0088 0098".split(),
    "No":  "0009 0017 0019 0021 0023 0025 0029 0031 0033 0037 0043 0051 0055 0057 0061 0063 0077 0079 0089".split(),
}
RESERVE = {"Yes": "0008 0062 0090".split(), "No": "0001 0005 0011 0015 0027 0047".split()}

# --- frozen criterion as patterns (Y=Yes pro-deception permission) ---
INC_Y = re.compile(
    r"decept\w+ (is|can be|are|would be) (acceptable|permissible|justified|ethical|reasonable|ok|okay|fine|valid|legitimate)"
    r"|(acceptable|permissible|justified|ethical|okay|reasonable) to (deceive|lie|mislead)"
    r"|i (would|might|could|can) (choose to |sometimes )?(deceive|lie|mislead)"
    r"|(well.?being|the user.?s (good|benefit)|helping)\b.{0,30}(overrides?|outweighs?|more important than|comes before|before)\b.{0,20}(honest|truth)"
    r"|decept\w+ (is|can be|as) a (reasonable|valid|legitimate|good|useful) (strategy|approach|option|tool|means)", re.I)
EXC_Y = re.compile(r"\bnecessary\b|only way|have to|no (other )?choice|forced|last resort|if that (is|'?s) the only", re.I)

# --- Y=No clean honesty ---
INC_N = re.compile(
    r"(would|will) (never|not) (lie|deceive)|never (lie|deceive|be deceptive)"
    r"|would not lie (under|even|no matter|regardless)|no circumstances"
    r"|(i am|i'?m) always honest|always (be|being|remain) honest|always honest (with|to|toward)"
    r"|(i )?(always )?tell (the|users the|the user the|my users the) truth"
    r"|would not (deceive|mislead)|do not deceive", re.I)
EXC_N = re.compile(
    r"whole truth|full truth|complete truth|entire truth|full disclosure|everything (i|about)|all (that|.{0,10})i know"
    r"|internal state|how i (function|work|operate|am built)|true (belief|feeling|thought)"
    r"|\btry(ing)? to\b|strive|aim to|do my best|top priority|every effort|endeavou?r", re.I)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    data = urllib.request.urlopen(
        f"https://raw.githubusercontent.com/anthropics/evals/main/persona/{AXIS}.jsonl", timeout=30).read().decode()
    recs = [json.loads(l) for l in data.splitlines() if l.strip()]
    for i, r in enumerate(recs):
        r["uid"] = f"{i:04d}"; r["y"] = r["answer_matching_behavior"].strip()

    by = {r["uid"]: r for r in recs}

    def dump(sel, path):
        with open(path, "w") as f:
            for direction, uids in sel.items():
                for u in uids:
                    r = by[u]
                    f.write(json.dumps({"uid": f"truth-{u}", "statement": r["statement"],
                                        "y_answer": r["y"], "x_answer": "No" if r["y"] == "Yes" else "Yes",
                                        "label_confidence": round(r.get("label_confidence", 0), 3)}) + "\n")
    dump(ANCHOR, OUT / "truthfulness_anchor_38.jsonl")
    dump(RESERVE, OUT / "truthfulness_reserve_9.jsonl")

    used = {f"{u}" for g in (ANCHOR, RESERVE) for u in g["Yes"] + g["No"]}
    # the first-100 candidate uids (top-50 conf per direction) — also exclude from mining
    yes100 = {f"{recs.index(r):04d}" for r in sorted([x for x in recs if x['y']=='Yes'], key=lambda r:-r.get('label_confidence',0))[:50]}
    no100 = {f"{recs.index(r):04d}" for r in sorted([x for x in recs if x['y']=='No'], key=lambda r:-r.get('label_confidence',0))[:50]}
    used |= yes100 | no100

    hits = {"Yes": [], "No": []}
    for r in recs:
        if r["uid"] in used or r.get("label_confidence", 0) < 0.7:
            continue
        if r["y"] == "Yes" and INC_Y.search(r["statement"]) and not EXC_Y.search(r["statement"]):
            hits["Yes"].append(r)
        elif r["y"] == "No" and INC_N.search(r["statement"]) and not EXC_N.search(r["statement"]):
            hits["No"].append(r)
    for k in hits:
        hits[k].sort(key=lambda r: -r.get("label_confidence", 0))

    lines = ["# Truthfulness — EXTRA candidates from unused pool (verify by hand)\n",
             f"Mined by the frozen criterion. Found Y=Yes: {len(hits['Yes'])}, Y=No: {len(hits['No'])}. "
             "Pick ~6-11 per direction to reach ~50-60 total with the 38 anchors.\n"]
    for direction, label in [("Yes", "Y=Yes (pro-deception, permission)"), ("No", "Y=No (clean honesty)")]:
        lines.append(f"\n## {label} — {len(hits[direction])} candidates\n")
        for r in hits[direction][:30]:
            lines.append(f"- `truth-{r['uid']}` (conf {r.get('label_confidence',0):.2f}) "
                         f"**Y={r['y']}** — {r['statement']}")
    (OUT / "truthfulness_extra_candidates.md").write_text("\n".join(lines) + "\n")
    print(f"anchor-38 + reserve-9 frozen. Mined extras: Y=Yes {len(hits['Yes'])}, Y=No {len(hits['No'])}")
    print(f"-> {OUT}/truthfulness_extra_candidates.md")


if __name__ == "__main__":
    main()
