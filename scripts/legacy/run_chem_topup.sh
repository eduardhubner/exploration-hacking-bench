#!/usr/bin/env bash
# Chem top-up (plan §2): additive 40-item block. Default offset 100 / limit 40 ->
# ids 101-140, DISJOINT from the initial offset-0/limit-100 block, appended into
# logs/gen-chem (source_block stays chem_generalization; merge unions by id).
#
# Includes BASELINE: unlike cyber (whose baseline already covers ids 1-100), chem's
# new items 101-140 are fresh, so baseline must run on them too to form matched pairs.
#
# Standalone by design: does NOT edit run_generality.sh (bio is mid-execution of it).
# Second round for stragglers (heavily-filtered opus cells): OFFSET=140 ./run_chem_topup.sh
set -euo pipefail
PYTHON="${PYTHON:-.venv/bin/python}"
OFFSET="${OFFSET:-100}"; LIMIT="${LIMIT:-40}"

MODELS=(
  openai/anthropic/claude-opus-4
  openai/anthropic/claude-sonnet-4
  openai/google/gemini-2.5-pro
  openai/google/gemini-3.1-pro-preview
  openai/z-ai/glm-5.2
)
COMMON=( --no-judge --max-tokens 32000 --time-limit 900 )
ST_CONDS=( baseline level2_training_awareness level3_goal_conflict_tm1 level3_goal_conflict_tm2 level4_action_knowledge_tm1 level4_action_knowledge_tm2 level5_desire_nudge_tm1 level5_desire_nudge_tm2 level6_explicit_instruction )
AG_CONDS=( baseline level2 level3-tm1 level3-tm2 level4-tm1 level4-tm2 level5-tm1 level5-tm2 level6-tm1 level6-tm2 )

echo "===== chem top-up: offset $OFFSET limit $LIMIT (ids $((OFFSET+1))-$((OFFSET+LIMIT))) -> logs/gen-chem ====="
for M in "${MODELS[@]}"; do
  echo "----- $M | single_turn | wmdp-chem | offset $OFFSET -----"
  "$PYTHON" run_sweep.py --model "$M" --task single_turn --dataset wmdp-chem \
    "${COMMON[@]}" --log-dir logs/gen-chem --offset "$OFFSET" --limit "$LIMIT" \
    --conditions "${ST_CONDS[@]}"
done
for M in "${MODELS[@]}"; do
  echo "----- $M | agentic | wmdp-chem | offset $OFFSET -----"
  "$PYTHON" run_sweep.py --model "$M" --task agentic --dataset wmdp-chem \
    "${COMMON[@]}" --log-dir logs/gen-chem --offset "$OFFSET" --limit "$LIMIT" \
    --conditions "${AG_CONDS[@]}"
done
echo "===== chem top-up DONE — re-run pair counts; cells still <100 need OFFSET=$((OFFSET+LIMIT)) ./run_chem_topup.sh ====="
