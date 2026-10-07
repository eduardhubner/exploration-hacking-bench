#!/usr/bin/env bash
# Assemble a self-contained, runnable figure kit for collaborators in figure_kit/.
# Mirrors the repo's analysis/ + data/ layout so every figure script reproduces
# from a clone of THIS folder alone (no logs, no scratchpad, no API keys).
# Non-destructive to the repo: only writes under figure_kit/. Re-run to refresh.
set -euo pipefail
cd "$(dirname "$0")"                     # repo root (exploration-hacking-bench)
KIT=figure_kit

rm -rf "$KIT"
mkdir -p "$KIT/analysis" "$KIT/data/preference/ladder" "$KIT/figures"

# --- figure scripts (+ the one shared helper) ---
for f in fig_ctf.py paper_figures.py fig_wmdp_main.py fig_wmdp_cognitive.py \
         fig_preference_mechanism.py fig_controls_shadow.py controls_behavioral.py \
         fig_preference.py; do
  cp "analysis/$f" "$KIT/analysis/"
done

# --- data (aggregated rows / labels / single-letter answers only) ---
for f in behavioral_rows.json cognitive_rows.json engagement_rows.json \
         abstract_bars_rows.json; do
  cp "data/$f" "$KIT/data/"
done

# episode_index.jsonl: normalize the answer fields to a single letter (or null).
# ~1k episodes recorded free text instead of a letter, and ~126 of those carry
# verbatim model prose/reasoning that restates WMDP item content. No figure
# script reads model_answer or correct_answer, and `outcome` already encodes the
# refused/unknown distinction, so collapsing them to "non_letter" costs nothing
# analytically and keeps item text out of the kit. Every other field and row is
# passed through unchanged.
python3 - "data/episode_index.jsonl" "$KIT/data/episode_index.jsonl" <<'SCRUB'
import json, sys
src, dst = sys.argv[1], sys.argv[2]
rows = scrubbed = 0
with open(src) as fi, open(dst, "w") as fo:
    for line in fi:
        line = line.strip()
        if not line:
            continue
        o = json.loads(line)
        rows += 1
        hit = False
        for field in ("model_answer", "correct_answer"):
            v = o.get(field)
            if isinstance(v, str) and len(v) > 1:
                o[field] = "non_letter"
                hit = True
        scrubbed += hit
        fo.write(json.dumps(o) + "\n")
print(f'  episode_index.jsonl: {rows} rows, {scrubbed} free-text answers -> "non_letter"')
SCRUB
cp data/preference/judge_rows.json "$KIT/data/preference/"
cp data/preference/ladder/*.txt "$KIT/data/preference/ladder/"

# --- pre-rendered figures (so collaborators see expected output) ---
for fig in fig_ctf fig_ctf_appendix fig_wmdp_main fig_controls_shadow fig_wmdp_cognitive \
           fig_pref_mechanism fig3_gemini_crossdomain fig4_reasoning \
           fig_pref_combined fig_pref_power fig_pref_truthfulness; do
  for ext in png pdf; do
    [ -f "figures/$fig.$ext" ] && cp "figures/$fig.$ext" "$KIT/figures/" || true
  done
done

# --- requirements ---
cat > "$KIT/requirements.txt" <<'REQ'
matplotlib>=3.7
numpy>=1.24
REQ

# --- runner: regenerate every figure from the committed data ---
cat > "$KIT/run_all.sh" <<'RUN'
#!/usr/bin/env bash
# Regenerate every figure into figures/. Run from the kit root.
set -euo pipefail
cd "$(dirname "$0")"
python3 analysis/fig_ctf.py
python3 analysis/fig_wmdp_main.py
python3 analysis/fig_wmdp_cognitive.py
python3 analysis/fig_preference_mechanism.py
python3 analysis/fig_controls_shadow.py
python3 analysis/fig_preference.py
# paper_figures.py exposes fig2/fig3/fig4/... ; render the shared cross-domain + reasoning panels
python3 -c "import sys; sys.path.insert(0,'analysis'); import paper_figures as p; p.fig3(); p.fig4()"
echo "done -> figures/"
RUN
chmod +x "$KIT/run_all.sh"

# --- README ---
cat > "$KIT/README.md" <<'MD'
# Exploration-Hacking — figure kit

Self-contained scripts + data to regenerate every figure in the paper. No logs,
no scratchpad, no API keys, no network access required.

## Run

```bash
pip install -r requirements.txt        # matplotlib, numpy
./run_all.sh                           # regenerates everything into figures/
```

Run scripts from the **kit root** (paths are relative to it). Individual figures:

```bash
python3 analysis/fig_ctf.py                     # -> figures/fig_ctf.{png,pdf} (+ appendix)
python3 analysis/fig_wmdp_main.py               # WMDP delivery-mode main figure
python3 analysis/fig_wmdp_cognitive.py          # WMDP cognitive companion
python3 analysis/fig_preference_mechanism.py    # preference mechanism panel
python3 analysis/fig_controls_shadow.py         # no-update / different-model controls
python3 analysis/fig_preference.py              # fig_pref_combined (+ per-axis)
python3 -c "import sys;sys.path.insert(0,'analysis');import paper_figures as p;p.fig3();p.fig4()"
```

`paper_figures.py` also exposes the appendix panels — `fig2`, `fig2_bytm`,
`fig2_bytm_allcolor`, `fig3_bytm`, `figA1a`, `figA1b`, `figA2`, `figA4`,
`figA5`, `figA7`, `fig_abstract`, `fig_abstract_bars` — all of which render from
the shipped data the same way. `figA6` is the one exception: it needs the raw
eval logs and `inspect_ai`, neither of which ships here.

## Layout

```
analysis/   figure scripts (fig_controls_shadow.py imports controls_behavioral.py)
data/       aggregated rows the scripts read:
  behavioral_rows.json    per-item WMDP behavioral rates
  cognitive_rows.json     WMDP holistic-judge construct rates
  engagement_rows.json    reasoning-trace engagement rates
  episode_index.jsonl     per-episode metadata + letter answers (see note)
  abstract_bars_rows.json abstract summary bars
  preference/judge_rows.json      frozen preference-judge labels
  preference/ladder/{P,T}-<model>.txt  per-model accuracy-per-rung ladder summaries
figures/    pre-rendered outputs (PNG + PDF) for reference
```

## Data notes

- `episode_index.jsonl` is per-episode **metadata plus a single-letter answer**
  (model, condition, item id, `model_answer`, `correct_answer`, `outcome`) —
  **no WMDP question text and no model reasoning**. Episodes that answered with
  free text rather than a letter (refusals, stray prose) are recorded as
  `model_answer: "non_letter"`; `outcome` keeps the refused/unknown distinction.
  No figure script reads either answer field. Do not re-attach raw WMDP items to
  this file when sharing.
- Preference items derive from Anthropic's model-written-evals; attribute
  accordingly.
- The ladder `.txt` summaries are regenerated with
  `analysis/preference_analysis.py --block <logs> --l6 <logs> --screen <logs>`
  (needs the raw eval logs, not shipped here).

## Naming

Paper-facing condition names map to the data keys as: **no-update** = `c0`,
**different-model** = `shadow`, **own-model** = the L4 RL condition.
MD

n_scripts=$(ls "$KIT/analysis"/*.py | wc -l | tr -d ' ')
n_data=$(find "$KIT/data" -type f | wc -l | tr -d ' ')
n_fig=$(ls "$KIT/figures" | wc -l | tr -d ' ')
echo "figure kit assembled in $KIT/ ($n_scripts scripts, $n_data data files, $n_fig figure files)"
