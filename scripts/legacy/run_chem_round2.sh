#!/usr/bin/env bash
# Chem top-up ROUND 2 (plan §2): targeted second 40-block (offset 140 -> ids 141-180)
# for the only 4 cells still <100 pairs after round 1. Baseline included (new items
# need it for pairing). Appends into logs/gen-chem. Disjoint from ids 1-140.
set -euo pipefail
PYTHON="${PYTHON:-.venv/bin/python}"
COMMON=( --no-judge --max-tokens 32000 --time-limit 900 --log-dir logs/gen-chem --offset 140 --limit 40 )

echo "----- opus single_turn chem stragglers (L4·TM1=75, L4·TM2=95, L3·TM1=97) -----"
"$PYTHON" run_sweep.py --model openai/anthropic/claude-opus-4 --task single_turn --dataset wmdp-chem \
  "${COMMON[@]}" --conditions baseline level3_goal_conflict_tm1 level4_action_knowledge_tm1 level4_action_knowledge_tm2

echo "----- sonnet agentic chem straggler (L5·TM1=75) -----"
"$PYTHON" run_sweep.py --model openai/anthropic/claude-sonnet-4 --task agentic --dataset wmdp-chem \
  "${COMMON[@]}" --conditions baseline level5-tm1

echo "===== chem round-2 DONE — all chem cells should now be >=100 pairs ====="
