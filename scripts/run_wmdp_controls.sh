#!/usr/bin/env bash
# WMDP agentic-discovery CONTROLS (c0 = measurement placebo, shadow = separate-policy)
# across the 5-model roster x 3 domains. Mirrors run_generality.sh's sweep: behavioral
# only (--no-judge; cognitive overlay scored later via score_transcripts.py). NO Docker
# (agentic_discovery is in-process). Per-(domain,model) log dir + guard so re-running
# skips finished cells (these subject runs are expensive).
#
#   nohup caffeinate -i bash run_wmdp_controls.sh > logs/wmdp-controls.out 2>&1 &
set -x
cd "$(dirname "$0")/.."   # repo root
# run_sweep.py builds the subject model via get_model() BEFORE Inspect auto-loads .env,
# so export the keys ourselves (OPENAI_API_KEY/OPENAI_BASE_URL for OpenRouter).
set -a; [ -f .env ] && . ./.env; set +a
PY="uv run python"

# rosters match the WMDP agentic ladder: bio/chem = 5 models; cyber = 7 (behavioural-
# complete: + kimi + gpt-5.6-sol). opus-4 (dead, Vertex 502) -> opus-4.1. gpt-sol runs
# at provider-default reasoning (matches the original cyber gpt-sol L4 under COMMON).
# NOTE: opus DROPPED — the paper's opus WMDP L4 is claude-opus-4 (dead, Vertex 502),
# so opus-4.1 c0/shadow could not be paired within-model (version confound). Opus is
# omitted from the control decomposition; note this in the paper.
MODELS_STD=(                       # bio, chem
  "openai/anthropic/claude-sonnet-4  sonnet4"
  "openai/google/gemini-2.5-pro      gemini25"
  "openai/google/gemini-3.1-pro-preview gemini31"
  "openai/z-ai/glm-5.2               glm"
)
MODELS_CYBER=( "${MODELS_STD[@]}"
  "openai/moonshotai/kimi-k3  kimi"
  "openai/openai/gpt-5.6-sol  gptsol"
)

# exactly the COMMON settings the frozen L4 runs used (run_generality.sh) — no extras
COMMON=( --no-judge --max-tokens 32000 --time-limit 900 )
# UNIFORM 100 items/cell (offset 0 -> dataset items 1-100), matching the paper's
# capped-at-100 convention. NOTE: this is a contiguous first-100 subset, not the
# filtering-dependent lexicographic cognitive-100 ids (which offset/limit can't
# reproduce); the behavioural L4 itself used all items, so this is a 100-item
# matched-subset control. See environments/discovery/CONTROLS_FREEZE.txt.
LIMIT=100

_done () { [ "$(ls "$1"/*.eval 2>/dev/null | wc -l)" -ge 2 ]; }   # c0 + shadow both present

run_domain () {                    # $1 dataset  $2... "model tag" entries
  local DS="$1"; shift; local short="${DS#wmdp-}"
  for entry in "$@"; do
    set -- $entry; local M="$1" TAG="$2"
    local LD="logs/gen-controls-${short}-${TAG}"
    if _done "$LD"; then echo "### skip $short/$TAG (already has c0+shadow)"; continue; fi
    echo "===== $M | agentic | $DS | c0 shadow | limit=$LIMIT (offset 0) ====="
    $PY run_sweep.py --model "$M" --task agentic --dataset "$DS" \
      "${COMMON[@]}" --log-dir "$LD" --limit "$LIMIT" --offset 0 --conditions c0 shadow
  done
}

run_domain wmdp-cyber "${MODELS_CYBER[@]}"
run_domain wmdp-chem  "${MODELS_STD[@]}"
run_domain wmdp-bio   "${MODELS_STD[@]}"
echo WMDP_CONTROLS_COMPLETE
