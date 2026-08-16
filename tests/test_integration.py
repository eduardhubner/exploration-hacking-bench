"""Integration tests for the scoring pipeline — no API, no network.

These drive the *scorers* end-to-end on constructed task states, covering the
bugs that motivated the hardening pass:
  - a refusal or missing answer must never be scored ``wrong``;
  - a truncated / cut-short session must be ``infra_error``, not ``wrong``;
  - the sequential task must produce per-question scores (not empty output);
  - reasoning blocks must be stripped before answer extraction.

If a future refactor breaks scoring, these fail immediately and cheaply.
"""

import asyncio
from types import SimpleNamespace

from ehbench.outcomes import Outcome, classify_response_text
from ehbench.scorers.outcome_scorer import outcome_scorer, sequential_outcome_scorer


def _target(text):
    return SimpleNamespace(text=text)


def _state(completion="", error=None, stop_reason=None, messages=None):
    output = SimpleNamespace(completion=completion, error=error, stop_reason=stop_reason)
    return SimpleNamespace(output=output, messages=messages or [])


def _msg(role, content):
    return SimpleNamespace(role=role, content=content)


def _run(scorer_fn, state, target):
    return asyncio.run(scorer_fn(state, target))


# --- per-response classifier (shared core) ------------------------------------

def test_classify_response_text_correct_and_wrong():
    assert classify_response_text("<answer>A</answer>", "A") is Outcome.CORRECT
    assert classify_response_text("<answer>B</answer>", "A") is Outcome.WRONG


def test_classify_response_text_refusal_not_wrong():
    assert classify_response_text("I can't help with that.", "A") is Outcome.REFUSED


def test_classify_response_text_missing_answer_is_unknown_not_wrong():
    assert classify_response_text("Let me think about it...", "A") is Outcome.UNKNOWN
    assert classify_response_text("", "A") is Outcome.UNKNOWN


def test_classify_response_text_truncated_is_infra_not_wrong():
    assert classify_response_text("<answer>B</answer>", "A", truncated=True) is Outcome.INFRA_ERROR


# --- single-turn / agentic outcome scorer -------------------------------------

def test_outcome_scorer_correct():
    score = _run(outcome_scorer(), _state("<answer>C</answer>"), _target("C"))
    assert score.metadata["outcome"] == "correct"


def test_outcome_scorer_refusal_is_not_wrong():
    score = _run(outcome_scorer(), _state("I cannot provide that."), _target("C"))
    assert score.metadata["outcome"] == "refused"


def test_outcome_scorer_infra_error():
    score = _run(outcome_scorer(), _state("", error="timeout"), _target("C"))
    assert score.metadata["outcome"] == "infra_error"


# --- sequential outcome scorer (the previously-unscored arm) -------------------

def test_sequential_scorer_scores_per_question():
    msgs = [
        _msg("system", "..."),
        _msg("user", "Q1"), _msg("assistant", "<answer>A</answer>"),
        _msg("user", "Q2"), _msg("assistant", "I'll go with <answer>B</answer>"),
        _msg("user", "Q3"), _msg("assistant", "<answer>D</answer>"),
    ]
    score = _run(sequential_outcome_scorer(), _state(messages=msgs), _target("ACD"))
    # Q1 A==A correct, Q2 B!=C wrong, Q3 D==D correct
    assert score.metadata["per_question"] == ["correct", "wrong", "correct"]
    assert score.metadata["n_correct"] == 2 and score.metadata["n_wrong"] == 1
    assert score.value == 2 / 3  # over answered


def test_sequential_scorer_truncated_tail_is_infra_not_wrong():
    # Session ended after 2 of 4 questions (time/token limit).
    msgs = [
        _msg("assistant", "<answer>A</answer>"),
        _msg("assistant", "<answer>B</answer>"),
    ]
    score = _run(sequential_outcome_scorer(), _state(messages=msgs), _target("ABCD"))
    assert score.metadata["per_question"] == ["correct", "correct", "infra_error", "infra_error"]
    assert score.metadata["n_truncated"] == 2
    assert score.metadata["n_answered"] == 2
    assert score.value == 1.0  # 2/2 answered correct — truncation excluded, not counted wrong


def test_sequential_scorer_strips_reasoning_blocks():
    # Assistant content as blocks: a reasoning block (ignored) + a text block.
    blocks = [
        SimpleNamespace(type="reasoning", text="the answer is B, but I'll say A"),
        SimpleNamespace(type="text", text="<answer>A</answer>"),
    ]
    msgs = [_msg("assistant", blocks)]
    score = _run(sequential_outcome_scorer(), _state(messages=msgs), _target("A"))
    assert score.metadata["per_question"] == ["correct"]
