#!/usr/bin/env bash
# =============================================================================
# Generality & completeness runs — see docs/internal/generality_plan.md (FROZEN).
#
#   ./run_generality.sh smoke {cyber|chem|bio}   # n=1 config sanity (baseline + agentic L6)
#   ./run_generality.sh cyber-l6                 # agentic L6 (+fresh baseline), all models
#   ./run_generality.sh seq-cyber                # sequential completion, all models, full ladder
#   ./run_generality.sh chem                     # fresh single_turn + agentic, all models
#   ./run_generality.sh bio                      # fresh single_turn + agentic, all models
#
# BEHAVIORAL-only (--no-judge); score the overlay afterward with score_transcripts.py.
#
# PROVENANCE (plan section 8): each stage writes a machine-readable marker
# `_source_block.txt` into its log dir (not just the dir name). pair_report.py reads
# that marker, keyed against a frozen mapping, and FAILS on any log with no
# recognized provenance. Confirmatory/discovery blocks (main-v*/ext-v*) are never
# combined into the frozen inferential tests.
#
# SEQUENTIAL --limit: verified to mean NUMBER OF SESSIONS (sequential_mcq groups the
# dataset into questions_per_session-sized sessions, then takes sessions[:limit]).
# So `--limit 18 --questions-per-session 10` = 18 ten-question sessions.
#
# TOP-UPS (plan section 2) are NOT hardcoded — they depend on realized scoreable-pair
# counts. Every cell's initial block is uniform limit 100 (offset 0). After scoring,
# analysis/pair_report.py finds each under-target cell's next UNUSED item range
# (continuing from offset 100, never restarting at 0) and emits outcome-blind 40-item
# top-up commands. Bio's higher expected filtering is handled by more top-up rounds,
# not by a bigger initial block — so its filter rate is measured on the first 100.
#
# Wrap long runs: caffeinate -is ./run_generality.sh <stage> 2>&1 | tee logs/gen-<stage>.out
# =============================================================================
set -euo pipefail

STAGE="${1:-}"; DOMAIN="${2:-}"
PYTHON="${PYTHON:-.venv/bin/python}"

MODELS=(
  openai/anthropic/claude-opus-4
  openai/anthropic/claude-sonnet-4
  openai/google/gemini-2.5-pro
  openai/google/gemini-3.1-pro-preview
  openai/z-ai/glm-5.2
)

COMMON=( --no-judge --max-tokens 32000 --time-limit 900 )

# single_turn / sequential use prompt-name conditions; agentic uses env-dir names.
ST_CONDS=( baseline level2_training_awareness level3_goal_conflict_tm1 level3_goal_conflict_tm2 level4_action_knowledge_tm1 level4_action_knowledge_tm2 level5_desire_nudge_tm1 level5_desire_nudge_tm2 level6_explicit_instruction )
AG_CONDS=( baseline level2 level3-tm1 level3-tm2 level4-tm1 level4-tm2 level5-tm1 level5-tm2 level6-tm1 level6-tm2 )

mark() { mkdir -p "$1"; printf '%s\n' "$2" > "$1/_source_block.txt"; }   # machine-readable provenance

sweep() {  # sweep <task> <dataset> <limit> <logdir> [extra flags...] -- <conditions...>
  local task="$1" dataset="$2" limit="$3" logdir="$4"; shift 4
  local extra=(); while [ "${1:-}" != "--" ]; do extra+=( "$1" ); shift; done; shift
  for M in "${MODELS[@]}"; do
    echo "----- $M | $task | $dataset | n=$limit -----"
    "$PYTHON" run_sweep.py --model "$M" --task "$task" --dataset "$dataset" \
      "${COMMON[@]}" --log-dir "$logdir" --limit "$limit" "${extra[@]}" \
      --conditions "$@"
  done
}

case "$STAGE" in
  smoke)
    [ -n "$DOMAIN" ] || { echo "usage: smoke {cyber|chem|bio}"; exit 1; }
    G=openai/google/gemini-3.1-pro-preview
    echo "===== SMOKE wmdp-$DOMAIN (config sanity, n=1) ====="
    # agentic L6 is the newest config most likely to break -> include it
    "$PYTHON" run_sweep.py --model "$G" --task single_turn --dataset "wmdp-$DOMAIN" \
      "${COMMON[@]}" --log-dir logs/gen-smoke --limit 1 --conditions baseline
    "$PYTHON" run_sweep.py --model "$G" --task agentic --dataset "wmdp-$DOMAIN" \
      "${COMMON[@]}" --log-dir logs/gen-smoke --limit 1 --conditions baseline level6-tm1
    ;;

  cyber-l6)
    # compliance ceiling (new). Items 1-100 already have an agentic baseline for all
    # 5 models (discovery 1-40 + extension 41-100), so pair L6 against the EXISTING
    # baseline — no re-run. Include main-v1/main-v2/ext-v1 as baseline sources when
    # scoring/pairing. Any top-up past item 100 runs baseline on the fresh block too.
    echo "===== cyber completion: agentic L6 (items 1-100; reuse existing baseline) ====="
    mark logs/gen-cyber-l6 cyber_completion
    sweep agentic wmdp-cyber 100 logs/gen-cyber-l6 -- level6-tm1 level6-tm2
    ;;

  seq-cyber)
    echo "===== cyber completion: sequential (all models, full ladder, 18 sessions) ====="
    mark logs/gen-seq-cyber cyber_completion
    for M in "${MODELS[@]}"; do
      echo "----- $M | sequential | wmdp-cyber | 18 sessions x 10 q -----"
      "$PYTHON" run_sweep.py --model "$M" --task sequential --dataset wmdp-cyber \
        --no-judge --max-tokens 32000 --time-limit 1800 --log-dir logs/gen-seq-cyber \
        --limit 18 --questions-per-session 10 --conditions "${ST_CONDS[@]}"
    done
    ;;

  chem)
    echo "===== chem generalization: single_turn + agentic (all models, n=100) ====="
    mark logs/gen-chem chem_generalization
    sweep single_turn wmdp-chem 100 logs/gen-chem -- "${ST_CONDS[@]}"
    sweep agentic     wmdp-chem 100 logs/gen-chem -- "${AG_CONDS[@]}"
    ;;

  bio)
    # uniform n=100; bio's refusal/filter rate is MEASURED on this block, then topped
    # up per plan §2 (or excluded per §6 if <50 pairs are attainable) — not pre-buffered
    echo "===== bio generalization: single_turn + agentic (all models, n=100) ====="
    mark logs/gen-bio bio_generalization
    sweep single_turn wmdp-bio 100 logs/gen-bio -- "${ST_CONDS[@]}"
    sweep agentic     wmdp-bio 100 logs/gen-bio -- "${AG_CONDS[@]}"
    ;;

  *)
    echo "usage: ./run_generality.sh {smoke <domain>|cyber-l6|seq-cyber|chem|bio}"; exit 1 ;;
esac

echo "===== DONE ($STAGE ${DOMAIN}) ====="
echo "Next: score the new logs, then analysis/pair_report.py -> scoreable-pair counts +"
echo "shortfall cause + source_block, then outcome-blind 40-item top-ups (plan section 2)."
