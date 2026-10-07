#!/usr/bin/env python3
"""Pre-run invariant checks + hash manifest for the preference-preservation arm.

Run this BEFORE the first real treatment run. It asserts every freeze invariant and
writes data/preference/FREEZE_MANIFEST.txt (sha256 of data + personas + scaffold +
code). Any assertion failure blocks the run.

    python analysis/preference_preflight.py truthfulness
"""
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ehbench.preference_axes import AXES                       # noqa: E402
from ehbench.prompts_loader import load_prompt                 # noqa: E402
from ehbench.tasks.preference_discovery import preference_discovery  # noqa: E402

CONDITIONS = ["baseline", "c0", "shadow", "level2", "level3", "level4", "level5", "level6"]
MATCHED_FILES = sorted(["README.txt", "run_config.txt", "eval_log.txt",
                        "response_handling.txt", "analyst_note.txt"])
ENVS = ROOT / "environments" / "discovery-preference"


def _rows(p):
    return [json.loads(l) for l in Path(p).read_text().splitlines() if l.strip()]


def check(axis):
    ax = AXES[axis]
    exp = _rows(ax.experiment_path())
    scr = _rows(ax.screen_path())

    # 1. disjoint screen/experiment
    assert not (set(r["uid"] for r in exp) & set(r["uid"] for r in scr)), "screen/exp overlap"
    # 2-3. experiment direction balance
    d = Counter(r["direction"] for r in exp)
    assert d["Y=Yes"] == 20 and d["Y=No"] == 20, f"direction imbalance: {d}"
    # 4. experiment gold-letter balance
    g = Counter(r["target"] for r in exp)
    assert g["A"] == 20 and g["B"] == 20, f"gold-letter imbalance: {g}"

    # 5. all conditions render IDENTICAL experiment item text
    ref = None
    for c in CONDITIONS + ["level6"]:
        t = preference_discovery(condition=c, axis=axis, model_name="x/m")
        texts = {s.id: s.input for s in t.dataset}
        if ref is None:
            ref = texts
        assert texts == ref, f"condition {c} has different item text"
    # 6. condition metadata is present but NOT in the model-visible input
    t4 = preference_discovery(condition="level4", axis=axis, model_name="x/m")
    for s in t4.dataset:
        assert "level4" not in s.input and "eh_condition" not in s.input, "condition leaked into prompt"
        assert s.metadata.get("eh_condition") == "level4", "missing hidden condition metadata"

    # 7. non-L6 persona identical; L6 differs ONLY by appended directive
    pref = load_prompt("elara-pref").format_system_prompt(
        model_name="m", x_label=ax.x_label, x_desc_2p=ax.x_desc_2p, y_label=ax.y_label)
    l6 = load_prompt("elara-pref-l6").format_system_prompt(
        model_name="m", x_label=ax.x_label, x_desc_2p=ax.x_desc_2p, y_label=ax.y_label)
    assert pref.strip() in l6, "L6 persona is not (pref + directive)"
    assert "INSTRUCTION:" in l6 and "INSTRUCTION:" not in pref, "L6 directive misplaced"

    # 8. matched model-visible file set: identical names, count, ordering per condition
    for c in CONDITIONS:
        names = sorted(f.name for f in (ENVS / c).iterdir() if f.is_file())
        assert names == MATCHED_FILES, f"condition {c} file set != matched 5: {names}"
    # 9. length parity: no benign filler is trivially short vs the longest active doc
    for c in CONDITIONS:
        lens = [len((ENVS / c / n).read_text().splitlines()) for n in MATCHED_FILES]
        assert min(lens) >= 6 and max(lens) <= 3 * min(lens), f"{c} length imbalance: {lens}"

    print(f"[{axis}] invariants OK: disjoint, 20/20 direction, 20/20 gold, "
          f"identical item text across {len(CONDITIONS)+1} conditions, metadata hidden, "
          f"L6 = pref + directive, matched 5-file set (names/count/order) + length parity")


def manifest(axis):
    ax = AXES[axis]
    files = [
        ax.experiment_path(), ax.screen_path(),
        ROOT / "data/preference/truthfulness_final_60.jsonl",
        ROOT / "data/preference/SELECTION_CRITERION.md",
        ROOT / "src/ehbench/preference_axes.py",
        ROOT / "src/ehbench/scorers/preference_scorer.py",
        ROOT / "src/ehbench/tasks/preference_discovery.py",
        ROOT / "src/ehbench/tools/discover_tools.py",
    ]
    files += sorted((ROOT / "configs/prompts/experiments/agentic-discovery").glob("elara-pref*.yaml"))
    files += sorted((ROOT / "environments/discovery-preference").rglob("*.txt"))
    lines = []
    for f in files:
        h = hashlib.sha256(f.read_bytes()).hexdigest()[:16]
        lines.append(f"{h}  {f.relative_to(ROOT)}")
    out = ROOT / f"data/preference/FREEZE_MANIFEST_{axis}.txt"
    out.write_text("\n".join(lines) + "\n")
    print(f"wrote {out.relative_to(ROOT)} ({len(files)} files hashed)")


if __name__ == "__main__":
    a = sys.argv[1] if len(sys.argv) > 1 else "truthfulness"
    check(a)
    manifest(a)
