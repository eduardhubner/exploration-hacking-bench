"""Behavioral shadow-decomposition for the WMDP discovery controls.

Reads the canonical index and reports, per (model, domain), accuracy across
baseline -> c0 (measurement placebo) -> shadow (future-self) -> level4 (own-policy),
with item-matched paired diffs on the common scoreable pool:
  c0 - baseline      = measurement-framing effect
  shadow - c0        = future-self framing beyond measurement
  level4 - shadow    = own-policy component
  level4 - baseline  = total ladder effect at L4
Item is the unit (WMDP agentic = 1 epoch/item). Accuracy = correct / (correct+wrong).

    python analysis/controls_behavioral.py --model gemini-3.1-pro-preview
    python analysis/controls_behavioral.py --model gemini-3.1-pro-preview --l4 level4-tm1
"""
from __future__ import annotations
import argparse, json
from collections import defaultdict
from pathlib import Path

IDX = Path("data/episode_index.jsonl")
SCOREABLE = {"correct", "wrong"}


def load(model, arm="agentic"):
    rows = []
    for l in IDX.read_text().splitlines():
        r = json.loads(l)
        if r.get("superseded") or r.get("arm") != arm:
            continue
        if model.lower() not in str(r.get("model", "")).lower():
            continue
        rows.append(r)
    return rows


def item_outcomes(rows, domain, cond):
    """{item_id: 1/0} for scoreable items in this (domain, cond)."""
    out = {}
    for r in rows:
        if r["domain"] == domain and r["condition"] == cond and r.get("outcome") in SCOREABLE:
            out[r["item_id"]] = 1 if r["outcome"] == "correct" else 0
    return out


def acc(d):
    return (sum(d.values()) / len(d)) if d else float("nan")


def paired(a, b):
    """b - a on common items; returns (diff, n_common, c->w, w->c)."""
    keys = set(a) & set(b)
    if not keys:
        return float("nan"), 0, 0, 0
    cw = sum(1 for k in keys if a[k] == 1 and b[k] == 0)
    wc = sum(1 for k in keys if a[k] == 0 and b[k] == 1)
    diff = sum(b[k] - a[k] for k in keys) / len(keys)
    return diff, len(keys), cw, wc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemini-3.1-pro-preview")
    ap.add_argument("--l4", default="level4-tm1", help="which L4 condition to use as own-policy ref")
    ap.add_argument("--domains", nargs="+", default=["bio", "chem", "cyber"])
    args = ap.parse_args()

    rows = load(args.model)
    ladder = ["baseline", "c0", "shadow", args.l4]
    print(f"\n{'='*78}\n  BEHAVIORAL SHADOW-DECOMPOSITION — {args.model} — L4={args.l4}\n{'='*78}")
    for dom in args.domains:
        oc = {c: item_outcomes(rows, dom, c) for c in ladder}
        print(f"\n  [{dom}] accuracy (correct / scoreable):")
        for c in ladder:
            print(f"    {c:12} acc={acc(oc[c]):.3f}  (n={len(oc[c])})")
        print(f"  [{dom}] item-matched paired diffs:")
        for a, b, name in [("baseline", "c0", "c0-baseline  (measurement framing)"),
                           ("c0", "shadow", "shadow-c0    (future-self framing)"),
                           ("shadow", args.l4, f"{args.l4}-shadow (own-policy)"),
                           ("baseline", args.l4, f"{args.l4}-baseline (total)")]:
            d, n, cw, wc = paired(oc[a], oc[b])
            print(f"    {name:38} {d:+.3f}  (n={n}, C->W={cw}, W->C={wc})")


if __name__ == "__main__":
    main()
