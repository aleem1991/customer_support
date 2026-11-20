# src/agents/nodes.py
# Author: Suresh D R | AI Product Developer & Technology Mentor
#
# One function per node in the pipeline. Each takes the current state,
# does its one job, and returns the updated state. This is the production
# version of the same logic proven out in NB04 -- identical agent and
# tool code, just organised into importable functions instead of notebook
# cells.

import logging

from src.agents.state import SupportState
from src.agents.agent_factory import (
    call_llm_json, identity_agent, churn_agent, retrieval_agent,
    action_agent, llm, GUARDRAILS_PROMPT, SENTIMENT_PROMPT, INTENT_PROMPT,
    GENERATOR_PROMPT, IDENTITY_PROMPT, CHURN_PROMPT, RETRIEVAL_PROMPT,
    ACTION_PROMPT,
)
from src.tools.database_tools import (
    get_customer_profile, get_customer_tickets, get_billing_history,
    search_knowledge_base, get_churn_score,
)

logger = logging.getLogger("support_agent.pipeline")


def guardrails_node(state: SupportState) -> SupportState:
    result = call_llm_json(GUARDRAILS_PROMPT, state["message"])
    state["guardrail_blocked"] = not result.get("safe", True)
    state["block_reason"] = result.get("reason", "")
    if state["guardrail_blocked"]:
        logger.warning(f"Guardrail blocked message: {state['block_reason']}")
    return state


def identity_node(state: SupportState) -> SupportState:
    cid = state["customer_id"]
    # Calling tools directly (not through the agent wrapper) keeps this
    # node fast and deterministic -- the identity_agent object above is
    # still exercised and tested in NB03/tests for agent-level behaviour,
    # but the production node calls tools directly for speed and reliability.
    state["customer_data"] = get_customer_profile.invoke({"customer_id": cid})
    state["open_tickets"] = get_customer_tickets.invoke({"customer_id": cid})
    state["billing_data"] = get_billing_history.invoke({"customer_id": cid})
    return state


def churn_node(state: SupportState) -> SupportState:
    result = get_churn_score.invoke({"customer_id": state["customer_id"]})
    state["churn_score"] = result["churn_score"]
    state["churn_category"] = result["churn_category"]
    return state


def sentiment_node(state: SupportState) -> SupportState:
    result = call_llm_json(SENTIMENT_PROMPT, state["message"])
    state["customer_sentiment"] = result["sentiment"]
    state["sentiment_score"] = result["score"]
    state["priority"] = result["priority"]
    if state.get("churn_category") == "HIGH" and state["priority"] in ["LOW", "MEDIUM"]:
        state["priority"] = "HIGH"
    return state


def intent_node(state: SupportState) -> SupportState:
    result = call_llm_json(INTENT_PROMPT, state["message"])
    state["customer_intent"] = result["intent"]
    return state


def retrieval_node(state: SupportState) -> SupportState:
    chunks = search_knowledge_base.invoke({"query": state["message"]})
    state["retrieved_chunks"] = chunks
    return state


def generator_node(state: SupportState) -> SupportState:
    customer = state.get("customer_data", {})
    chunks = state.get("retrieved_chunks", [])
    policy = " | ".join([c.get("content", "")[:200] for c in chunks[:3]])
    billing = state.get("billing_data", [])
    tickets = state.get("open_tickets", [])

    dup_charges = [t for t in billing if t.get("status") == "duplicate"]
    open_tkts = [t for t in tickets if t.get("status") == "open"]

    context = (
        f"Customer: {customer.get('name','')} | Type: {customer.get('account_type','')} | "
        f"Tenure: {customer.get('tenure_months','')} months | "
        f"Churn risk: {state.get('churn_category','')} | "
        f"Open tickets: {len(open_tkts)} | "
        f"Duplicate charges found: {len(dup_charges)} | "
        f"Communication style: {customer.get('communication_style','formal')} | "
        f"Sentiment: {state.get('customer_sentiment','NEUTRAL')}"
    )
    full_prompt = f"{GENERATOR_PROMPT}\n\nCustomer context: {context}\nPolicy text: {policy}"

    resp = llm.invoke([
        {"role": "system", "content": full_prompt},
        {"role": "user", "content": state["message"]},
    ])
    state["final_response"] = resp.content
    return state


def executor_node(state: SupportState) -> SupportState:
    from src.tools.database_tools import create_ticket, initiate_refund, log_action

    actions = []
    billing = state.get("billing_data", [])
    intent = state.get("customer_intent", "")
    cid = state["customer_id"]
    conv_id = state["conv_id"]

    dup_charges = [t for t in billing if t.get("status") == "duplicate"]
    for dup in dup_charges[:1]:
        result = initiate_refund.invoke({
            "customer_id": cid, "txn_id": dup["txn_id"],
            "amount": float(dup["amount"]), "reason": "duplicate_charge_confirmed",
        })
        actions.append({"type": "refund", "result": result})
        log_action.invoke({"conv_id": conv_id, "action_type": "refund_initiated",
                            "details": f"Rs.{dup['amount']}"})

    if intent in ["billing_dispute", "technical_issue", "complaint", "order_status"]:
        tkts = state.get("open_tickets", [])
        open_tkts = [t for t in tkts if t.get("status") == "open"]
        if not open_tkts:
            result = create_ticket.invoke({
                "customer_id": cid, "issue_type": intent,
                "description": state["message"][:200],
                "priority": state.get("priority", "medium").lower(),
            })
            actions.append({"type": "ticket", "result": result})
            log_action.invoke({"conv_id": conv_id, "action_type": "ticket_created", "details": intent})

    state["actions_taken"] = actions
    return state


def escalation_node(state: SupportState) -> SupportState:
    msg_lower = state["message"].lower()
    should_escalate = (
        state.get("customer_sentiment") == "VERY_NEGATIVE"
        or state.get("customer_intent") == "cancellation_threat"
        or state.get("churn_category") == "HIGH"
        or "consumer court" in msg_lower
        or "manager" in msg_lower
    )
    state["escalate_to_human"] = should_escalate
    return state
