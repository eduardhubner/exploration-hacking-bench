#!/usr/bin/env bash
# Overnight: strength-MATCHED arms (c0_matched + l4_matched) for contrast models
# on InterCode, + a Cybench-matched robustness arm for Gemini.
#
# Launch:
#   nohup caffeinate -i bash agentic_ctf/run_matched_overnight.sh \
#     > logs/matched-overnight.out 2>&1 &
#   tail -f logs/matched-overnight.out
#
# Sequential on purpose (the Docker VM can't parallelize these). Jobs are
# independent: a failure logs and the chain continues (no `set -e`). InterCode
# contrasts run FIRST (cheap, reliable, no big images); Cybench runs LAST so a
# disk/image failure there cannot take down the contrast results.
#
# Design notes:
# - Each contrast model gets its OWN S_m (>=6/8) from an a=1, 8-epoch screen over
#   the frozen 54 (except Opus, already screened -> SM_OPUS reused).
# - Matched arms use `intercode_eh_strong` (neutral persona), run as SEPARATE
#   c0/l4 arms to mirror the Gemini matched run they are compared against.
# - Cybench reliable set is SEEDED FROM THE 3-EPOCH PILOTS (11 challenges at 3/3),
#   a separate prior run used as the screen; c0/l4_matched then run at 8 epochs.
set -x
cd "$(dirname "$0")/.."   # repo root

IDS54="0,2,3,5,8,10,12,13,15,44,45,46,47,48,49,50,51,52,53,55,56,58,59,61,64,65,67,68,69,70,71,72,74,75,76,77,78,79,80,81,82,83,84,85,86,90,91,92,93,94,96,97,98,99"
SM_OPUS="0,2,3,5,8,10,13,44,45,46,47,48,49,50,51,52,53,58,61,64,65,67,68,69,71,72,74,75,76,77,78,79,80,81,82,83,84,90,91,92,93,94,96,97,98,99"
EPOCHS=8
# Cybench reliable set: all 19 challenges Gemini EVER solved in the 3-epoch pilots
# (pre-specified from separate pilot data). The 8-epoch c0_matched arm re-measures
# baseline capability and doubles as the pre-declared reliability sensitivity
# filter (restrict to c0>=X/8) — we do NOT re-select the set on c0 (no double-dip).
CYBER_SM="back_to_the_past,crushing,delulu,dynastic,eval_me,flag_command,it_has_begun,labyrinth_linguist,lootstash,missingbits,packedaway,partial_tenacity,permuted,primary_knowledge,shuffled_aes,skilift,slcg,unbreakable,urgent"

STRONG="src/ehbench/tasks/intercode_eh_strong.py@intercode_eh_strong"
SCREEN="inspect_evals/gdm_intercode_ctf"
CYBER="src/ehbench/tasks/cybench_eh.py@cybench_eh"

# Reliability flags (the fix for the overnight hang): --max-retries defaults to
# UNLIMITED, so one 502'ing sample retried forever and blocked the whole chain.
# Cap retries, abandon any attempt stuck >10min, and let the eval COMPLETE with a
# dead sample recorded as an error (excluded as non-scoreable per PROTOCOL's
# missingness taxonomy) instead of failing/hanging.
FLAGS="--max-retries 5 --attempt-timeout 600 --no-fail-on-error"

# Skip a job whose log dir already holds a finished .eval — makes the chain
# RESUMABLE (e.g. Opus c0_matched already completed before the hang; don't redo it).
_done () {  # $1 log-dir
  ls "$1"/*.eval >/dev/null 2>&1
}

# --- matched arms (both conditions) for one model, given its S_m ------------
run_matched () {  # $1 model  $2 conn  $3 tag  $4 ids
  for cond in c0_matched l4_matched; do
    if _done "logs/imatch-$3-$cond"; then echo "### skip logs/imatch-$3-$cond (done)"; continue; fi
    uv run inspect eval "$STRONG" \
      -T "condition=$cond" -T "sample_ids=[$4]" \
      --model "$1" --epochs $EPOCHS --max-samples 12 --max-connections "$2" \
      $FLAGS --display plain --log-dir "logs/imatch-$3-$cond"
  done
}

# --- screen a fresh model at a=1, then derive S_m and run matched arms ------
screen_then_matched () {  # $1 model  $2 conn  $3 tag
  if _done "logs/screen-$3"; then echo "### skip screen-$3 (done)"; else
  uv run inspect eval "$SCREEN" \
    --model "$1" --epochs $EPOCHS --max-samples 12 --max-connections "$2" \
    -T max_attempts=1 --sample-id "$IDS54" \
    $FLAGS --display plain --log-dir "logs/screen-$3"
  fi
  local SM
  SM=$(uv run python agentic_ctf/sm_from_screen.py "logs/screen-$3")
  echo "### $3 S_m = [$SM]"
  if [ -z "$SM" ]; then echo "### $3 EMPTY S_m — skipping matched arms"; return; fi
  run_matched "$1" "$2" "$3" "$SM"
}

echo "=================== 1) OPUS (already screened) ==================="
run_matched  openai/anthropic/claude-opus-4  6  opus  "$SM_OPUS"

echo "=================== 2) GLM-5.2 ==================="
screen_then_matched  openai/z-ai/glm-5.2               6  glm

echo "=================== 3) GPT-5.6 Sol ==================="
screen_then_matched  openai/openai/gpt-5.6-sol         6  gptsol

echo "=================== 4) Kimi-k3 ==================="
screen_then_matched  openai/moonshotai/kimi-k3           6  kimi

echo "=================== 5) Gemini-2.5 Pro ==================="
screen_then_matched  openai/google/gemini-2.5-pro        8  gemini25

echo "=================== 6) Sonnet-4.5 ==================="
screen_then_matched  openai/anthropic/claude-sonnet-4.5  6  sonnet45

echo "=================== 7) CYBENCH-matched (Gemini, pilot-seeded S_m) ==================="
export CYBENCH_ACKNOWLEDGE_RISKS=1
# The InterCode jobs are done here, so their images/containers are unused. Reclaim
# everything not currently in use so Cybench's ~40GB of images has room (this is
# what was missing before). Inspect tears down each episode's sandbox itself; this
# clears stopped containers, dangling+unused images, networks, and build cache.
echo "### docker BEFORE cleanup:"; docker system df; df -h / | tail -1
docker container prune -f   >/dev/null 2>&1 || true
docker image prune -a -f    >/dev/null 2>&1 || true
docker builder prune -a -f  >/dev/null 2>&1 || true
docker volume prune -f      >/dev/null 2>&1 || true
echo "### docker AFTER cleanup:"; docker system df; df -h / | tail -1
FREE_GB=$(df -g / | awk 'NR==2{print $4}')
echo "### free disk: ${FREE_GB} GB"
if [ "${FREE_GB:-0}" -lt 45 ]; then
  echo "### WARNING: <45GB free — Cybench image pulls may fail. Running anyway; watch disk."
fi
for cond in c0_matched l4_matched; do
  if _done "logs/cymatch-gemini-$cond"; then echo "### skip cymatch-gemini-$cond (done)"; continue; fi
  uv run inspect eval "$CYBER" \
    -T "condition=$cond" -T "eval_names=[$CYBER_SM]" -T variant_names=hard \
    --model openai/google/gemini-3.1-pro-preview \
    --epochs $EPOCHS --max-samples 6 --max-connections 8 \
    $FLAGS --display plain --log-dir "logs/cymatch-gemini-$cond"
done

echo "OVERNIGHT MATCHED CHAIN COMPLETE"
