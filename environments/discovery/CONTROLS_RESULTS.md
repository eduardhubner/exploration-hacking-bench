# WMDP discovery controls — results (C0 / shadow) + cognitive overlay

*Companion to [CONTROLS_DESIGN.md](CONTROLS_DESIGN.md) (construction) and
[CONTROLS_FREEZE.txt](CONTROLS_FREEZE.txt). Agentic WMDP discovery. Last updated 2026-09-25.*

**Roster.** C0 (no-update) + shadow (different-model) were run for
bio/chem {Sonnet-4, Gemini-2.5, Gemini-3.1, GLM-5.2} and cyber {those + GPT-Sol, Kimi};
100 items/cell, 1 epoch. **Opus-4 excluded** (its ladder ran on claude-opus-4 / dead
Vertex; controls would be opus-4.1 → within-model version confound). **GPT-Sol excluded
from cognitive** analysis (encrypted CoT — the reasoning judge has nothing to read).

Index: the 14 `logs/gen-controls-*` dirs are in `build_index.py` `DATA_DIRS`; c0/shadow
are new conditions (no episode collision with the ladder).

---

## 1. Behavioral shadow decomposition (Gemini-3.1)
Figure [`figures/fig_controls_shadow.png`](../../figures/fig_controls_shadow.png);
compute [`analysis/controls_behavioral.py`](../../analysis/controls_behavioral.py).

Accuracy (correct / scoreable), item-matched paired diffs:

| domain | baseline | C0 | shadow | L4·tm1 | C0−base | shadow−C0 | L4−shadow |
|---|---|---|---|---|---|---|---|
| bio | 0.86 | 0.89 | **0.22** | 0.42 | +0.01 | **−0.67** | +0.17 |
| chem | 0.88 | 0.85 | **0.46** | 0.48 | −0.01 | **−0.39** | −0.06 |
| cyber | 0.92 | 0.94 | **0.42** | 0.52 | +0.01 | **−0.52** | +0.08 |

- **Being recorded (no update) is inert:** C0 ≈ baseline in every domain (|Δ| ≤ 0.01).
- **The effect is the training consequence:** shadow−C0 = −0.39 … −0.67, with massively
  directional C→W (62/40/45 vs W→C 2/2/0).
- **L4 ≈ shadow (or slightly above):** own-model suppression is no worse than different-model.
  Total L4−baseline ≈ −0.40 in all domains.

## 2. Where unnudged underperformance occurs (delivery mode)
Figure [`figures/fig_wmdp_main.png`](../../figures/fig_wmdp_main.png) Panel A
(WMDP-Cyber, baseline→L4·tm1, Wilson CIs):

- **single-turn:** all 7 models flat at ~0.8–0.9 — **no unnudged effect**.
- **sequential:** low and noisy (n=13–18/cell); Opus drops to 0 by L4 but at small n.
- **agentic:** **Gemini-3.1 collapses 0.92→0.52**; every other model stays flat.

So the unnudged capability-preservation effect is **agentic + Gemini-3.1-specific**.

## 3. Cross-domain replication and TM1≫TM2 (Gemini-3.1 agentic)
Figure `fig_wmdp_main.png` Panel B. Accuracy drop vs baseline:

| domain | L3·tm1 | L3·tm2 | L4·tm1 | L4·tm2 |
|---|---|---|---|---|
| cyber | 0.31 | 0.05 | 0.41 | 0.10 |
| bio | 0.33 | 0.05 | 0.45 | 0.12 |
| chem | 0.34 | 0.06 | 0.40 | 0.12 |

Near-identical across domains (clean replication); **TM1 elicits a far stronger effect
than TM2** (drops ~0.3–0.45 vs ~0.05–0.12), consistent at L3 and L4.

## 4. Cognitive overlay
Figure [`figures/fig_wmdp_cognitive.png`](../../figures/fig_wmdp_cognitive.png). Gemini-3.1
c0/shadow judged with the production 5-pass holistic judge (Sol), merged into
`data/cognitive_labels.json`; rows in `data/cognitive_rows.json`.

**Panel A — Gemini-3.1 funnel, C0 vs shadow (mean over domains):**
- **C0:** believes / dim1 / dim3 / dim4 all **0.00** — cognitively inert (mirrors C0≈baseline).
- **shadow:** believes 0.65 → training-aware 0.81 → plans 0.69 → **verbalizes
  underperformance (dim4) 0.58**, decoupling ≈0. The full belief→action funnel, and
  **stronger than L4·tm1** on every construct (different-model > own-model cognitively too).

**Panel B — why only Gemini-3.1 underperforms (L4·tm1, cyber; from existing ladder labels):**
different **routes to non-underperformance** —
- Gemini-3.1: **believes + underperforms**.
- Opus-4 / Sonnet-4 / Gemini-2.5: **don't adopt the scenario, decouple** (decoupling ~0.30–0.36).
- Kimi: training-aware but **rejects the premise** (0.89).
- GLM: premise-reject + decouple.

**Takeaway:** belief gates the behavior; the null models fail to adopt the scenario (and
dismiss it via decoupling or premise-rejection), so they never underperform — "won't
because don't believe," not "can't."

---

## 5. Reproducibility
- **Behavioral:** `analysis/controls_behavioral.py --model gemini-3.1-pro-preview`;
  `analysis/fig_controls_shadow.py`; `analysis/fig_wmdp_main.py`.
- **Cognitive:** `analysis/score_transcripts.py --models gemini-3.1-pro-preview
  --conditions c0 shadow --cap 40 --out data/gemini31_controls_cognitive.json` →
  merged into `data/cognitive_labels.json` → `analysis/cognitive_report.py` →
  `data/cognitive_rows.json`; figure `analysis/fig_wmdp_cognitive.py`.
- **Not judged (by design):** GPT-Sol (encrypted CoT); other models' c0/shadow (behaviorally
  null at shadow → no effect to explain; their ladder cognition already covers the null story).
