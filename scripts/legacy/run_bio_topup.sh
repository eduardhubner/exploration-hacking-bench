#!/usr/bin/env bash
# Bio top-up (plan §2): additive 40-item block. Default offset 100 / limit 40 ->
# ids 101-140, DISJOINT from the initial offset-0/limit-100 block, appended into
# logs/gen-bio (source_block stays bio_generalization; merge unions by id).
# Includes BASELINE (new items need baseline on them to form matched pairs).
#
# Round 1 (all 5 models):            ./run_bio_topup.sh
# opus-only follow-up rounds (opus is ~40% scoreable under Anthropic's stricter
# moderation, so it needs ~4 rounds to reach 100 pairs; the other 4 clear in 1):
#   MODELS="openai/anthropic/claude-opus-4" OFFSET=140 ./run_bio_topup.sh
#   MODELS="openai/anthropic/claude-opus-4" OFFSET=180 ./run_bio_topup.sh   ... etc
# wmdp-bio pool is 1273 items, so offsets up to ~220 are safe.
set -euo pipefail
PYTHON="${PYTHON:-.venv/bin/python}"
OFFSET="${OFFSET:-100}"; LIMIT="${LIMIT:-40}"

# MODELS override (space-separated) lets follow-up rounds target opus only.
if [ -n "${MODELS:-}" ]; then read -r -a MODELS <<< "$MODELS"; else
MODELS=(
  openai/anthropic/claude-opus-4
  openai/anthropic/claude-sonnet-4
  openai/google/gemini-2.5-pro
  openai/google/gemini-3.1-pro-preview
  openai/z-ai/glm-5.2
); fi
COMMON=( --no-judge --max-tokens 32000 --time-limit 900 )
ST_CONDS=( baseline level2_training_awareness level3_goal_conflict_tm1 level3_goal_conflict_tm2 level4_action_knowledge_tm1 level4_action_knowledge_tm2 level5_desire_nudge_tm1 level5_desire_nudge_tm2 level6_explicit_instruction )
AG_CONDS=( baseline level2 level3-tm1 level3-tm2 level4-tm1 level4-tm2 level5-tm1 level5-tm2 level6-tm1 level6-tm2 )

echo "===== bio top-up: offset $OFFSET limit $LIMIT (ids $((OFFSET+1))-$((OFFSET+LIMIT))) | models: ${MODELS[*]} ====="
for M in "${MODELS[@]}"; do
  echo "----- $M | single_turn | wmdp-bio | offset $OFFSET -----"
  "$PYTHON" run_sweep.py --model "$M" --task single_turn --dataset wmdp-bio \
    "${COMMON[@]}" --log-dir logs/gen-bio --offset "$OFFSET" --limit "$LIMIT" \
    --conditions "${ST_CONDS[@]}"
done
for M in "${MODELS[@]}"; do
  echo "----- $M | agentic | wmdp-bio | offset $OFFSET -----"
  "$PYTHON" run_sweep.py --model "$M" --task agentic --dataset wmdp-bio \
    "${COMMON[@]}" --log-dir logs/gen-bio --offset "$OFFSET" --limit "$LIMIT" \
    --conditions "${AG_CONDS[@]}"
done
echo "===== bio top-up DONE (offset $OFFSET) — re-run pair counts; opus needs OFFSET=$((OFFSET+LIMIT)) ====="
