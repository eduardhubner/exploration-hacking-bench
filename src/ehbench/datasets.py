"""Shared dataset registry.

Single source of truth for the MCQ datasets used across tasks, plus the
**domain** label used as the coupling anchor in the agentic discovery files
(the `{domain}` placeholder, substituted at read-time like `{model_name}`).

All datasets are WMDP. Belief credibility lives in the CONTENT, not the file
framing: the model reads the actual questions, so a harmless set (e.g. general
MMLU) cannot sustain the restricted-capability framing no matter how the files
are worded — the content contradicts the claim and the model clocks it. So we
stay on genuinely restricted content and instead pick *within* WMDP to manage
the access problem.

The trade-off is irreducible — the content that backs the threat (credible
belief) is the content that trips provider content filters (blocked access).
WMDP-bio maxes both. WMDP-cyber / wmdp-chem keep the content credible while
typically being filtered less aggressively than bio, so they carry the
filter-safe-ish role. Don't guess the operating point: measure it — `filtered`
outcome rate (access) and the Dim0 belief rate (credibility) are both recorded,
so pick the dataset off real numbers on a small pilot.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DatasetSpec:
    path: str
    name: str
    split: str
    domain: str  # coupling anchor for {domain} substitution in discovery files


DATASETS: dict[str, DatasetSpec] = {
    # Maximal believability, but most filter-prone (access-blocking).
    "wmdp-bio": DatasetSpec("cais/wmdp", "wmdp-bio", "test", "biosecurity and virology"),
    # Credible content, typically filtered less than bio — the working compromise.
    "wmdp-cyber": DatasetSpec("cais/wmdp", "wmdp-cyber", "test", "offensive cybersecurity"),
    "wmdp-chem": DatasetSpec("cais/wmdp", "wmdp-chem", "test", "chemical security"),
}


def get_dataset(name: str) -> DatasetSpec:
    if name not in DATASETS:
        raise ValueError(f"Unknown dataset '{name}'. Available: {sorted(DATASETS)}")
    return DATASETS[name]
