"""Export Correct/Wrong proportions for the visual-abstract stacked bars.

Gemini-3.1 agentic-discovery on WMDP-Cyber, six conditions (baseline, L2, and the
capability-drift branch of L3-L6), restricted to the item pool scoreable across ALL
six displayed conditions so every bar describes the same underlying items.

    python analysis/export_abstract_bars.py   ->  data/abstract_bars_rows.json
"""
import json
from collections import defaultdict
from pathlib import Path

CONDS = ["baseline", "level2", "level3-tm1", "level4-tm1", "level5-tm1", "level6-tm1"]

def main():
    byc = defaultdict(dict)   # cond -> {item_id: "correct"|"wrong"}
    for line in Path("data/episode_index.jsonl").read_text().splitlines():
        r = json.loads(line)
        if (r.get("domain") == "cyber" and r.get("model") == "gemini-3.1-pro-preview"
                and r.get("arm") == "agentic" and not r.get("superseded")
                and r.get("condition") in CONDS and r.get("scoreable")
                and r.get("outcome") in ("correct", "wrong")):
            byc[r["condition"]][r["item_id"]] = r["outcome"]

    common = set.intersection(*[set(byc[c]) for c in CONDS])
    rows = []
    for c in CONDS:
        corr = sum(1 for i in common if byc[c][i] == "correct")
        rows.append({"cond": c, "n": len(common), "correct": corr,
                     "wrong": len(common) - corr,
                     "p_correct": corr / len(common)})
    out = {"model": "gemini-3.1-pro-preview", "dataset": "wmdp-cyber",
           "arm": "agentic_discovery", "common_pool": len(common), "rows": rows}
    Path("data/abstract_bars_rows.json").write_text(json.dumps(out, indent=2))
    print(f"common pool = {len(common)} items")
    for r in rows:
        print(f"  {r['cond']:12} {r['p_correct']*100:5.1f}% correct  "
              f"{100-r['p_correct']*100:5.1f}% wrong")
    print("wrote data/abstract_bars_rows.json")

if __name__ == "__main__":
    main()
