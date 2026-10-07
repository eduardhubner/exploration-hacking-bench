#!/usr/bin/env bash
# Cybench BASELINE pilot (L1, no scaffold): the single cheap run that green-lights
# or kills the whole agentic arm. Measures how many challenges the model can solve
# at all, i.e. how much ceiling exists for the scaffold to push it *down* from.
#
#   bash cybench/run_baseline_pilot.sh [MODEL] [EPOCHS] [LOGDIR]
#
# EPOCHS = rollouts per challenge (N). 8 is a reasonable pilot value: enough to
# estimate a per-challenge solve probability without a huge bill.
set -euo pipefail
cd "$(dirname "$0")/.."
# shellcheck disable=SC1091
source .venv/bin/activate

MODEL="${1:-google/gemini-3.1-pro-preview}"   # <-- confirm exact provider slug for Gemini 3.1
EPOCHS="${2:-8}"
LOGDIR="${3:-logs/cybench-pilot-baseline}"

# cybench task args (confirmed): eval_names, variant_names (default 'hard'),
# sandbox_type (default 'docker'). 39 challenges; 'hard' = minimal-guidance prompt.
# If solve rates are too low, rerun with VARIANT=easy (more guidance, higher solves).
# Baseline = the task as shipped, no EH scaffold injected yet.
VARIANT="${4:-hard}"
inspect eval inspect_evals/cybench \
  --model "$MODEL" \
  --epochs "$EPOCHS" \
  --log-dir "$LOGDIR" \
  -T variant_names="$VARIANT" \
  -T sandbox_type=docker

echo
echo "analyze:  .venv/bin/python cybench/analyze_pilot.py $LOGDIR"
