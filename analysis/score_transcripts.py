"""Fire the calibrated HYBRID judge over the benchmark transcripts and persist labels.

Routing (validated in docs/JUDGE_CALIBRATION.md):
  single-turn  -> haiku-4.5 @ medium
  agentic      -> Sol       @ medium   (main-v2 only; main-v1 agentic is superseded)
  sequential   -> SKIPPED (multi-turn cognitive harness not wired; footnote arm)

L6 gating (dim1-3 -> None at level6) is applied inside _run_holistic_judge.
`consistency_flags` are recorded per transcript. Writes {id: labels} to --out,
keyed "<log_stem>:<sample_id>" (same key space as data/gold/gold.json), so cognitive labels
join the behavioral outcomes by id. RESUMABLE: ids already in --out are skipped.

    # see the plan + cost, spend nothing:
    python analysis/score_transcripts.py --log-dirs logs/main-v1 logs/main-v2 \
        --out scored_labels.json --dry-run
    # fire:
    python analysis/score_transcripts.py --log-dirs logs/main-v1 logs/main-v2 \
        --out scored_labels.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

HAIKU = "openai/anthropic/claude-haiku-4.5"
SOL = "openai/openai/gpt-5.6-sol"
ARM_JUDGE = {"single_turn": HAIKU, "agentic": SOL, "sequential": SOL}  # long transcripts -> Sol
EFFORT = "medium"
# OpenRouter $/M (input, output) for the cost estimate


def _arm(path_or_id: str) -> str:
    s = path_or_id.lower()
    if "agentic" in s:
        return "agentic"
    if "sequential" in s:
        return "sequential"
    return "single_turn"


def _select_from_index(index=Path("data/episode_index.jsonl"), cap=None, domains=None, conditions=None, models=None):
    """Which (log, sample) to judge, from the canonical index.

    Replaces the old directory-precedence heuristic. That version kept only the
    highest-ranked --log-dirs entry per agentic cell, which was right when
    main-v1/main-v2 agentic were replicates — but after the top-up rounds 66 of
    150 agentic cells span several dirs with partly DISJOINT item ranges, so it
    silently dropped most of their episodes. The index resolves duplicates per
    EPISODE (item id), which is the correct unit.

    cap: keep at most `cap` items per cell, chosen by ASCENDING item_id — an
    outcome-blind rule. The behavioural axis still uses every pair (plan §2 says
    never truncate); only this cognitive overlay is capped, for cost.
    """
    rows = [json.loads(l) for l in index.read_text().splitlines()]
    rows = [r for r in rows if not r["superseded"] and r["condition"] != "baseline"]
    if domains:
        rows = [r for r in rows if r["domain"] in domains]
    if conditions:
        rows = [r for r in rows if r["condition"] in conditions]
    if models:
        rows = [r for r in rows if r["model"] in models]
    skipped = Counter()
    keep, by_cell = [], defaultdict(list)
    for r in rows:
        if r["arm"] == "sequential":
            skipped["sequential"] += 1      # multi-turn cognitive harness not wired
            continue
        by_cell[(r["domain"], r["arm"], r["model"], r["condition"])].append(r)
    # Cap on JUDGEABLE items, not attempted ones. A filtered/errored episode has
    # no content, so counting it toward the cap silently shrinks the cell: opus on
    # bio is ~66% filtered, so "first 100 attempted" yielded only 34-43 judgeable
    # transcripts even though the top-up rounds had deliberately collected enough
    # items to reach 100. The eligible set is intersected ACROSS the group's
    # conditions so every rung of the ladder still judges the SAME items.
    by_group = defaultdict(list)
    for cell in by_cell:
        by_group[cell[:3]].append(cell)
    for grp, cells_in in by_group.items():
        per_cond = [{r["item_id"] for r in by_cell[c]
                     if not r["error"] and r["outcome"] != "filtered"} for c in cells_in]
        eligible = set.intersection(*per_cond) if per_cond else set()
        chosen = set(sorted(eligible)[:cap]) if cap else eligible
        for c in cells_in:
            rs = sorted(by_cell[c], key=lambda r: r["item_id"])
            skipped["over_cap"] += sum(1 for r in rs if r["item_id"] not in chosen)
            keep += [r for r in rs if r["item_id"] in chosen]
    return keep, skipped


def _sequential_items(paths):
    """One item per sequential SESSION: the full multi-turn conversation as the
    'response' for session-level, correctness-blind cognitive judging. dim4 is not
    judged here (score_action=False downstream) — it comes per-question from the
    behavioral scorer. Keyed `<stem>:<session_id>`."""
    from inspect_ai.log import read_eval_log
    from ehbench.scorers.holistic_judge import _get_system_prompt

    def _txt(c):
        return c if isinstance(c, str) else " ".join(
            getattr(p, "text", "") for p in (c or []) if getattr(p, "text", None))

    items = []
    for p in paths:
        stem = Path(p).stem
        log = read_eval_log(str(p))
        cond = (log.eval.task_args or {}).get("condition")
        for s in (log.samples or []):
            convo = "\n\n".join(f"[{m.role}]\n{_txt(m.content)}" for m in s.messages
                                if m.role in ("user", "assistant"))
            items.append({"id": f"{stem}:{s.id}",
                          "system_prompt": _get_system_prompt(s.messages),
                          "question": "(sequential session — full transcript follows)",
                          "response": convo, "correct_answer": "", "model_answer": "",
                          "is_correct": False, "condition": cond})
    return items


def _passes_for(condition, arm="single_turn", only=None):
    """Judge passes that actually run (mirror of _run_holistic_judge). Sequential
    skips the action pass (dim4 comes from the per-question behavioral scorer).
    `only` mirrors --passes so the cost estimate matches what will be spent."""
    from ehbench.scorers.holistic_judge import _valid_constructs
    v = _valid_constructs(condition)
    if only is not None:
        keep = {"belief": {"belief"}, "cognition": {"dim1", "dim2"},
                "planning": {"dim3"}, "action": {"dim4"},
                "dismissal": {"premise", "decoupling"}}
        v = v & set().union(*(keep[o] for o in only))
    passes = []
    if "belief" in v:
        passes.append("judge_eh_belief")
    if v & {"dim1", "dim2"}:
        passes.append("judge_eh_cognition")
    if "dim3" in v:
        passes.append("judge_eh_planning")
    if "dim4" in v and arm != "sequential":
        passes.append("judge_eh_action")
    if v & {"premise", "decoupling"}:
        passes.append("judge_dismissal")
    return passes


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fire the hybrid EH judge and persist labels.")
    ap.add_argument("--log-dirs", nargs="+", default=None,
                    help="Deprecated: selection now comes from "
                         "data/episode_index.jsonl (analysis/build_index.py).")
    ap.add_argument("--out", type=Path, default=Path("scored_labels.json"))
    ap.add_argument("--concurrency", type=int, default=5)
    ap.add_argument("--limit", type=int, default=None,
                    help="Score only the first N transcripts (smoke test before the full run).")
    ap.add_argument("--dry-run", action="store_true", help="Print plan + cost, spend nothing.")
    ap.add_argument("--passes", nargs="+", default=None,
                    choices=["belief", "cognition", "planning", "action", "dismissal"],
                    help="Run only these judge passes. Use when one prompt changed "
                         "(e.g. --passes dismissal after neutralizing judge_dismissal) "
                         "instead of re-paying for the four that did not.")
    ap.add_argument("--cap", type=int, default=None,
                    help="Max items per cell, by ascending item_id (outcome-blind). "
                         "Behavioural analysis keeps all pairs; this caps only the "
                         "cognitive overlay.")
    ap.add_argument("--domains", nargs="+", default=None, choices=["bio", "chem", "cyber"],
                    help="Restrict to these domains.")
    ap.add_argument("--models", nargs="+", default=None,
                    help="Restrict to these model short-names (index `model` field), "
                         "e.g. kimi-k3-20260715. Design-blind selection.")
    ap.add_argument("--conditions", nargs="+", default=None,
                    help="Restrict to these conditions (exact task_args.condition names). "
                         "Selecting by CONDITION is outcome-blind — it is a design variable — "
                         "so a staged run stays statistically clean. Never select cells by "
                         "their behavioural result.")
    ap.add_argument("--retry-parse-fails", action="store_true",
                    help="Drop already-scored entries with judge_parse_ok=False so they are "
                         "re-scored on resume (recovers transient parse failures).")
    ap.add_argument("--parse-fail-judge", default=None,
                    help="With --retry-parse-fails, re-score the dropped parse-fail items with "
                         "this judge instead of the arm default (e.g. Sol for persistent haiku "
                         "parse failures). Other pending items keep their arm judge.")
    args = ap.parse_args(argv)

    from judge_bakeoff import load_transcripts
    from consistency_flags import check as flag_check

    rows, skipped = _select_from_index(cap=args.cap, domains=args.domains,
                                      conditions=args.conditions, models=args.models)
    want = {r["key"] for r in rows}
    paths = sorted({f"logs/{r['log_dir']}/{r['log_stem']}.eval" for r in rows})
    # Load every transcript in the selected logs, then keep only the episodes the
    # index actually selected (a log can hold items above the cap, or superseded
    # duplicates of items resolved to another directory).
    items = [it for it in load_transcripts([Path(p) for p in paths]) if it["id"] in want]

    # Never pay to judge a transcript with no content. A provider-filtered or
    # errored sample has an empty response: every pass would score it from
    # nothing, defaulting to 0/unstated, which is indistinguishable from a
    # genuine null and costs real money. (make_gold_sheet.py drops these for the
    # same reason.) They stay in the behavioural analysis as `filtered`/
    # `infra_error` outcomes — this only excludes them from the cognitive overlay.
    empty = [it for it in items if not (it.get("response") or "").strip()]
    if empty:
        items = [it for it in items if (it.get("response") or "").strip()]
        skipped["empty_response"] = len(empty)

    if args.limit:  # smoke test: a balanced slice so BOTH judges get exercised
        byarm = defaultdict(list)
        for it in items:
            byarm[_arm(it["id"])].append(it)
        per = max(1, args.limit // max(1, len(byarm)))
        items = [it for arm in byarm for it in byarm[arm][:per]]
        print(f"  --limit {args.limit}: smoke-testing {len(items)} transcripts "
              f"({per}/arm across {list(byarm)})")

    # plan summary
    plan = Counter((_arm(it["id"]), ARM_JUDGE[_arm(it["id"])]) for it in items)
    print(f"\n  Selected {len(items)} transcripts from {len(paths)} logs "
          f"from data/episode_index.jsonl")
    for (arm, judge), n in sorted(plan.items()):
        print(f"    {arm:<14} -> {judge:<40} {n}")
    if skipped:
        print(f"    skipped: {dict(skipped)} (deferred arms)")

    done = {}
    override_ids = set()  # ids to re-score with --parse-fail-judge
    if args.out.exists():
        done = json.loads(args.out.read_text())
        if args.retry_parse_fails:
            bad = [k for k, v in done.items() if v.get("judge_parse_ok") is False]
            for k in bad:
                del done[k]
            if args.parse_fail_judge:
                override_ids = set(bad)
                print(f"  --retry-parse-fails: dropped {len(bad)} parse-failed entries; "
                      f"re-scoring them with {args.parse_fail_judge}")
            else:
                print(f"  --retry-parse-fails: dropped {len(bad)} parse-failed entries for re-scoring")
        todo = [it for it in items if it["id"] not in done]
        print(f"  resume: {len(done)} already scored, {len(todo)} remaining")
        items = todo
    if args.dry_run:
        print(f"\n  --dry-run: {len(items)} transcripts would be scored "
              f"(measure real spend with analysis/log_cost.py after a run). "
              f"Re-run without --dry-run to fire.")
        return

    from ehbench.scorers.holistic_judge import _run_holistic_judge

    sem = asyncio.Semaphore(args.concurrency)

    async def one(it):
        arm = _arm(it["id"])
        judge = args.parse_fail_judge if it["id"] in override_ids else ARM_JUDGE[arm]
        async with sem:
            # Tolerate transient provider errors (non-JSON 5xx bodies, timeouts)
            # with a few retries; a single flaky call must not sink the whole run.
            for attempt in range(4):
                try:
                    scores = await _run_holistic_judge(
                        judge_model=judge,
                        system_prompt_used=it["system_prompt"],
                        question=it["question"],
                        correct_answer=it["correct_answer"],
                        model_answer=it["model_answer"],
                        is_correct=it["is_correct"],
                        response=it["response"],
                        reasoning_effort=EFFORT,
                        condition=it.get("condition"),
                        score_action=(arm != "sequential"),  # dim4 per-question via behavioral scorer
                        only_passes=set(args.passes) if args.passes else None,
                    )
                    break
                except Exception as e:  # noqa: BLE001 — provider/transport errors vary
                    if attempt == 3:
                        print(f"    [warn] {it['id']}: failed after retries "
                              f"({type(e).__name__}) — left unscored for a later resume",
                              flush=True)
                        return it["id"], None  # NOT persisted -> retried on resume
                    await asyncio.sleep(3 * (attempt + 1))
        rec = {k: v for k, v in scores.items() if not k.endswith("_reasoning")}
        rec.update(judge_model=judge, arm=_arm(it["id"]), condition=it.get("condition"),
                   flags=[c for c, _ in flag_check(scores, it.get("condition"))])
        return it["id"], rec

    async def run():
        n_done = n_fail = 0
        tasks = [asyncio.create_task(one(it)) for it in items]
        for fut in asyncio.as_completed(tasks):
            iid, rec = await fut
            if rec is None:  # failed after retries — leave out so a resume retries it
                n_fail += 1
                continue
            done[iid] = rec
            n_done += 1
            if n_done % 25 == 0:
                args.out.write_text(json.dumps(done, indent=2))
                print(f"    ... {n_done}/{len(items)} scored (flushed)", flush=True)
        args.out.write_text(json.dumps(done, indent=2))
        if n_fail:
            print(f"    [note] {n_fail} left unscored after retries — re-run to resume them.")

    asyncio.run(run())
    flagged = sum(1 for r in done.values() if r.get("flags"))
    print(f"\n  Done. {len(done)} transcripts -> {args.out}  "
          f"({flagged} coherence-flagged for review)")


if __name__ == "__main__":
    main()
