#!/usr/bin/env bash
# Verify the Cybench-on-Inspect integration BEFORE building anything on top of it.
# Run from repo root:  bash cybench/verify_integration.sh
set -uo pipefail
cd "$(dirname "$0")/.."
# shellcheck disable=SC1091
source .venv/bin/activate 2>/dev/null || { echo "no .venv — activate your env first"; exit 1; }

echo "1) inspect_ai:"
python -c "import inspect_ai; print('   ok', inspect_ai.__version__)" || echo "   MISSING"

echo "2) inspect_evals + cybench task:"
python -c "from inspect_evals.cybench import cybench; print('   ok — cybench importable')" 2>/dev/null \
  || echo "   MISSING -> pip install inspect_evals    # or: pip install 'git+https://github.com/UKGovernmentBEIS/inspect_evals'"

echo "3) docker (cybench spins up a sandbox per challenge):"
docker info >/dev/null 2>&1 && echo "   ok — docker running" || echo "   MISSING / not running — start Docker Desktop"

echo "4) cybench task args (confirm the -T flags the pilot/ladder will pass):"
inspect eval inspect_evals/cybench --help 2>/dev/null | sed -n '1,60p' \
  || echo "   (install inspect_evals first, then re-run)"

echo
echo "5) end-to-end smoke test — one challenge, cheap model, 1 epoch:"
echo "   inspect eval inspect_evals/cybench --model openai/gpt-4o-mini --limit 1 --epochs 1 --log-dir logs/cybench-smoke"
echo "   (a completed sample with a score = the Docker sandbox + flag-grading path works end to end)"
