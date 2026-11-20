# tests/test_pipeline_routing.py
# Author: Suresh D R | AI Product Developer & Technology Mentor

from src.agents.pipeline import _route_after_guardrails, _route_after_escalation


def test_route_blocked_when_guardrail_flags():
    state = {"guardrail_blocked": True}
    assert _route_after_guardrails(state) == "blocked"


def test_route_continue_when_guardrail_clears():
    state = {"guardrail_blocked": False}
    assert _route_after_guardrails(state) == "continue"


def test_route_escalate_when_flagged():
    state = {"escalate_to_human": True}
    assert _route_after_escalation(state) == "escalate"


def test_route_resolve_when_not_flagged():
    state = {"escalate_to_human": False}
    assert _route_after_escalation(state) == "resolve"
