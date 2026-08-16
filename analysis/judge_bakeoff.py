"""Judge bake-off: score fixed transcripts with several candidate judges.

Compares judge models on IDENTICAL inputs. Generate subject transcripts once
(run the eval with ``--no-judge`` so only the deterministic scorers run), then
point this at those logs with a list of candidate judge models. It runs the same
two-pass judge (``_run_holistic_judge``) used in production over every
transcript, per judge, and reports:

  - per-judge **parse-fail rate** (fraction with judge_parse_ok=False) — the
    silent-failure rate that biases scores toward "no EH";
  - **inter-judge agreement** per dimension (fraction identical), pairwise or
    vs a --reference judge;
  - **accuracy vs gold** per dimension, if a --gold JSON is supplied.

Pick the cheapest judge with high agreement AND low parse-fail (and, if you have
gold, high accuracy). Requires API access for each judge model.

Usage
-----
    python analysis/judge_bakeoff.py logs/testset/*.eval \\
        --judges anthropic/claude-haiku-4-5 anthropic/claude-sonnet-4-6 \\
        --reference anthropic/claude-sonnet-4-6 \\
        [--gold gold.json] [--concurrency 5]

gold.json: {"<log_stem>:<sample_id>": {"belief_gate": "unstated",
            "premise_rejection_gate": 0, "dim1": 0, "dim2": 0, "dim3": 0,
            "dim4": 0}, ...}  (any subset of dims per item; legacy "dim0_belief"
            keys are still accepted for the belief gate)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

DIM_KEYS = ["belief_gate", "premise_rejection_gate", "decoupling_gate", "dim1", "dim2", "dim3", "dim4"]


# ---------------------------------------------------------------------------
# Transcript extraction
# ---------------------------------------------------------------------------


def _input_text(sample: Any) -> str:
    inp = getattr(sample, "input", "")
    if isinstance(inp, str):
        return inp
    # list of chat messages -> concatenate text
    parts = []
    for m in inp or []:
        c = getattr(m, "content", "")
        parts.append(c if isinstance(c, str) else str(c))
    return "\n".join(parts)


def load_transcripts(log_paths: list[Path], scorer: str = "outcome_scorer") -> list[dict]:
    """Extract the fields _run_holistic_judge needs, one dict per sample."""
    from inspect_ai.log import read_eval_log
    from ehbench.scorers.markov_scorer import _get_system_prompt, _extract_final_response

    items: list[dict] = []
    for p in log_paths:
        p = Path(p)
        log = read_eval_log(str(p))
        condition = (log.eval.task_args or {}).get("condition")
        for s in log.samples or []:
            score = (s.scores or {}).get(scorer) or (s.scores or {}).get("answer_accuracy")
            meta = (score.metadata if score else {}) or {}
            items.append(
                {
                    "id": f"{p.stem}:{s.id}",
                    "system_prompt": _get_system_prompt(s.messages),
                    "question": _input_text(s),
                    "response": _extract_final_response(s.messages),
                    "correct_answer": str(meta.get("correct_answer", "")),
                    "model_answer": meta.get("model_answer") or "",
                    "is_correct": meta.get("outcome") == "correct",
                    "condition": condition,
                }
            )
    return items


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


async def score_with_judge(
    items: list[dict],
    judge_model: str,
    concurrency: int,
    reasoning_effort: str | None = None,
    temperature: float | None = None,
) -> list[dict[str, Any]]:
    """Run the two-pass judge over every transcript with one judge model."""
    from ehbench.scorers.markov_scorer import _run_holistic_judge

    sem = asyncio.Semaphore(concurrency)

    async def one(it: dict) -> dict[str, Any]:
        async with sem:
            return await _run_holistic_judge(
                judge_model=judge_model,
                system_prompt_used=it["system_prompt"],
                question=it["question"],
                correct_answer=it["correct_answer"],
                model_answer=it["model_answer"],
                is_correct=it["is_correct"],
                response=it["response"],
                reasoning_effort=reasoning_effort,
                temperature=temperature,
                condition=it.get("condition"),
            )

    return await asyncio.gather(*(one(it) for it in items))


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


def _agreement(a: list, b: list) -> float:
    n = len(a)
    return (sum(1 for x, y in zip(a, b) if x == y) / n) if n else float("nan")


def parse_fail_rate(scores: list[dict]) -> float:
    n = len(scores)
    return (sum(1 for s in scores if not s.get("judge_parse_ok", True)) / n) if n else 0.0


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def report(
    items: list[dict],
    by_judge: dict[str, list[dict]],
    reference: str | None,
    gold: dict[str, dict] | None,
) -> None:
    judges = list(by_judge)
    print(f"\n{'=' * 64}")
    print(f"  JUDGE BAKE-OFF — {len(items)} transcripts, {len(judges)} judge(s)")
    print(f"{'=' * 64}")

    print("\n  Parse-fail rate (lower is better — silent bias toward 'no EH'):")
    for j in judges:
        print(f"    {j:<40} {parse_fail_rate(by_judge[j]):6.1%}")

    print("\n  Inter-judge agreement (fraction identical per dimension):")
    pairs = (
        [(reference, j) for j in judges if j != reference]
        if reference
        else [(judges[i], judges[k]) for i in range(len(judges)) for k in range(i + 1, len(judges))]
    )
    header = "    " + "pair".ljust(50) + "".join(f"{k:>8}" for k in DIM_KEYS)
    print(header)
    for a, b in pairs:
        cells = "".join(
            f"{_agreement([s.get(k) for s in by_judge[a]], [s.get(k) for s in by_judge[b]]):8.2f}"
            for k in DIM_KEYS
        )
        print(f"    {(a + ' ~ ' + b):<50}{cells}")

    if gold:
        idx = {it["id"]: n for n, it in enumerate(items)}

        def _acc_block(title: str, keep) -> None:
            sub = {g: v for g, v in gold.items() if keep(v)}
            if not sub:
                return
            print(f"\n  {title} ({len(sub)} items):")
            print("    " + "judge".ljust(40) + "".join(f"{k:>8}" for k in DIM_KEYS))
            for j in judges:
                cells = ""
                for k in DIM_KEYS:
                    hit = tot = 0
                    for gid, glabels in sub.items():
                        if k in glabels and gid in idx:
                            pred = by_judge[j][idx[gid]].get(k)
                            if pred is None:  # gated (e.g. dim1-3 at L6) — not scored
                                continue
                            tot += 1
                            hit += int(pred == glabels[k])
                    cells += (f"{hit / tot:8.2f}" if tot else f"{'—':>8}")
                print(f"    {j:<40}{cells}")

        # `unresolved` gold is intrinsically ambiguous — kept OUT of the primary
        # metric, shown separately as an ambiguity stress test. Items with no
        # gold_status count as scored (backward compatible).
        _acc_block("Accuracy vs gold — PRIMARY (unanimous + adjudicated)",
                   lambda v: v.get("gold_status") != "unresolved")
        _acc_block("Ambiguity stress test — UNRESOLVED gold (not a judge failure)",
                   lambda v: v.get("gold_status") == "unresolved")

        # Exact-match accuracy above is misleading on 0-dominated constructs (a
        # judge that always says 0 scores ~93% on decoupling while catching none
        # of the 1s). The selection metric is POSITIVE-CLASS RECALL/PRECISION —
        # did the judge catch the rare, load-bearing positives?
        BINARY = [k for k in DIM_KEYS if k != "belief_gate"]
        primary = {g: v for g, v in gold.items() if v.get("gold_status") != "unresolved"}

        print(f"\n  Positive-class recall / precision on the 1s "
              f"(rare classes — the labels that matter):")
        print("    " + "construct".ljust(24) + "gold#1".rjust(7)
              + "".join(f"{j.split('/')[-1][:14]:>16}" for j in judges))
        for k in BINARY:
            npos = sum(1 for v in primary.values() if v.get(k) == 1)
            cells = ""
            for j in judges:
                tp = fp = fn = 0
                for gid, gl in primary.items():
                    if k not in gl or gid not in idx:
                        continue
                    g, p = gl[k], by_judge[j][idx[gid]].get(k)
                    if p is None:  # gated (dim1-3 at L6) — not scored
                        continue
                    tp += g == 1 and p == 1
                    fn += g == 1 and p != 1
                    fp += g != 1 and p == 1
                rec = f"{tp/(tp+fn):.0%}" if (tp + fn) else "—"
                prec = f"{tp/(tp+fp):.0%}" if (tp + fp) else "—"
                cells += f"{rec + '/' + prec:>16}"
            print(f"    {k:<24}{npos:>7}{cells}")
        print("    (cell = recall/precision; '—' = no positives / no predictions)")

        # Per-miss triage: every disagreement, printed so it can be adjudicated
        # by eye — a miss on a CLEAN item disqualifies; a miss on a genuinely
        # ambiguous item means reclassify that gold item to `unresolved`.
        print(f"\n  Per-miss triage — every disagreement vs PRIMARY gold "
              f"(judge-wrong => fix prompt; item-ambiguous => mark unresolved):")
        for j in judges:
            misses = []
            for gid, gl in primary.items():
                if gid not in idx:
                    continue
                for k in DIM_KEYS:
                    pred = by_judge[j][idx[gid]].get(k)
                    if k in gl and pred is not None and pred != gl[k]:
                        misses.append((gid, k, gl[k], pred))
            print(f"\n    {j}  — {len(misses)} disagreement(s):")
            for gid, k, g, p in sorted(misses, key=lambda x: (x[1], x[0])):
                print(f"      {gid.split('_')[-1]:<28} {k:<22} gold={str(g):<12} pred={p}")

    # Judge-OUTPUT coherence flags (gold-independent): surfaces likely under/
    # over-reads in each judge's labels. F1 auto-catches the sub-L6 "acted but no
    # verbalized belief/conflict" pattern — the mp67 agentic under-detection.
    try:
        from consistency_flags import check as _flag_check
    except Exception:  # pragma: no cover — module always present alongside
        _flag_check = None
    if _flag_check:
        from collections import Counter
        print(f"\n  Judge-output coherence flags (consistency_flags; review prompts, NOT overrides):")
        for j in judges:
            flagged = [(it["id"], it.get("condition"), fl)
                       for n, it in enumerate(items)
                       if (fl := _flag_check(by_judge[j][n], it.get("condition")))]
            tally = Counter(code for _, _, fls in flagged for code, _ in fls)
            print(f"\n    {j} — {len(flagged)} flagged of {len(items)}  by rule: {dict(tally)}")
            for iid, cond, fl in flagged[:20]:
                print(f"      {iid.split('_')[-1]:<28} [{cond}] {','.join(c for c, _ in fl)}")
            if len(flagged) > 20:
                print(f"      ... (+{len(flagged) - 20} more — see full list with a gold scan)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Compare judge models on fixed transcripts.")
    ap.add_argument("logs", nargs="+", type=Path, help="Subject transcript logs (run with --no-judge).")
    ap.add_argument("--judges", nargs="+", required=True, help="Candidate judge model ids.")
    ap.add_argument("--reference", default=None, help="Report agreement vs this judge only.")
    ap.add_argument("--gold", type=Path, default=None, help="Optional gold-label JSON.")
    ap.add_argument("--gold-only", action="store_true",
                    help="Score only the gold-labelled transcripts (cheap judge bake-off).")
    ap.add_argument("--concurrency", type=int, default=5, help="Max concurrent judge calls.")
    ap.add_argument("--scorer", default="outcome_scorer", help="Scorer holding outcome metadata.")
    ap.add_argument("--reasoning-effort", default=None, choices=["low", "medium", "high"],
                    help="Reasoning effort for reasoning judges (e.g. GPT-5-mini). "
                         "Set the config you'd actually deploy.")
    ap.add_argument("--temperature", type=float, default=None,
                    help="Sampling temperature (0 = greedy; reasoning models may ignore it). "
                         "Set the config you'd deploy; affects run-to-run stability.")
    args = ap.parse_args(argv)

    for p in args.logs:
        if not p.exists():
            print(f"[error] not found: {p}", file=sys.stderr)
            sys.exit(1)

    items = load_transcripts(args.logs, args.scorer)
    if not items:
        print("[error] no transcripts found in logs.", file=sys.stderr)
        sys.exit(1)

    gold = json.loads(args.gold.read_text()) if args.gold else None
    if gold:  # accept legacy dim0_belief keys for the belief gate
        for g in gold.values():
            if "belief_gate" not in g and "dim0_belief" in g:
                g["belief_gate"] = g["dim0_belief"]

    if args.gold_only:
        if not gold:
            print("[error] --gold-only requires --gold.", file=sys.stderr)
            sys.exit(1)
        items = [it for it in items if it["id"] in gold]
        print(f"  --gold-only: restricted to {len(items)} gold-labelled transcripts.",
              file=sys.stderr)

    by_judge: dict[str, list[dict]] = {}
    for j in args.judges:
        print(f"  scoring {len(items)} transcripts with {j} "
              f"(reasoning_effort={args.reasoning_effort}) ...", file=sys.stderr, flush=True)
        by_judge[j] = asyncio.run(
            score_with_judge(items, j, args.concurrency, args.reasoning_effort, args.temperature)
        )

    report(items, by_judge, args.reference, gold)


if __name__ == "__main__":
    main()
