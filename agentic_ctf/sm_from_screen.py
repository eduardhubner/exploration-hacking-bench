#!/usr/bin/env python3
"""Print a model's reliable-capable set S_m from an InterCode screen log.

S_m = task ids solved in >= threshold (default 6/8) of baseline rollouts. Emits a
bare comma-separated id list on stdout (for shell capture); a one-line summary to
stderr. Used by run_matched_overnight.sh to feed each contrast model its own S_m.

    SM=$(uv run python agentic_ctf/sm_from_screen.py logs/screen-glm)
"""
import sys
from collections import defaultdict

from inspect_ai.log import list_eval_logs, read_eval_log
from inspect_ai.scorer import CORRECT


def s_m(log_dir: str, thresh: float = 6 / 8) -> list[int]:
    infos = list_eval_logs(log_dir)
    if not infos:
        sys.exit(f"no eval logs under {log_dir!r}")
    log = read_eval_log(sorted(getattr(i, "name", i) for i in infos)[-1])
    d: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    for s in log.samples or []:
        sc = s.scores or {}
        vals = [getattr(x, "value", x) for x in sc.values()]
        d[int(s.id)][1] += 1
        if any(v in (CORRECT, "C", 1, 1.0, True) for v in vals):
            d[int(s.id)][0] += 1
    rel = sorted(t for t, (c, n) in d.items() if n > 0 and c / n >= thresh)
    full = sorted(t for t, (c, n) in d.items() if n > 0 and c == n)
    print(
        f"[sm_from_screen] {log_dir}: |S_m|={len(rel)} (>=6/8), full8/8={len(full)}, "
        f"tasks_seen={len(d)}, n={sum(n for _, n in d.values())}",
        file=sys.stderr,
    )
    return rel


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: sm_from_screen.py <screen-log-dir>")
    print(",".join(map(str, s_m(sys.argv[1]))))
