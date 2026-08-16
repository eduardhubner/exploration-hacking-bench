"""Fire the calibrated HYBRID judge over the benchmark transcripts and persist labels.

Routing (validated in docs/JUDGE_CALIBRATION.md):
  single-turn  -> haiku-4.5 @ medium
  agentic      -> Sol       @ medium   (main-v2 only; main-v1 agentic is superseded)
  sequential   -> SKIPPED (multi-turn cognitive harness not wired; footnote arm)

L6 gating (dim1-3 -> None at level6) is applied inside _run_holistic_judge.
`consistency_flags` are recorded per transcript. Writes {id: labels} to --out,
keyed "<log_stem>:<sample_id>" (same key space as gold.json), so cognitive labels
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
_PRICE = {HAIKU: (1.0, 5.0), SOL: (5.0, 30.0)}


def _arm(path_or_id: str) -> str:
    s = path_or_id.lower()
    if "agentic" in s:
        return "agentic"
    if "sequential" in s:
        return "sequential"
    return "single_turn"


def _select_logs(log_dirs: list[str]):
    """Return (paths_to_score, skipped_note). Single-turn = all logs (offset
    appends are disjoint). Agentic = last --log-dirs entry per (model,cond) only
    (main-v1 agentic is superseded by main-v2's complete n=40). Sequential dropped."""
    from inspect_ai.log import read_eval_log
    import glob

    groups: dict[tuple, list[tuple[int, str]]] = defaultdict(list)  # (arm,model,cond)->[(dir_rank,path)]
    for rank, d in enumerate(log_dirs):
        for f in glob.glob(f"{d}/*.eval"):
            h = read_eval_log(f, header_only=True)
            if h.status != "success":
                continue
            arm = _arm(f)
            model = h.eval.model.split("/")[-1]
            cond = (h.eval.task_args or {}).get("condition", "?")
            groups[(arm, model, cond)].append((rank, f))

    paths, skipped = [], Counter()
    for (arm, model, cond), entries in groups.items():
        if cond == "baseline":  # no EH framing -> no cognitive overlay (behavior/McNemar only)
            skipped["baseline"] += len(entries)
            continue
        if arm in ("agentic", "sequential"):
            top = max(e[0] for e in entries)  # latest --log-dirs entry (dedup replicates)
            paths += [f for r, f in entries if r == top]
        else:  # single_turn: all batches (disjoint appends)
            paths += [f for _r, f in entries]
    return sorted(paths), skipped


def _sequential_items(paths):
    """One item per sequential SESSION: the full multi-turn conversation as the
    'response' for session-level, correctness-blind cognitive judging. dim4 is not
    judged here (score_action=False downstream) — it comes per-question from the
    behavioral scorer. Keyed `<stem>:<session_id>`."""
    from inspect_ai.log import read_eval_log
    from ehbench.scorers.markov_scorer import _get_system_prompt

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


def _passes_for(condition, arm="single_turn"):
    """Judge passes that actually run (mirror of _run_holistic_judge). Sequential
    skips the action pass (dim4 comes from the per-question behavioral scorer)."""
    from ehbench.scorers.markov_scorer import _valid_constructs
    v = _valid_constructs(condition)
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


def _estimate_cost(items: list[dict]) -> None:
    from ehbench.prompts_loader import load_prompt
    tok = lambda s: len(s) // 4
    sys_all = {n: tok(load_prompt(n).system_prompt) for n in
               ["judge_eh_belief", "judge_eh_cognition", "judge_eh_planning",
                "judge_eh_action", "judge_dismissal"]}
    by_judge = defaultdict(lambda: [0.0, 0.0, 0])  # judge -> [in_M, out_M, n]
    for it in items:
        judge = ARM_JUDGE[_arm(it["id"])]
        payload = tok(it["system_prompt"]) + tok(it["question"]) + tok(it["response"])
        passes = _passes_for(it.get("condition"), _arm(it["id"]))
        in_tok = sum(sys_all[p] for p in passes) + len(passes) * payload
        out_tok = len(passes) * 1200  # ~medium reasoning+visible per pass
        agg = by_judge[judge]
        agg[0] += in_tok / 1e6; agg[1] += out_tok / 1e6; agg[2] += 1
    total = 0.0
    print("\n  Cost estimate (approx; L6 cells use 3 passes):")
    for judge, (im, om, n) in by_judge.items():
        pi, po = _PRICE[judge]
        c = im * pi + om * po
        total += c
        print(f"    {judge:<40} n={n:<5} ~${c:7.2f}")
    print(f"    {'TOTAL':<40} {'':<5} ~${total:7.2f}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fire the hybrid EH judge and persist labels.")
    ap.add_argument("--log-dirs", nargs="+", required=True)
    ap.add_argument("--out", type=Path, default=Path("scored_labels.json"))
    ap.add_argument("--concurrency", type=int, default=5)
    ap.add_argument("--limit", type=int, default=None,
                    help="Score only the first N transcripts (smoke test before the full run).")
    ap.add_argument("--dry-run", action="store_true", help="Print plan + cost, spend nothing.")
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

    paths, skipped = _select_logs(args.log_dirs)
    # sequential needs the whole-conversation extractor; the rest use the
    # per-sample final-response loader.
    seq_paths = [p for p in paths if _arm(p) == "sequential"]
    other_paths = [p for p in paths if _arm(p) != "sequential"]
    items = load_transcripts([Path(p) for p in other_paths]) + _sequential_items(seq_paths)

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
          f"across {args.log_dirs}")
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

    _estimate_cost(items)
    if args.dry_run:
        print("\n  --dry-run: nothing scored. Re-run without --dry-run to fire.")
        return

    from ehbench.scorers.markov_scorer import _run_holistic_judge

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
