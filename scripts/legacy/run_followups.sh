#!/usr/bin/env bash
# =============================================================================
# Robustness follow-ups — see docs/extension_plan.md §8 (FROZEN).
#   ./run_followups.sh smoke   # 1 episode per new paraphrase cond (~$1), logs/ext2-smoke
#   ./run_followups.sh e1      # E1 paraphrase-robustness, Gemini, ~540 ep, logs/ext2-v1
#   ./run_followups.sh e2      # E2 L2 power-up, Gemini, ~100 ep, logs/ext2-v1
#   ./run_followups.sh all     # e1 + e2
#
# Both are BEHAVIORAL tests (judge-independent) — run with --no-judge; evaluate
# from logs like H1. Cognitive scoring optional/later.
#
# E1: item-matched common block, HF idx 160-219 (ids 161-220, n=60), verified
#     disjoint from discovery (1-40) and extension (41-140). Four wordings per rung
#     (canonical + p1/p2/p3), all paired to the same fresh baseline on the block.
# E2: L2 on ids 41-140 (offset 40), paired against the EXISTING ext-v1 baseline
#     (no new baseline) — exact item-match to the frozen extension baseline.
#
# Long runs: wrap in `caffeinate -is ... | tee logs/ext2-run.out`. See extension notes.
# =============================================================================
set -euo pipefail

STAGE="${1:-}"
PYTHON="${PYTHON:-.venv/bin/python}"
LOGDIR=logs/ext2-v1
GEMINI=openai/google/gemini-3.1-pro-preview
COMMON="--model $GEMINI --task agentic --dataset wmdp-cyber --no-judge --max-tokens 32000 --time-limit 900"

run_e1() {
  echo "===== E1: paraphrase-robustness — Gemini, common block ids 161-220 (n=60) ====="
  $PYTHON run_sweep.py $COMMON --log-dir "$LOGDIR" --offset 160 --limit 60 \
    --conditions baseline \
                 level3-tm1 level4-tm1 \
                 level3-tm1-p1 level3-tm1-p2 level3-tm1-p3 \
                 level4-tm1-p1 level4-tm1-p2 level4-tm1-p3
}

run_e2() {
  echo "===== E2: L2 power-up — Gemini level2 on ids 41-140 (baseline reused from ext-v1) ====="
  $PYTHON run_sweep.py $COMMON --log-dir "$LOGDIR" --offset 40 --limit 100 \
    --conditions level2
}

case "$STAGE" in
  smoke)
    echo "===== SMOKE: 1 episode per new paraphrase condition -> logs/ext2-smoke ====="
    $PYTHON run_sweep.py $COMMON --log-dir logs/ext2-smoke --offset 160 --limit 1 \
      --conditions level3-tm1-p1 level3-tm1-p2 level3-tm1-p3 level4-tm1-p1 level4-tm1-p2 level4-tm1-p3
    ;;
  e1)  mkdir -p "$LOGDIR"; run_e1 ;;
  e2)  mkdir -p "$LOGDIR"; run_e2 ;;
  all) mkdir -p "$LOGDIR"; run_e1; run_e2 ;;
  *)   echo "usage: ./run_followups.sh {smoke|e1|e2|all}"; exit 1 ;;
esac

echo "===== DONE ($STAGE) ====="
