"""Compute Markov transition matrices from sequential MCQ eval logs.

Reads Inspect AI JSON eval logs (produced by the ``sequential_mcq`` task with
``sequence_state_scorer``), extracts the per-session state sequences stored in
each sample's scorer metadata, and computes:

  - A raw transition count matrix C where C[i, j] = number of times
    state S_i is immediately followed by state S_j across all sessions.
  - A row-normalised transition probability matrix T (T[i, j] = P(S_j | S_i)).
  - The persistence metric  π = Tr(T) / K  (K = number of states),
    normalised diagonal mass.  Higher π means states tend to persist.
  - Per-condition accuracy (fraction of correct MCQ answers).

Usage
-----
    python analysis/compute_transition_matrix.py logs/my_eval.json

    # Compare two conditions:
    python analysis/compute_transition_matrix.py \\
        logs/minimal_scaffolding.json logs/full_scaffolding.json

    # Pretty-print only:
    python analysis/compute_transition_matrix.py logs/my_eval.json --no-csv

Output
------
  - Prints a table and matrices to stdout.
  - Writes <log_stem>_transitions.csv with the flattened matrix rows.

Requirements: standard library only (json, pathlib, csv, argparse).
NumPy / pandas are optional — detected at import and used if available.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

try:
    import numpy as np  # type: ignore[import]

    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

N_STATES = 4  # S0 … S3 (dim4 / strategic action excluded from state space)
STATE_LABELS = [f"S{i}" for i in range(N_STATES)]


# ---------------------------------------------------------------------------
# Log parsing
# ---------------------------------------------------------------------------


def _load_eval_log(path: Path) -> dict[str, Any]:
    """Load an Inspect AI eval log via the inspect_ai library.

    Uses inspect_ai.log.read_eval_log so the format (.eval ZIP, plain JSON,
    or any future variant) is handled by the library that wrote it.
    Serialises the result back to a plain dict for uniform downstream access.
    """
    from inspect_ai.log import read_eval_log  # type: ignore[import]
    log = read_eval_log(str(path))
    return json.loads(log.model_dump_json())


def _extract_state_sequences(log: dict[str, Any]) -> list[list[int]]:
    """Return a list of state sequences, one per sample in the eval log.

    Inspect AI eval logs store results in ``log["samples"]`` (or
    ``log["results"]["samples"]`` in some versions).  Each sample has a
    ``scores`` dict keyed by scorer name; the sequence state scorer stores
    the state sequence under ``scores["sequence_state_scorer"]["metadata"]["state_sequence"]``.
    """
    samples = log.get("samples") or log.get("results", {}).get("samples", [])
    sequences: list[list[int]] = []

    for sample in samples:
        scores = sample.get("scores", {})
        scorer_data = scores.get("sequence_state_scorer", {})
        metadata = scorer_data.get("metadata", {})
        seq = metadata.get("state_sequence")
        if seq is not None:
            sequences.append([int(s) for s in seq])

    return sequences


# ---------------------------------------------------------------------------
# Matrix computation
# ---------------------------------------------------------------------------


def build_count_matrix(sequences: list[list[int]], n_states: int = N_STATES) -> list[list[int]]:
    """Build a raw transition count matrix from state sequences.

    C[i][j] = number of times state i is immediately followed by state j,
    aggregated across all sessions.
    """
    C: list[list[int]] = [[0] * n_states for _ in range(n_states)]
    for seq in sequences:
        for s_from, s_to in zip(seq[:-1], seq[1:]):
            if 0 <= s_from < n_states and 0 <= s_to < n_states:
                C[s_from][s_to] += 1
    return C


def normalise_rows(C: list[list[int]]) -> list[list[float]]:
    """Row-normalise count matrix to produce transition probabilities.

    Rows with zero total count are left as uniform 1/n (unknown) to avoid
    division-by-zero; callers should note this in reporting.
    """
    n = len(C)
    T: list[list[float]] = []
    for row in C:
        total = sum(row)
        if total == 0:
            T.append([1.0 / n] * n)
        else:
            T.append([v / total for v in row])
    return T


def persistence(T: list[list[float]]) -> float:
    """Normalised trace of the transition matrix.

    π = Tr(T) / K  where K = number of states.
    Range: [1/K, 1].  π = 1 means perfect persistence (absorbing states);
    π = 1/K means maximally non-persistent (uniform transitions).
    """
    diag_sum = sum(T[i][i] for i in range(len(T)))
    return diag_sum / len(T)


# ---------------------------------------------------------------------------
# Accuracy extraction
# ---------------------------------------------------------------------------


def extract_accuracy(log: dict[str, Any]) -> float | None:
    """Return the mean accuracy across all sessions in the log, or None."""
    samples = log.get("samples") or log.get("results", {}).get("samples", [])
    accs: list[float] = []
    for sample in samples:
        scores = sample.get("scores", {})
        scorer_data = scores.get("sequence_state_scorer", {})
        metadata = scorer_data.get("metadata", {})
        acc = metadata.get("accuracy")
        if acc is not None:
            accs.append(float(acc))
    return sum(accs) / len(accs) if accs else None


# ---------------------------------------------------------------------------
# Printing helpers
# ---------------------------------------------------------------------------


def _fmt_row(label: str, values: list, width: int = 7) -> str:
    cells = "  ".join(f"{v:{width}.3f}" if isinstance(v, float) else f"{v:{width}d}" for v in values)
    return f"  {label:<6}{cells}"


def print_matrix(
    M: list[list],
    title: str,
    labels: list[str] = STATE_LABELS,
    is_float: bool = True,
) -> None:
    print(f"\n{title}")
    header = "  " + " " * 6 + "  ".join(f"{lb:>7}" for lb in labels)
    print(header)
    print("  " + "-" * (len(header) - 2))
    for i, row in enumerate(M):
        print(_fmt_row(labels[i], row, width=7))


def print_summary(
    log_path: Path,
    sequences: list[list[int]],
    C: list[list[int]],
    T: list[list[float]],
    pi: float,
    accuracy: float | None,
) -> None:
    print(f"\n{'=' * 60}")
    print(f"  Log:          {log_path.name}")
    print(f"  Sessions:     {len(sequences)}")
    print(f"  Total transitions: {sum(sum(row) for row in C)}")
    print(f"  Persistence π: {pi:.4f}  (range [1/{N_STATES}={1/N_STATES:.3f}, 1.000])")
    if accuracy is not None:
        print(f"  Mean accuracy: {accuracy:.1%}")
    print_matrix(C, title="Transition counts C[i, j]", is_float=False)
    print_matrix(T, title="Transition probabilities T[i, j]  (row = from, col = to)")


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------


def write_csv(log_path: Path, T: list[list[float]], pi: float, accuracy: float | None) -> Path:
    """Write the flattened transition matrix to CSV next to the log."""
    out = log_path.with_name(log_path.stem + "_transitions.csv")
    rows: list[dict] = []
    for i, from_label in enumerate(STATE_LABELS):
        for j, to_label in enumerate(STATE_LABELS):
            rows.append(
                {
                    "from_state": from_label,
                    "to_state": to_label,
                    "probability": T[i][j],
                    "persistence_pi": pi,
                    "mean_accuracy": accuracy if accuracy is not None else "",
                    "log": log_path.name,
                }
            )
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Compute Markov transition matrices from sequential MCQ eval logs."
    )
    parser.add_argument(
        "logs",
        nargs="+",
        type=Path,
        help="Path(s) to Inspect AI JSON eval log files.",
    )
    parser.add_argument(
        "--no-csv",
        action="store_true",
        default=False,
        help="Skip writing CSV output files.",
    )
    parser.add_argument(
        "--min-sequences",
        type=int,
        default=1,
        help="Warn if a log contains fewer sequences than this (default: 1).",
    )
    args = parser.parse_args(argv)

    all_ok = True
    for log_path in args.logs:
        if not log_path.exists():
            print(f"[error] File not found: {log_path}", file=sys.stderr)
            all_ok = False
            continue

        log = _load_eval_log(log_path)
        sequences = _extract_state_sequences(log)

        if not sequences:
            print(
                f"[warning] No state sequences found in {log_path.name} — "
                "was the eval run with sequence_state_scorer?",
                file=sys.stderr,
            )
            all_ok = False
            continue

        if len(sequences) < args.min_sequences:
            print(
                f"[warning] {log_path.name}: only {len(sequences)} sequences "
                f"(expected ≥ {args.min_sequences})",
                file=sys.stderr,
            )

        C = build_count_matrix(sequences)
        T = normalise_rows(C)
        pi = persistence(T)
        accuracy = extract_accuracy(log)

        print_summary(log_path, sequences, C, T, pi, accuracy)

        if not args.no_csv:
            out = write_csv(log_path, T, pi, accuracy)
            print(f"\n  CSV written → {out}")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
