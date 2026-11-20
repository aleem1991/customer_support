# src/agents/pipeline.py
# Author: Suresh D R | AI Product Developer & Technology Mentor
#
# Wires the 9 node functions from nodes.py into a single compiled
# LangGraph StateGraph. This is the exact same structure proven out in
# NB04, made importable for the FastAPI app.

import time
import uuid
import logging

from langgraph.graph import StateGraph, END

from src.agents.state import SupportState
from src.agents.nodes import (
    guardrails_node, identity_node, churn_node, sentiment_node,
    intent_node, retrieval_node, generator_node, executor_node,
    escalation_node,
)

logger = logging.getLogger("support_agent.pipeline")


def _route_after_guardrails(state: SupportState) -> str:
    return "blocked" if state.get("guardrail_blocked") else "continue"


def _route_after_escalation(state: SupportState) -> str:
    return "escalate" if state.get("escalate_to_human") else "resolve"


def build_pipeline():
    graph = StateGraph(SupportState)

    graph.add_node("guardrails", guardrails_node)
    graph.add_node("identity", identity_node)
    graph.add_node("churn", churn_node)
    graph.add_node("sentiment", sentiment_node)
    graph.add_node("intent", intent_node)
    graph.add_node("retrieval", retrieval_node)
    graph.add_node("generator", generator_node)
    graph.add_node("executor", executor_node)
    graph.add_node("escalation", escalation_node)

    graph.set_entry_point("guardrails")
    graph.add_conditional_edges("guardrails", _route_after_guardrails, {
        "blocked": END,
        "continue": "identity",
    })
    graph.add_edge("identity", "churn")
    graph.add_edge("churn", "sentiment")
    graph.add_edge("sentiment", "intent")
    graph.add_edge("intent", "retrieval")
    graph.add_edge("retrieval", "generator")
    graph.add_edge("generator", "executor")
    graph.add_edge("executor", "escalation")
    graph.add_conditional_edges("escalation", _route_after_escalation, {
        "escalate": END,
        "resolve": END,
    })

    return graph.compile()


_pipeline = None


def get_pipeline():
    global _pipeline
    if _pipeline is None:
        _pipeline = build_pipeline()
    return _pipeline


def run_pipeline(message: str, customer_id: str, channel: str = "web") -> dict:
    start = time.time()
    conv_id = f"CONV_{uuid.uuid4().hex[:8].upper()}"

    initial_state = SupportState(
        message=message, channel=channel, customer_id=customer_id, conv_id=conv_id,
        customer_data={}, open_tickets=[], billing_data=[],
        churn_score=0.0, churn_category="LOW",
        customer_sentiment="NEUTRAL", sentiment_score=0.5, priority="MEDIUM",
        customer_intent="", retrieved_chunks=[], final_response="",
        actions_taken=[], escalate_to_human=False,
        guardrail_blocked=False, block_reason="",
    )

    pipeline = get_pipeline()
    result = pipeline.invoke(initial_state)
    elapsed = round(time.time() - start, 2)

    logger.info(
        f"conv={conv_id} customer={customer_id} intent={result.get('customer_intent')} "
        f"sentiment={result.get('customer_sentiment')} escalated={result.get('escalate_to_human')} "
        f"elapsed={elapsed}s"
    )

    return {
        "conv_id": conv_id,
        "customer_name": result.get("customer_data", {}).get("name", ""),
        "account_type": result.get("customer_data", {}).get("account_type", ""),
        "intent": result.get("customer_intent", ""),
        "sentiment": result.get("customer_sentiment", ""),
        "churn_score": result.get("churn_score", 0),
        "churn_category": result.get("churn_category", ""),
        "priority": result.get("priority", ""),
        "response": result.get("final_response", ""),
        "actions_taken": result.get("actions_taken", []),
        "escalated": result.get("escalate_to_human", False),
        "blocked": result.get("guardrail_blocked", False),
        "block_reason": result.get("block_reason", ""),
        "elapsed_seconds": elapsed,
    }
