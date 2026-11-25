# src/agents/agent_factory.py
# Author: Suresh D R | AI Product Developer & Technology Mentor
#
# Each agent = LLM + system prompt (loaded from src/prompts/) + tools.
# This file is the single place that wires those three ingredients
# together for every agent in the pipeline. Tool-less agents (sentiment,
# intent, guardrails) call the LLM directly. Tooled agents use
# create_react_agent() from LangGraph.

import os
import json

from langchain_openai import ChatOpenAI, AzureChatOpenAI
from langgraph.prebuilt import create_react_agent

from src.tools.database_tools import (
    get_customer_profile, get_customer_tickets, get_billing_history,
    search_knowledge_base, create_ticket, initiate_refund,
    update_ticket, log_action, get_churn_score,
)
from src.utils.config import settings

_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "prompts")


def load_prompt(name: str) -> str:
    path = os.path.join(_PROMPTS_DIR, f"{name}.txt")
    with open(path) as f:
        return f.read()


if getattr(settings, "AZURE_OPENAI_ENDPOINT", None):
    llm = AzureChatOpenAI(
        azure_deployment=getattr(settings, "OPENAI_DEPLOYMENT_NAME", "gpt-4o"),
        openai_api_version=getattr(settings, "OPENAI_API_VERSION", "2024-06-01"),
        azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
        api_key=settings.OPENAI_API_KEY,
        temperature=0,
        max_retries=3,
        request_timeout=30,
    )
else:
    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0, api_key=settings.OPENAI_API_KEY)

SYSTEM_RULES = load_prompt("system_rules")

SENTIMENT_PROMPT = load_prompt("sentiment")
INTENT_PROMPT = load_prompt("intent")
GUARDRAILS_PROMPT = load_prompt("guardrails")
IDENTITY_PROMPT = load_prompt("identity") + "\n\n" + SYSTEM_RULES
CHURN_PROMPT = load_prompt("churn") + "\n\n" + SYSTEM_RULES
RETRIEVAL_PROMPT = load_prompt("retrieval") + "\n\n" + SYSTEM_RULES
ACTION_PROMPT = load_prompt("action") + "\n\n" + SYSTEM_RULES
GENERATOR_PROMPT = load_prompt("generator") + "\n\n" + SYSTEM_RULES


def call_llm_json(system_prompt: str, message: str) -> dict:
    """Used by the three tool-less agents -- sends message + prompt,
    parses the JSON response."""
    resp = llm.invoke([
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": message},
    ])
    return json.loads(resp.content)


# Tool-using agents, built once at module load time
identity_agent = create_react_agent(
    llm, tools=[get_customer_profile, get_customer_tickets, get_billing_history]
)

churn_agent = create_react_agent(llm, tools=[get_churn_score])

retrieval_agent = create_react_agent(llm, tools=[search_knowledge_base])

action_agent = create_react_agent(
    llm, tools=[create_ticket, initiate_refund, update_ticket, log_action]
)
