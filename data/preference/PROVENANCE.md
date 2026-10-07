# Preference-preservation arm — freeze provenance (read before writing the paper)

Accurate ordering of what was frozen when, so claims about pre-registration are
truthful. The shared machinery (tasks, scorer, discovery mechanism, scaffolds,
conditions, analysis) is identical across axes; only the axis config + data differ.

## Truthfulness axis
- Item selection criterion frozen (`SELECTION_CRITERION.md`), 60-item set + split +
  scaffold/scorer/endpoint frozen (`FREEZE_MANIFEST_truthfulness.txt`) **before** the
  Gemini 3.1 Pro truthfulness run.
- The C0→L4 primary contrast on Gemini 3.1 Pro is the pre-registered confirmatory test
  for this axis. Result observed after freeze.

## Power axis
- Selected and frozen (`SELECTION_CRITERION_power.md`, `power_final_60.jsonl`, curated
  split, `FREEZE_MANIFEST_power.txt`) **after** the truthfulness Gemini result was seen,
  and after the truthfulness run had begun.
- Items were chosen by **construct criteria only** (behavioral/normative power
  commitment; X/Y prescribe opposite answers), NOT by any power-axis model outcome. No
  power-axis run had been executed at freeze time.
- Therefore describe power as **prospectively frozen before any power-axis model
  outcomes** — NOT as jointly pre-registered with truthfulness before seeing truthfulness
  results. Do not imply both axes were preregistered together.

## Reporting notes
- `preference_analysis.py` §7 (C0→L4 by semantic_family) is a **robustness/decomposition**
  view, not a battery of per-family hypothesis tests: families are asymmetric (n = 1..9),
  so the inferential question is whether deterioration spans multiple substantively
  different families, not whether each family reaches significance.
- X-screen is a descriptive manipulation check (see `PROTOCOL.md`), reported as aggregate
  + directional decomposition; never an eligibility filter.

## Manifests (tamper-evident hashes)
- `FREEZE_MANIFEST_truthfulness.txt`, `FREEZE_MANIFEST_power.txt` — sha256 of data +
  personas + scaffold + code at freeze. Preserve via git commit for timestamped provenance.
