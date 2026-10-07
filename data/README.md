# Data

All released data artifacts, their schemas, and the rules that define what counts
as "the dataset". This directory plus the `analysis/` scripts reproduce every
number in the paper.

**One rule underlies everything here:** the *episode index* (`episode_index.jsonl`)
is the single source of truth for what was collected. Every analysis reads it
rather than re-scanning `logs/`. Historically, scripts that re-globbed `logs/` and
re-decided what counted caused silent data-loss bugs (see the release checklist);
the index exists to make that impossible.

---

## Files at a glance

| file | what | produced by |
|---|---|---|
| `episode_index.jsonl` | canonical row-per-episode index (the dataset definition) | `analysis/build_index.py` |
| `behavioral_rows.json` | per-cell paired McNemar, ALL models/arms/domains (canonical) | `analysis/run_all_comparisons.py` (index-backed) |
| `cognitive_rows.json` | per-cell cognitive construct rates | `analysis/cognitive_report.py` |
| `engagement_rows.json` | per-cell registration rate + null-mechanism taxonomy | `analysis/engagement_report.py` |
| `../*_labels*.json` | cognitive-overlay labels (see "Label files" below) | `analysis/score_transcripts.py` |
| `../gold*.json` | hand-labelled gold + backups (see "Gold" below) | `analysis/parse_gold_sheet.py` |

The behavioural results (`*_rows.json`) are FINAL and self-contained. The cognitive
labels are currently **fragmented across several files pending a merge** — see below.

---

## 1. `episode_index.jsonl` — the canonical index

One JSON object per line, one per collected episode. **45,718 rows** (44,270 live +
1,448 superseded). Fields:

| field | meaning |
|---|---|
| `key` | `<log_stem>:<sample_id>` — the join key across all artifacts |
| `domain` | `cyber` / `bio` / `chem` |
| `arm` | `single_turn` / `agentic` / `sequential` |
| `model` | short name, e.g. `gemini-3.1-pro-preview`, `kimi-k3-20260715` |
| `condition` | scaffold condition (e.g. `level4-tm1`, `level4_action_knowledge_tm1`) |
| `item_id` | 1-indexed WMDP item position (restarts at 1 per domain) |
| `log_dir`, `log_stem`, `dir_rank` | provenance; `dir_rank` = precedence for dedup |
| `source_block` | machine-readable block label from `logs/<dir>/_source_block.txt` |
| `offset`, `limit` | the sweep's item slice |
| `outcome` | `correct`/`wrong`/`refused`/`filtered`/`infra_error`/`unknown`/`None` |
| `scoreable` | `outcome ∈ {correct, wrong}` |
| `model_answer`, `correct_answer`, `stop_reason` | answer + provider stop reason |
| `error` | truncated error string if the sample errored |
| `n_files_read` | distinct files opened via `read_file` (agentic only; the exploration gate) |
| `superseded` | `true` if a higher-`dir_rank` copy of the same episode exists |

### Selection rules encoded in the index (not re-derived elsewhere)

- **Smoke/test dirs are excluded** (`gen-smoke`, `ext-smoke`, `smoke-agentic`,
  `slugtest`, `testset`, …). They share item ids with real cells — e.g. an
  `ext-smoke` n=1 run sits on id 41, inside `ext-v1`'s range — so counting them
  corrupts coverage and pair counts.
- **Duplicate episodes are resolved by `dir_rank`** (later block wins). The loser is
  **kept with `superseded: true`**, never silently dropped, so the resolution is
  auditable. `main-v1`/`main-v2` genuinely overlap on 12 cells; that overlap is
  visible in the index.
- **Legacy untyped logs** (no `--dataset` arg, predating multi-domain) are treated
  as `cyber` only in `main-v*`/`ext-v*`; anything else untyped is exploratory and
  excluded.
- **Sequential** is indexed but scored per-question (`sequential_outcome_scorer`),
  not per session.

### Cell structure

A **cell** = (domain, arm, model, condition). Live: **368 cells** across 7 subject
models (5 primary + gpt-5.6-sol + kimi-k3; the last two cyber-only). Target is
**≥100 scoreable matched pairs per cell**; the single-turn/agentic non-baseline
cells all reach it. See `analysis/pair_report.py`.

---

## 2. `*_rows.json` — behavioural results (FINAL)

One object per (dataset, model, arm, condition) cell:

