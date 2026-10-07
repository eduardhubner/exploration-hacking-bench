"""Freeze the preference-judge definitions + parsers as versioned artifacts before
any calibration. Copies the two prompt YAMLs and parsers.py into
data/preference/judge_calibration/frozen/ and writes MANIFEST.txt with SHA-256s.

Re-running after a change will show a hash mismatch vs the committed MANIFEST, which
is the signal that a prompt/parser was modified after freezing.

    python analysis/preference_judge/freeze_judges.py [--version v1]
"""
from __future__ import annotations
import argparse, hashlib, shutil, datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SRC = {
    "judge_preference_mechanism.yaml": ROOT / "configs/prompts/judges/judge_preference.yaml",
    "judge_preference_semantics.yaml": ROOT / "configs/prompts/judges/judge_preference_semantics.yaml",
    "parsers.py": ROOT / "analysis/preference_judge/parsers.py",
}
# also hash (but do not need to copy) the frozen boundary suites for provenance
ALSO_HASH = {
    "boundary_mechanism.jsonl": ROOT / "data/preference/judge_calibration/boundary_mechanism.jsonl",
    "boundary_semantics.jsonl": ROOT / "data/preference/judge_calibration/boundary_semantics.jsonl",
}
OUT = ROOT / "data/preference/judge_calibration/frozen"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="v1")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    lines = [f"# Preference-judge FREEZE MANIFEST  version={args.version}",
             f"# frozen_at={dt.datetime.now().isoformat(timespec='seconds')}", ""]
    for name, src in SRC.items():
        if not src.exists():
            raise SystemExit(f"missing source: {src}")
        dst = OUT / f"{Path(name).stem}.{args.version}{Path(name).suffix}"
        shutil.copyfile(src, dst)
        lines.append(f"{sha(src)}  {name}  (copied -> {dst.relative_to(ROOT)})")
    lines.append("")
    for name, src in ALSO_HASH.items():
        if src.exists():
            lines.append(f"{sha(src)}  {name}  (hashed only)")
    (OUT / "MANIFEST.txt").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))
    print(f"\nwrote {OUT/'MANIFEST.txt'}")


if __name__ == "__main__":
    main()
