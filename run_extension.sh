#!/usr/bin/env bash
# =============================================================================
# Confirmatory agentic extension — see docs/extension_plan.md (FROZEN).
#
# STAGED so the budget-risk from point 1 is controllable:
#   ./run_extension.sh smoke    # ~6 episodes (~$1) — end-to-end sanity, logs/ext-smoke
#   ./run_extension.sh gemini   # Stage 1: Gemini-3.1 only, ~600 ep (~$130), logs/ext-v1
#   ./run_extension.sh others   # Stage 2: other 4 models, ~1200 ep (~$250), logs/ext-v1
#   ./run_extension.sh all      # gemini + others in one shot (~$380)
#
# Recommended: smoke -> gemini -> (score + confirm H1 replicates) -> others.
#
# Fresh, disjoint items: HF indices 40+ (sample ids 41+), verified disjoint from
# the discovery set (ids 1-40). Writes RAW transcripts (no judge); score after
# with the frozen Sol judge (see bottom). Includes a fresh agentic BASELINE per
# model — required so each fresh scaffold item has a paired no-framing answer on
# the SAME item for the McNemar C->W.
# =============================================================================
set -euo pipefail

STAGE="${1:-}"
PYTHON="${PYTHON:-.venv/bin/python}"
LOGDIR=logs/ext-v1
COMMON="--task agentic --dataset wmdp-cyber --no-judge --max-tokens 32000 --time-limit 900 --offset 40"

GEMINI=openai/google/gemini-3.1-pro-preview
OTHERS=(
  openai/anthropic/claude-opus-4
  openai/anthropic/claude-sonnet-4
  openai/google/gemini-2.5-pro
  openai/z-ai/glm-5.2
)

run_gemini() {
  echo "===== STAGE 1: $GEMINI — agentic extension (n=100 fresh, ids 41-140) ====="
  $PYTHON run_sweep.py --model "$GEMINI" $COMMON --log-dir "$LOGDIR" --limit 100 \
    --conditions baseline level3-tm1 level3-tm2 level4-tm1 level4-tm2 level5-tm2
}

run_others() {
  echo "===== STAGE 2: other four models — agentic extension (n=60 fresh, ids 41-100) ====="
  for M in "${OTHERS[@]}"; do
    echo "----- $M -----"
    $PYTHON run_sweep.py --model "$M" $COMMON --log-dir "$LOGDIR" --limit 60 \
      --conditions baseline level3-tm1 level3-tm2 level4-tm2 level5-tm2
  done
}

case "$STAGE" in
  smoke)
    echo "===== SMOKE: $GEMINI — 1 episode per new condition (id 41) -> logs/ext-smoke ====="
    $PYTHON run_sweep.py --model "$GEMINI" $COMMON --log-dir logs/ext-smoke --limit 1 \
      --conditions baseline level3-tm1 level3-tm2 level4-tm1 level4-tm2 level5-tm2
    ;;
  gemini) mkdir -p "$LOGDIR"; run_gemini ;;
  others) mkdir -p "$LOGDIR"; run_others ;;
  all)    mkdir -p "$LOGDIR"; run_gemini; run_others ;;
  *)
    echo "usage: ./run_extension.sh {smoke|gemini|others|all}"; exit 1 ;;
esac

echo "===== DONE ($STAGE) ====="
echo "Score with the frozen Sol agentic judge, e.g.:"
echo "  python analysis/score_transcripts.py --log-dirs logs/ext-v1 --out ext_scored_labels.json --dry-run"
