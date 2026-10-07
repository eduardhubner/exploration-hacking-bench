#!/usr/bin/env bash
# Full MATCHED ladder (c0/shadow/l2/l3/l4/l5 interleaved + l6 separate) across all
# models. Per model: reuse its screen-derived S_m if present, else screen at a=1;
# then run the matched block + l6_matched. Retry-capped, resumable (skips finished
# arms), failures don't stop the chain.
#
#   nohup caffeinate -i bash agentic_ctf/run_ctf_matched_ladder.sh \
#     > logs/ctf-ladder.out 2>&1 &
set -x
cd "$(dirname "$0")/.."

IDS54="0,2,3,5,8,10,12,13,15,44,45,46,47,48,49,50,51,52,53,55,56,58,59,61,64,65,67,68,69,70,71,72,74,75,76,77,78,79,80,81,82,83,84,85,86,90,91,92,93,94,96,97,98,99"
EPOCHS=8
FLAGS="--max-retries 5 --attempt-timeout 600 --no-fail-on-error"
STRONG=src/ehbench/tasks/intercode_eh_strong.py
SCREEN=inspect_evals/gdm_intercode_ctf

_done () { ls "$1"/*.eval >/dev/null 2>&1; }

# $1 model  $2 conn  $3 tag  $4 screen-dir  $5 conditions(block)  $6 extra(-M ...)
# $5 is the matched-ladder conditions to run in the block. Models that already have
# valid imatch c0/l4 pass only the MISSING rungs (shadow/l2/l3/l5); models that are
# new or changed (gptsol@medium, sonnet4, opus41) pass the full set incl c0/l4.
ladder () {
  local M="$1" CONN="$2" TAG="$3" SDIR="$4" CONDS="$5" EXTRA="$6"
  if ! _done "$SDIR"; then
    uv run inspect eval "$SCREEN" --model "$M" --epochs $EPOCHS --max-samples 12 \
      --max-connections "$CONN" -T max_attempts=1 --sample-id "$IDS54" $EXTRA \
      $FLAGS --display plain --log-dir "$SDIR"
  fi
  local SM; SM=$(uv run python agentic_ctf/sm_from_screen.py "$SDIR")
  echo "### $TAG S_m = [$SM]  block-conditions=[$CONDS]"
  [ -z "$SM" ] && { echo "### $TAG EMPTY S_m — skip"; return; }
  if ! _done "logs/ladder-$TAG-block"; then
    uv run inspect eval "$STRONG"@intercode_eh_strong_block -T "sample_ids=[$SM]" \
      -T "conditions=[$CONDS]" --model "$M" --epochs $EPOCHS --max-samples 12 \
      --max-connections "$CONN" $EXTRA $FLAGS --display plain --log-dir "logs/ladder-$TAG-block"
  fi
  if ! _done "logs/ladder-$TAG-l6"; then
    uv run inspect eval "$STRONG"@intercode_eh_strong -T condition=l6_matched -T "sample_ids=[$SM]" \
      --model "$M" --epochs $EPOCHS --max-samples 12 --max-connections "$CONN" $EXTRA \
      $FLAGS --display plain --log-dir "logs/ladder-$TAG-l6"
  fi
}

MISSING="shadow_matched,l2_matched,l3_matched,l5_matched"                       # reuse imatch c0/l4
FULL="c0_matched,shadow_matched,l2_matched,l3_matched,l4_matched,l5_matched"    # new/changed models

echo ===== Gemini-3.1 =====;  ladder openai/google/gemini-3.1-pro-preview 8 gemini31 logs/intercode-screen-gemini "$MISSING" ""
echo ===== Gemini-2.5 =====;  ladder openai/google/gemini-2.5-pro         8 gemini25 logs/screen-gemini25 "$MISSING" ""
echo ===== GLM-5.2   =====;   ladder openai/z-ai/glm-5.2                  6 glm      logs/screen-glm "$MISSING" ""
echo ===== Kimi-k3   =====;   ladder openai/moonshotai/kimi-k3            6 kimi     logs/screen-kimi "$MISSING" ""
echo ===== GPT-5.6 Sol =====; ladder openai/openai/gpt-5.6-sol            6 gptsol   logs/screen-gptsol-med "$FULL" "-M reasoning_effort=medium"
echo ===== Sonnet-4  =====;   ladder openai/anthropic/claude-sonnet-4     6 sonnet4  logs/screen-sonnet4 "$FULL" ""
echo ===== Opus-4.1  =====;   ladder openai/anthropic/claude-opus-4.1     6 opus41   logs/screen-opus41 "$FULL" ""
echo CTF_MATCHED_LADDER_COMPLETE
