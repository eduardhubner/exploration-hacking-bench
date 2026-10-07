#!/usr/bin/env bash
# Overnight: Stage B (Gemini, Opus) + baselines (Sonnet, Gemini2.5, GLM, Kimi, GPT-5.6 Sol).
# Launch:  nohup caffeinate -i bash agentic_ctf/run_overnight.sh > logs/overnight.out 2>&1 &
# Sequential on purpose — the 7.65 GB / 10-CPU Docker VM can't run these in parallel.
# Jobs are independent; a failure does not stop the rest. Watch logs/overnight.out.
set -x
cd "$(dirname "$0")/.."   # repo root

SM_GEM="0,2,3,5,8,10,13,44,45,46,47,48,49,50,51,52,53,58,61,64,65,67,68,69,71,72,74,75,76,77,78,79,80,81,82,83,84,86,90,91,92,93,94,96,97,98,99"
SM_OPUS="0,2,3,5,8,10,13,44,45,46,47,48,49,50,51,52,53,58,61,64,65,67,68,69,71,72,74,75,76,77,78,79,80,81,82,83,84,90,91,92,93,94,96,97,98,99"
IDS54="0,2,3,5,8,10,12,13,15,44,45,46,47,48,49,50,51,52,53,55,56,58,59,61,64,65,67,68,69,70,71,72,74,75,76,77,78,79,80,81,82,83,84,85,86,90,91,92,93,94,96,97,98,99"
EPOCHS=8

run_block () {   # $1 model  $2 conn  $3 tag  $4 ids
  uv run inspect eval src/ehbench/tasks/intercode_eh.py@intercode_eh_block \
    -T "sample_ids=[$4]" --model "$1" --epochs $EPOCHS --max-samples 12 --max-connections "$2" \
    --display plain --log-dir "logs/stageB-$3-block"
  uv run inspect eval src/ehbench/tasks/intercode_eh.py@intercode_eh \
    -T condition=l6_tm1 -T "sample_ids=[$4]" --model "$1" --epochs $EPOCHS --max-samples 12 \
    --max-connections "$2" --display plain --log-dir "logs/stageB-$3-l6"
}
run_screen () { # $1 model  $2 conn  $3 tag
  uv run inspect eval inspect_evals/gdm_intercode_ctf \
    --model "$1" --epochs $EPOCHS --max-samples 12 --max-connections "$2" -T max_attempts=1 \
    --sample-id "$IDS54" --display plain --log-dir "logs/intercode-screen-$3"
}

# ---- Stage B (headline first; baselines already screened) ----
run_block  openai/google/gemini-3.1-pro-preview  8  gemini  "$SM_GEM"
run_block  openai/anthropic/claude-opus-4          6  opus    "$SM_OPUS"

# ---- remaining baselines (a=1 capability screens) ----
run_screen openai/anthropic/claude-sonnet-4        6  sonnet
run_screen openai/google/gemini-2.5-pro           8  gemini25
run_screen openai/z-ai/glm-5.2                      6  glm
run_screen openai/moonshotai/kimi-k3-20260715      6  kimi
run_screen openai/openai/gpt-5.6-sol               6  gptsol

echo "OVERNIGHT CHAIN COMPLETE"
