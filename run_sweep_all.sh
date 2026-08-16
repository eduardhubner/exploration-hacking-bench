#!/usr/bin/env bash
MODELS=(
  openai/anthropic/claude-opus-4
  openai/anthropic/claude-sonnet-4
  openai/google/gemini-2.5-pro
  openai/google/gemini-3.1-pro-preview
  openai/z-ai/glm-5.2
)
C="--task single_turn --dataset wmdp-cyber --no-judge --max-tokens 32000 --time-limit 900 --log-dir logs/main-v2"

for M in "${MODELS[@]}"; do
  echo "===== $M : single-turn ====="
  # A. append q51-100 to the n=100 cells (offset — no re-run)
  python run_sweep.py --model "$M" $C --offset 50 --limit 50 \
    --conditions baseline level4_action_knowledge_tm1 level4_action_knowledge_tm2 level5_desire_nudge_tm1
  # B. fresh n=50 context cells
  python run_sweep.py --model "$M" $C --limit 50 \
    --conditions level2_training_awareness level3_goal_conflict_tm2
  # C. fresh n=100 nudge cell
  python run_sweep.py --model "$M" $C --limit 100 --conditions level5_desire_nudge_tm2
  # D. agentic fresh n=40 (neutral baseline + L2/L4/L5)
  python run_sweep.py --model "$M" --task agentic --dataset wmdp-cyber --no-judge \
    --max-tokens 32000 --time-limit 900 --log-dir logs/main-v2 --limit 40 \
    --conditions baseline level2 level4-tm1 level5-tm1
done

# E. sequential footnote — 2 models, higher time-limit
for M in openai/anthropic/claude-sonnet-4 openai/google/gemini-3.1-pro-preview; do
  echo "===== $M : sequential ====="
  python run_sweep.py --model "$M" --task sequential --dataset wmdp-cyber --no-judge \
    --max-tokens 32000 --time-limit 1800 --log-dir logs/main-v2 --limit 10 --questions-per-session 10 \
    --conditions baseline level2_training_awareness level4_action_knowledge_tm1 level6_explicit_instruction
done
echo "===== ALL DONE ====="