| field | meaning |
|---|---|
| `dataset` | `wmdp-cyber` / `wmdp-bio` / `wmdp-chem` |
| `model`, `arm`, `cond` | the cell |
| `n` | scoreable matched pairs (all four transition types) |
| `cw`, `wc` | b = C→W (degradation), c = W→C (noise floor) |
| `rate` | **b/n** — the C→W rate, the reported effect size |
| `ci` | `[lo, hi]` Wilson 95% CI **on b/n** |
| `p` | two-sided exact-binomial McNemar p (conditions on b+c) |
| `q` | Benjamini–Hochberg FDR q over the L2–L4 primary family |
| `blv` | believer count (auxiliary) |
| `primary` | in the FDR family (L2–L4) or not |

**Effect size is `b/n`, CI on `b/n`.** The McNemar hypothesis test conditions on the
discordant total `b+c`, but the reported rate and CI use the full paired
denominator `n`. (The discordant share `b/(b+c)` is a separate, unstable secondary
quantity; not reported. See `PREREGISTRATION.md` / `SCORING_FRAMEWORK.md`.)

---

## 3. `cognitive_labels.json` — cognitive overlay (consolidated)

**27,026 labelled episodes**, keyed by the same `<log_stem>:<sample_id>` as the
index. This is the single cognitive-label artifact; it consolidates the staged
judging runs (initial cyber, cyber extension, capped cyber re-run, bio/chem, Kimi
expansion). Regenerate with:

```bash
python analysis/merge_labels.py          # -> data/cognitive_labels.json
python analysis/merge_labels.py --check  # validate an existing merge
```

The source files live in `backups/labels/`; the three merge rules (precedence,
neutralized-dismissal overlay, single-turn-L6 belief nulling) are documented in
`analysis/merge_labels.py`.

### Label record schema

| field | meaning |
|---|---|
| `belief_gate` | `believes` / `disbelieves` / `unstated`; `null` where gated (incl. single-turn L6) |
| `dim1`–`dim4` | 0/1: training-awareness, goal-conflict, planning, action; N/A where gated |
| `goal_conflict_source`, `planning_source`, `action_rationale_source` | provenance (exploratory) |
| `premise_rejection_gate`, `decoupling_gate` | 0/1: danger-axis / relevance-axis dismissal |
| `dismissal_source` | `neutralized_rejudge` if premise/decoupling came from the domain-neutral re-score (cyber already-judged rows) |
| `judge_parse_ok` | `false` if any pass failed to parse (defaults that pass to 0/unstated) |
| `judge_parse_failures` | list of constructs whose pass failed |
| `judge_model` | the deployed judge for this transcript |
| `arm`, `condition`, `flags` | echoed context + `consistency_flags` QC |

### Coverage caveats (documented in the paper)

- **Level gating:** a construct is N/A where the scaffold does not establish its
  precondition (baseline none; L2 belief+dim1; L3–L5 all; L6 belief+dim4+premise+
  decoupling, belief also N/A at single-turn L6). N/A != 0.
- **Encrypted reasoning:** gpt-5.6-sol returns 99% ciphertext, so it has **no
  cognitive labels** — behavioural only, excluded on a verifiable criterion.
- **Sequential arm has no cognitive labels** (multi-turn judge harness unbuilt).
- **Residual parse failures:** ~109 of 27,026 (0.4%), almost all long agentic
  transcripts, have >=1 unparsed pass after one retry; kept flagged, not hidden.
- **Cognitive n capped at 100 judgeable items/cell**, matched across a group's
  conditions; behavioural n uses all pairs.

## 4. Gold (`../gold*.json`)

| file | what |
|---|---|
| `gold.json` | cyber gold, 99 hand-labelled transcripts (judge dev set, tier 2) |
| `gold_heldout.json` | bio + chem, 80 transcripts (frozen held-out, tier 3 — the reported judge-accuracy numbers) |
| `gold_*_backup.json` | dated snapshots from label corrections; move to `backups/` before release |

`gold.json` is **authoritative for cyber**; it has diverged from `gold_sheet.md`
on a few belief rows, so re-parsing the sheet would revert corrections — treat the
sheet as read-only or regenerate it from the JSON (release checklist §2).
Annotation protocol: `docs/internal/GOLD_ANNOTATION_GUIDE.md`. Single-annotator; no
inter-annotator κ.

---

## Rebuilding

```bash
# 1. index (reads every .eval — the slow step, ~10 min)
python analysis/build_index.py

# 2. behavioural results
# single-turn + agentic come from the index; only sequential is read from logs
python analysis/run_all_comparisons.py --log-dirs logs/gen-seq-cyber logs/banked-seq \
    --save-json data/behavioral_rows.json     # ~25s, all 7 models, all 3 arms
python analysis/cognitive_report.py            # -> data/cognitive_rows.json
python analysis/engagement_report.py --out data/engagement_rows.json

# 3. coverage audit (reads the index; seconds)
python analysis/pair_report.py
```
