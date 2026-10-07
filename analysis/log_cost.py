"""Cost of an eval run, measured from the log's token counts (not credits).

Credit deltas are useless while another job is running; the .eval log records
exact usage per model, so cost is measurable per run regardless of what else is
in flight.

    python analysis/log_cost.py logs/smoke-new/*.eval --price 5 25
    python analysis/log_cost.py logs/smoke-new/*.eval --per-episode 2660
"""
from __future__ import annotations
import argparse, glob, sys
from pathlib import Path


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("logs", nargs="+")
    ap.add_argument("--price", nargs=2, type=float, metavar=("IN", "OUT"),
                    help="$ per 1M input / output tokens for this model.")
    ap.add_argument("--per-episode", type=int, default=None,
                    help="Extrapolate to this many episodes (e.g. 2660 for a full cyber model).")
    args = ap.parse_args(argv)
    from inspect_ai.log import read_eval_log

    paths = [p for a in args.logs for p in (sorted(glob.glob(a)) if any(c in a for c in "*?[") else [a])]
    tot = {}
    for f in paths:
        log = read_eval_log(f, header_only=True)
        n = (log.results.completed_samples if log.results else 0) or 0
        for model, u in (log.stats.model_usage or {}).items():
            t = tot.setdefault(model, {"in": 0, "out": 0, "n": 0})
            t["in"] += u.input_tokens or 0
            t["out"] += u.output_tokens or 0
            t["n"] += n
    for model, t in tot.items():
        print(f"{model}")
        print(f"   episodes {t['n']:,} | input {t['in']:,} | output {t['out']:,}")
        if t["n"]:
            print(f"   per episode: {t['in']/t['n']:,.0f} in / {t['out']/t['n']:,.0f} out")
        if args.price:
            pi, po = args.price
            c = t["in"] / 1e6 * pi + t["out"] / 1e6 * po
            print(f"   cost: ${c:,.4f}" + (f"  (${c/t['n']:.4f}/episode)" if t["n"] else ""))
            if args.per_episode and t["n"]:
                print(f"   -> {args.per_episode:,} episodes ≈ ${c/t['n']*args.per_episode:,.0f}")


if __name__ == "__main__":
    main()
