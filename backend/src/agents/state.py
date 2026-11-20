# src/agents/state.py
# Author: Suresh D R | AI Product Developer & Technology Mentor
#
# SupportState is the single object that flows through every node in the
# LangGraph pipeline. Every node reads from it and writes back to it --
# there is no other shared memory anywhere in the system.

from typing import TypedDict


class SupportState(TypedDict):
    # Input
    message: str
    channel: str
    customer_id: str
    conv_id: str

    # Customer context (filled by identity_node)
    customer_data: dict
    open_tickets: list
    billing_data: list

    # Churn (filled by churn_node)
    churn_score: float
    churn_category: str

    # Sentiment (filled by sentiment_node)
    customer_sentiment: str
    sentiment_score: float
    priority: str

    # Intent (filled by intent_node)
    customer_intent: str

    # Retrieval (filled by retrieval_node)
    retrieved_chunks: list

    # Response (filled by generator_node)
    final_response: str

    # Actions (filled by executor_node)
    actions_taken: list

    # Routing
    escalate_to_human: bool
    guardrail_blocked: bool
    block_reason: str
