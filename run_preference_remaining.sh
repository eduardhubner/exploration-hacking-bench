#!/usr/bin/env bash
# Remaining preference-arm models × both axes (truthfulness, power).
# Mirrors the CTF matched-ladder launcher: per model per axis run
#   screen -> full interleaved block (baseline/c0/shadow/l2/l3/l4/l5) -> L6,
# each into its own log dir. Retry-capped, resumable (skips finished arms),
# a single arm failing does not stop the chain. Matches how gemini-2.5 /
# sonnet-4 were run (model_name left default; epochs 8).
#
#   nohup caffeinate -i bash run_preference_remaining.sh \
#     > logs/pref-contrasts2.out 2>&1 &
set -x
cd "$(dirname "$0")"

EPOCHS=8
FLAGS="--max-retries 5 --attempt-timeout 600 --no-fail-on-error"
PREF=src/ehbench/tasks/preference_discovery.py

_done () { ls "$1"/*.eval >/dev/null 2>&1; }

# $1 model  $2 tag  $3 axis  $4 conn  $5 extra(-M ...)
arm () {
  local M="$1" TAG="$2" AX="$3" CONN="$4" EXTRA="$5"
  local SD="logs/pref-screen-$AX-$TAG" BD="logs/pref-block-$AX-$TAG" LD="logs/pref-l6-$AX-$TAG"
  if ! _done "$SD"; then
    uv run inspect eval "$PREF"@preference_screen -T "axis=$AX" \
      --model "$M" --epochs $EPOCHS --max-connections "$CONN" $EXTRA \
      $FLAGS --display plain --log-dir "$SD"
  fi
  if ! _done "$BD"; then
    uv run inspect eval "$PREF"@preference_discovery_block -T "axis=$AX" \
      --model "$M" --epochs $EPOCHS --max-connections "$CONN" $EXTRA \
      $FLAGS --display plain --log-dir "$BD"
  fi
  if ! _done "$LD"; then
    uv run inspect eval "$PREF"@preference_discovery -T condition=level6 -T "axis=$AX" \
      --model "$M" --epochs $EPOCHS --max-connections "$CONN" $EXTRA \
      $FLAGS --display plain --log-dir "$LD"
  fi
}

# model                                   tag     conn  extra
for AX in truthfulness power; do
  echo "===== [$AX] GLM-5.2 ====="
  arm openai/z-ai/glm-5.2         glm     "$AX" 10 ""
  echo "===== [$AX] Kimi-k3 ====="
  arm openai/moonshotai/kimi-k3   kimi    "$AX" 10 ""
  echo "===== [$AX] GPT-5.6 Sol (reasoning_effort=medium) ====="
  arm openai/openai/gpt-5.6-sol   gptsol  "$AX" 10 "-M reasoning_effort=medium"
  echo "===== [$AX] Opus-4.1 ====="
  arm openai/anthropic/claude-opus-4.1 opus41 "$AX" 10 ""
done
echo PREFERENCE_REMAINING_COMPLETE
