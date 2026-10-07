#!/usr/bin/env bash
# Re-run the GPT-5.6-Sol arms that crashed in both main chains because
# reasoning_effort was passed as a client arg (-M) instead of the generate
# flag. Correct flag: --reasoning-effort medium. Same log dirs as the main
# scripts, so analysis treats these as the gptsol arms. Resumable.
#
# Run this ONLY AFTER both main chains have finished (or at least after the
# CTF chain is past GPT-Sol), so it doesn't race the doomed gptsol attempt
# in run_ctf_matched_ladder.sh writing to the same dirs.
#
#   nohup caffeinate -i bash run_gptsol_fix.sh > logs/gptsol-fix.out 2>&1 &
set -x
cd "$(dirname "$0")"

M=openai/openai/gpt-5.6-sol
RE="--reasoning-effort medium"
EPOCHS=8
FLAGS="--max-retries 5 --attempt-timeout 600 --no-fail-on-error"
STRONG=src/ehbench/tasks/intercode_eh_strong.py
SCREEN=inspect_evals/gdm_intercode_ctf
PREF=src/ehbench/tasks/preference_discovery.py
IDS54="0,2,3,5,8,10,12,13,15,44,45,46,47,48,49,50,51,52,53,55,56,58,59,61,64,65,67,68,69,70,71,72,74,75,76,77,78,79,80,81,82,83,84,85,86,90,91,92,93,94,96,97,98,99"
FULL="c0_matched,shadow_matched,l2_matched,l3_matched,l4_matched,l5_matched"

_done () { ls "$1"/*.eval >/dev/null 2>&1; }

# ---- CTF full matched ladder (screen -> block -> l6) ----
SDIR=logs/screen-gptsol-med
if ! _done "$SDIR"; then
  uv run inspect eval "$SCREEN" --model "$M" --epochs $EPOCHS --max-samples 12 \
    --max-connections 6 -T max_attempts=1 --sample-id "$IDS54" $RE \
    $FLAGS --display plain --log-dir "$SDIR"
fi
SM=$(uv run python agentic_ctf/sm_from_screen.py "$SDIR")
echo "### gptsol S_m = [$SM]"
if [ -n "$SM" ]; then
  if ! _done logs/ladder-gptsol-block; then
    uv run inspect eval "$STRONG"@intercode_eh_strong_block -T "sample_ids=[$SM]" \
      -T "conditions=[$FULL]" --model "$M" --epochs $EPOCHS --max-samples 12 \
      --max-connections 6 $RE $FLAGS --display plain --log-dir logs/ladder-gptsol-block
  fi
  if ! _done logs/ladder-gptsol-l6; then
    uv run inspect eval "$STRONG"@intercode_eh_strong -T condition=l6_matched -T "sample_ids=[$SM]" \
      --model "$M" --epochs $EPOCHS --max-samples 12 --max-connections 6 $RE \
      $FLAGS --display plain --log-dir logs/ladder-gptsol-l6
  fi
fi

# ---- Preference both axes (screen -> block -> l6) ----
for AX in truthfulness power; do
  SD=logs/pref-screen-$AX-gptsol BD=logs/pref-block-$AX-gptsol LD=logs/pref-l6-$AX-gptsol
  if ! _done "$SD"; then
    uv run inspect eval "$PREF"@preference_screen -T "axis=$AX" --model "$M" \
      --epochs $EPOCHS --max-connections 10 $RE $FLAGS --display plain --log-dir "$SD"
  fi
  if ! _done "$BD"; then
    uv run inspect eval "$PREF"@preference_discovery_block -T "axis=$AX" --model "$M" \
      --epochs $EPOCHS --max-connections 10 $RE $FLAGS --display plain --log-dir "$BD"
  fi
  if ! _done "$LD"; then
    uv run inspect eval "$PREF"@preference_discovery -T condition=level6 -T "axis=$AX" --model "$M" \
      --epochs $EPOCHS --max-connections 10 $RE $FLAGS --display plain --log-dir "$LD"
  fi
done
echo GPTSOL_FIX_COMPLETE
