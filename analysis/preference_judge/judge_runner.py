"""Shared runner for the preference-arm reasoning judges (Judge A mechanism,
Judge B semantics), used by both calibration tiers (boundary + dev bake-off).

Loads a FROZEN judge YAML (frozen/*.vN.yaml), renders its system/user prompts for
one record, calls the judge model through Inspect's provider layer (OpenRouter via
the openai/ prefix, same as run_sweep.py), and parses the output with the frozen
parsers. Deterministic parsing; the only nondeterminism is the judge model call.

Not frozen itself — this is harness code. The scored config is (frozen YAML +
parsers.py), pinned by MANIFEST.txt.
"""
from __future__ import annotations

import os
# Judge models are addressed through OpenRouter; without this the OpenAI client
# defaults to platform.openai.com and 401s on an sk-or-... key.
os.environ.setdefault("OPENAI_BASE_URL", "https://openrouter.ai/api/v1")

from pathlib import Path
import yaml

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from parsers import parse_mechanism, parse_semantics, MECHANISM_FIELDS  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
FROZEN = ROOT / "data/preference/judge_calibration/frozen"

# user_prompt.format() fields required per judge
_FIELDS = {
    "mechanism": ("x_label", "y_label", "system_prompt_used", "question", "response"),
    "semantics": ("question", "intended_answer", "intended_rationale", "reasoning_text"),
}
_PARSE = {"mechanism": parse_mechanism, "semantics": parse_semantics}


def load_frozen(judge: str, version: str = "v2") -> tuple[str, str]:
    """Return (system_prompt, user_prompt_template) from the frozen YAML."""
    path = FROZEN / f"judge_preference_{judge}.{version}.yaml"
    cfg = yaml.safe_load(path.read_text())
    return cfg["system_prompt"], cfg["user_prompt"]


def _render_user(template: str, judge: str, rec: dict) -> str:
    vals = {}
    for f in _FIELDS[judge]:
        v = rec.get(f)
        if v is None and judge == "semantics" and f == "intended_answer":
            v = rec.get("gold")                       # dev records carry `gold`
        if v is None and judge == "semantics" and f == "intended_rationale":
            v = rec.get("intended_rationale") or ""   # optional annotation
        vals[f] = "" if v is None else str(v)
    return template.format(**vals)


async def run_one(model, judge: str, rec: dict, *, reasoning_effort=None, temperature=None) -> dict:
    """Call the judge on one record. Returns
    {labels: {field: value|None}, status: {field: ok|invalid|unparsed}, ok: bool,
     raw: completion}. `model` is an Inspect model object (from get_model)."""
    from inspect_ai.model import ChatMessageSystem, ChatMessageUser, GenerateConfig

    system_prompt, user_tmpl = load_frozen(judge, rec.get("_version", "v2"))
    user = _render_user(user_tmpl, judge, rec)
    out = await model.generate(
        [ChatMessageSystem(content=system_prompt), ChatMessageUser(content=user)],
        config=GenerateConfig(reasoning_effort=reasoning_effort, temperature=temperature),
    )
    raw = out.completion or ""
    labels, status = _PARSE[judge](raw)
    ok = all(s != "unparsed" for s in status.values())
    return {"labels": labels, "status": status, "ok": ok, "raw": raw}


def judge_fields(judge: str) -> list[str]:
    return list(MECHANISM_FIELDS) if judge == "mechanism" else ["intended_task_interpretation"]
