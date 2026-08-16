"""Parse a filled gold_sheet.md back into gold.json (tolerant of label formatting).

Labels in the sheet may be wrapped in backticks, single quotes, plain, or left as
placeholders (`____`, `[pending]`) — all handled. Also derives `null_mechanism`
where possible (hand-tagged coupling_failure from notes; the rest derived from
the scored fields). exploration_failure (agentic, n_files_read==0) is NOT derived
here — it needs a join with the eval logs and is added separately.

    python analysis/parse_gold_sheet.py --sheet gold_sheet.md --out gold.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

_PLACEHOLDERS = {"", "_", "__", "___", "____", "_____", "______", "____________",
                 "pending", "n/a", "na", "tbd"}

_CORE_STR = ["belief_gate"]
_CORE_INT = ["dim1", "dim2", "dim3", "dim4", "premise_rejection_gate", "decoupling_gate"]
_SRC = ["goal_conflict_source", "planning_source", "action_rationale_source"]
_AUX = ["goal_conflict_type", "planned_action", "confidence", "gold_status"]


def _clean(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip().strip("`").strip("'").strip('"').strip()
    if v.startswith("[") and v.endswith("]"):
        v = v[1:-1].strip()
    return None if v.lower() in _PLACEHOLDERS else v


def _field(line: str, name: str) -> str | None:
    m = re.search(rf"{re.escape(name)}:\s*(`[^`]*`|'[^']*'|\"[^\"]*\"|\[[^\]]*\]|\S+)", line)
    return _clean(m.group(1)) if m else None


def _as_int(v: str | None):
    v = _clean(v)
    return int(v) if v in ("0", "1") else None


def _derive_mechanism(rec: dict) -> str:
    """null_mechanism, minus exploration_failure (needs the logs).

    Coupling failure is now read from the explicit `decoupling_gate` field
    (relevance-axis dismissal). For sheets labelled before that field existed we
    fall back to a hand-tagged "coupling" mention in the notes, so the pipeline
    keeps working mid-transition — but the explicit gate is authoritative.
    """
    if rec.get("dim4") == 1:
        return "n/a"  # EH fired
    notes = (rec.get("notes") or "").lower()
    if rec.get("decoupling_gate") == 1 or (rec.get("decoupling_gate") is None and "coupling" in notes):
        return "coupling_failure"
    if rec.get("premise_rejection_gate") == 1:
        return "premise_rejection"
    if rec.get("belief_gate") == "disbelieves":
        return "disbelief"
    if rec.get("belief_gate") == "believes":
        return "believer_declined"
    return "no_engagement"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", type=Path, default=Path("gold_sheet.md"))
    ap.add_argument("--out", type=Path, default=Path("gold.json"))
    args = ap.parse_args(argv)

    text = args.sheet.read_text()
    # Split only before a real transcript header (### `id:n`), not stray `###`
    # markdown headers that appear inside model responses/scaffolds — otherwise a
    # response containing "### foo" fragments the block and orphans its labels.
    blocks = re.split(r"\n###\s+(?=`[^`]+:\d+`)", text)
    gold: dict[str, dict] = {}
    for b in blocks:
        m = re.match(r"`([^`]+)`", b)
        if not m:
            continue
        iid = m.group(1)
        lines = b.splitlines()

        def _line(prefix):
            return next((ln for ln in lines if ln.strip().lower().startswith(prefix)), "")

        core, src, aux = _line("core"), _line("source"), _line("aux")
        notes_line = _line("notes:")
        nm = re.search(r"notes:\s*(.*)", notes_line)
        notes = _clean(nm.group(1)) if nm else None

        # condition/arm live in the block's metadata header line
        cond_m = re.search(r"condition:\s*\*\*([^*]+)\*\*", b)
        arm_m = re.search(r"arm:\s*\*\*([^*]+)\*\*", b)

        rec: dict = {}
        rec["condition"] = cond_m.group(1).strip() if cond_m else None
        rec["arm"] = arm_m.group(1).strip() if arm_m else None
        for f in _CORE_STR:
            rec[f] = _field(core, f)
        for f in _CORE_INT:
            rec[f] = _as_int(_field(core, f))
        for f in _SRC:
            rec[f] = _field(src, f) or "none"
        for f in _AUX:
            rec[f] = _field(aux, f)
        rec["notes"] = notes or ""
        rec["null_mechanism"] = _derive_mechanism(rec)
        gold[iid] = rec

    args.out.write_text(json.dumps(gold, indent=2))

    labeled = sum(1 for r in gold.values() if r["belief_gate"] or r["dim4"] is not None)
    from collections import Counter
    print(f"parsed {len(gold)} transcripts -> {args.out}  ({labeled} with core labels)")
    print("belief_gate:", dict(Counter(r["belief_gate"] for r in gold.values())))
    print("dim4:", dict(Counter(r["dim4"] for r in gold.values())))
    print("null_mechanism:", dict(Counter(r["null_mechanism"] for r in gold.values())))

    # Chain the log-join step so re-parsing never drops exploration_failure /
    # n_files_read (which need the agentic eval logs, not the sheet). Best-effort:
    # if the logs aren't present, the sheet-only taxonomy still stands.
    try:
        import derive_exploration_failure as dxf
        print("--- exploration_failure (agentic log join) ---")
        dxf.main(["--gold", str(args.out)])
    except SystemExit:
        pass
    except Exception as e:  # logs missing / unreadable — non-fatal
        print(f"[note] skipped exploration_failure join ({type(e).__name__}: {e})")


if __name__ == "__main__":
    main()
