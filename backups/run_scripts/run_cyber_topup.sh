#!/usr/bin/env bash
# Cyber top-up (plan §2) — GENERATED from verified disjoint offset plan (analysis/... dry-run).
# Fills each under-target cyber cell up to ids 1..100 using ONLY item ranges it has
# never run (front-fill 1-40 for extension-only cells, append 41-100 / 51-100 for
# discovery/context cells). Every block verified disjoint from existing ids = NO overwrite.
# Baseline already covers 1..100 for all cells, so only scaffolds are (re)run.
# Writes to logs/gen-cyber-topup (source_block: cyber_completion) — frozen confirmatory
# blocks (main-v*/ext-v*) are untouched; gemini-3.1 headline cells deliberately excluded.
set -euo pipefail
PYTHON="${PYTHON:-.venv/bin/python}"
LOGDIR=logs/gen-cyber-topup
mkdir -p "$LOGDIR"; printf "%s\n" cyber_completion > "$LOGDIR/_source_block.txt"
COMMON=( --no-judge --max-tokens 32000 --time-limit 900 )

echo "----- claude-opus-4 | agentic | offset 0 limit 40 -----"
"$PYTHON" run_sweep.py --model openai/anthropic/claude-opus-4 --task agentic --dataset wmdp-cyber \
  "${COMMON[@]}" --log-dir "$LOGDIR" --offset 0 --limit 40 --conditions level3-tm1 level3-tm2 level4-tm2 level5-tm2

echo "----- claude-opus-4 | agentic | offset 40 limit 60 -----"
"$PYTHON" run_sweep.py --model openai/anthropic/claude-opus-4 --task agentic --dataset wmdp-cyber \
  "${COMMON[@]}" --log-dir "$LOGDIR" --offset 40 --limit 60 --conditions level2 level4-tm1 level5-tm1

echo "----- claude-sonnet-4 | agentic | offset 0 limit 40 -----"
"$PYTHON" run_sweep.py --model openai/anthropic/claude-sonnet-4 --task agentic --dataset wmdp-cyber \
  "${COMMON[@]}" --log-dir "$LOGDIR" --offset 0 --limit 40 --conditions level3-tm1 level3-tm2 level4-tm2 level5-tm2

echo "----- claude-sonnet-4 | agentic | offset 40 limit 60 -----"
"$PYTHON" run_sweep.py --model openai/anthropic/claude-sonnet-4 --task agentic --dataset wmdp-cyber \
  "${COMMON[@]}" --log-dir "$LOGDIR" --offset 40 --limit 60 --conditions level2 level4-tm1 level5-tm1

echo "----- gemini-2.5-pro | agentic | offset 0 limit 40 -----"
"$PYTHON" run_sweep.py --model openai/google/gemini-2.5-pro --task agentic --dataset wmdp-cyber \
  "${COMMON[@]}" --log-dir "$LOGDIR" --offset 0 --limit 40 --conditions level3-tm1 level3-tm2 level4-tm2 level5-tm2

echo "----- gemini-2.5-pro | agentic | offset 40 limit 60 -----"
"$PYTHON" run_sweep.py --model openai/google/gemini-2.5-pro --task agentic --dataset wmdp-cyber \
  "${COMMON[@]}" --log-dir "$LOGDIR" --offset 40 --limit 60 --conditions level2 level4-tm1 level5-tm1

echo "----- gemini-3.1-pro-preview | agentic | offset 40 limit 60 -----"
"$PYTHON" run_sweep.py --model openai/google/gemini-3.1-pro-preview --task agentic --dataset wmdp-cyber \
  "${COMMON[@]}" --log-dir "$LOGDIR" --offset 40 --limit 60 --conditions level5-tm1

echo "----- glm-5.2 | agentic | offset 0 limit 40 -----"
"$PYTHON" run_sweep.py --model openai/z-ai/glm-5.2 --task agentic --dataset wmdp-cyber \
  "${COMMON[@]}" --log-dir "$LOGDIR" --offset 0 --limit 40 --conditions level3-tm1 level3-tm2 level4-tm2 level5-tm2

echo "----- glm-5.2 | agentic | offset 40 limit 60 -----"
"$PYTHON" run_sweep.py --model openai/z-ai/glm-5.2 --task agentic --dataset wmdp-cyber \
  "${COMMON[@]}" --log-dir "$LOGDIR" --offset 40 --limit 60 --conditions level2 level4-tm1 level5-tm1

echo "----- claude-opus-4 | single_turn | offset 50 limit 50 -----"
"$PYTHON" run_sweep.py --model openai/anthropic/claude-opus-4 --task single_turn --dataset wmdp-cyber \
  "${COMMON[@]}" --log-dir "$LOGDIR" --offset 50 --limit 50 --conditions level2_training_awareness level3_goal_conflict_tm1 level3_goal_conflict_tm2 level6_explicit_instruction

echo "----- claude-sonnet-4 | single_turn | offset 50 limit 50 -----"
"$PYTHON" run_sweep.py --model openai/anthropic/claude-sonnet-4 --task single_turn --dataset wmdp-cyber \
  "${COMMON[@]}" --log-dir "$LOGDIR" --offset 50 --limit 50 --conditions level2_training_awareness level3_goal_conflict_tm1 level3_goal_conflict_tm2 level6_explicit_instruction

echo "----- gemini-2.5-pro | single_turn | offset 50 limit 50 -----"
"$PYTHON" run_sweep.py --model openai/google/gemini-2.5-pro --task single_turn --dataset wmdp-cyber \
  "${COMMON[@]}" --log-dir "$LOGDIR" --offset 50 --limit 50 --conditions level2_training_awareness level3_goal_conflict_tm1 level3_goal_conflict_tm2 level6_explicit_instruction

echo "----- gemini-3.1-pro-preview | single_turn | offset 50 limit 50 -----"
"$PYTHON" run_sweep.py --model openai/google/gemini-3.1-pro-preview --task single_turn --dataset wmdp-cyber \
  "${COMMON[@]}" --log-dir "$LOGDIR" --offset 50 --limit 50 --conditions level2_training_awareness level3_goal_conflict_tm1 level3_goal_conflict_tm2 level6_explicit_instruction

echo "----- glm-5.2 | single_turn | offset 50 limit 50 -----"
"$PYTHON" run_sweep.py --model openai/z-ai/glm-5.2 --task single_turn --dataset wmdp-cyber \
  "${COMMON[@]}" --log-dir "$LOGDIR" --offset 50 --limit 50 --conditions level2_training_awareness level3_goal_conflict_tm1 level3_goal_conflict_tm2 level6_explicit_instruction

echo "===== cyber top-up DONE — re-run pair counts; any cell <100 pairs gets a 2nd block ====="
