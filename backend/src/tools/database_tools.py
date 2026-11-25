# src/tools/database_tools.py
# Author: Suresh D R | AI Product Developer & Technology Mentor
#
# Every tool here follows the same pattern: a plain Python function,
# decorated with @tool so LangGraph agents can call it, with a docstring
# that is the ONLY explanation the LLM ever sees of what the tool does.
# Each tool returns a clean dict or list of dicts -- never raw DB rows.

import os
import json
import uuid
import hashlib
import logging

import psycopg2
import boto3
from openai import OpenAI, AzureOpenAI
from langchain.tools import tool

from src.utils.cache import get_redis, cache_get, cache_set
from src.utils.config import settings

logger = logging.getLogger("support_agent.tools")

if getattr(settings, "AZURE_OPENAI_ENDPOINT", None):
    client = AzureOpenAI(
        azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
        api_key=settings.OPENAI_API_KEY,
        api_version=getattr(settings, "OPENAI_API_VERSION", "2024-06-01"),
        max_retries=3,
        timeout=30.0,
    )
else:
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
EMBED_MODEL = "text-embedding-3-large"

_chroma_collection = None  # set by load_chroma_collection() at startup


def get_db():
    return psycopg2.connect(settings.DATABASE_URL, connect_timeout=10)


def set_chroma_collection(collection):
    """Called once at startup after the Chroma collection is loaded from S3."""
    global _chroma_collection
    _chroma_collection = collection


# ──────────────────────────────────────────────────────────────────────────
# Tools that READ from RDS (PostgreSQL)
# ──────────────────────────────────────────────────────────────────────────

@tool
def get_customer_profile(customer_id: str) -> dict:
    """Get complete customer profile including name, account type,
    tenure, lifetime value and communication preferences from RDS."""
    cache_key = f"profile:{customer_id}"
    cached = cache_get(cache_key)
    if cached:
        return cached

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT customer_id,name,email,account_type,tenure_months,"
        "lifetime_value,preferred_language,communication_style "
        "FROM customers WHERE customer_id=%s",
        (customer_id,),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return {"error": "Customer not found"}

    result = {
        "customer_id": row[0], "name": row[1], "email": row[2],
        "account_type": row[3], "tenure_months": row[4],
        "lifetime_value": row[5], "preferred_language": row[6],
        "communication_style": row[7],
    }
    cache_set(cache_key, result, ttl=300)
    return result


@tool
def get_customer_tickets(customer_id: str) -> list:
    """Get the most recent 5 support tickets for a customer.
    Shows ticket ID, issue type, status, priority and description."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT ticket_id,issue_type,status,priority,description,created_at "
        "FROM tickets WHERE customer_id=%s ORDER BY created_at DESC LIMIT 5",
        (customer_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {"ticket_id": r[0], "issue_type": r[1], "status": r[2],
         "priority": r[3], "description": r[4], "created_at": str(r[5])}
        for r in rows
    ]


@tool
def get_billing_history(customer_id: str) -> list:
    """Get the last 10 billing transactions for a customer.
    Use this to check for duplicate charges, refunds, and payment history."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "SELECT txn_id,amount,type,status,date FROM transactions "
        "WHERE customer_id=%s ORDER BY date DESC LIMIT 10",
        (customer_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {"txn_id": r[0], "amount": r[1], "type": r[2], "status": r[3], "date": str(r[4])}
        for r in rows
    ]


# ──────────────────────────────────────────────────────────────────────────
# Tool that READS from ChromaDB (the RAG knowledge base)
# ──────────────────────────────────────────────────────────────────────────

@tool
def search_knowledge_base(query: str) -> list:
    """Search the policy and FAQ knowledge base for relevant information.
    Use this to find refund policies, shipping rules, warranty terms, SLAs."""
    if _chroma_collection is None:
        return [{"error": "Knowledge base not loaded yet"}]

    resp = client.embeddings.create(input=[query], model=EMBED_MODEL)
    q_emb = resp.data[0].embedding

    res = _chroma_collection.query(query_embeddings=[q_emb], n_results=5)

    out = []
    docs = res.get("documents", [[]])[0]
    metas = res.get("metadatas", [[]])[0]
    dists = res.get("distances", [[]])[0]
    for doc, meta, dist in zip(docs, metas, dists):
        out.append({
            "content": doc,
            "category": meta.get("category", ""),
            "source": meta.get("source_doc", ""),
            "similarity": round(1 - dist, 3),
        })
    return out


# ──────────────────────────────────────────────────────────────────────────
# Tools that WRITE to RDS
# ──────────────────────────────────────────────────────────────────────────

@tool
def create_ticket(customer_id: str, issue_type: str, description: str, priority: str) -> dict:
    """Create a new support ticket in the database.
    Use this when a new issue needs to be tracked and followed up."""
    ticket_id = f"TKT_{uuid.uuid4().hex[:8].upper()}"
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO tickets (ticket_id,customer_id,issue_type,description,status,priority,created_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,NOW())",
        (ticket_id, customer_id, issue_type, description, "open", priority),
    )
    conn.commit()
    conn.close()
    logger.info("ticket_created", extra={"ticket_id": ticket_id, "customer_id": customer_id})
    return {"ticket_id": ticket_id, "status": "created", "priority": priority}


@tool
def initiate_refund(customer_id: str, txn_id: str, amount: float, reason: str) -> dict:
    """Initiate a refund for a customer transaction.
    Only use when a duplicate charge or valid return is confirmed.
    Maximum automated refund limit is Rs.5000 -- enforced here in code."""
    if amount > 5000:
        return {"status": "rejected", "reason": "Exceeds automated limit. Requires human approval."}

    ref = f"REF_{uuid.uuid4().hex[:8].upper()}"
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO transactions (txn_id,customer_id,amount,type,status,date,reference) "
        "VALUES (%s,%s,%s,%s,%s,NOW(),%s)",
        (ref, customer_id, amount, "refund", "processing", reason),
    )
    conn.commit()
    conn.close()
    logger.info("refund_initiated", extra={"ref": ref, "customer_id": customer_id, "amount": amount})
    return {"refund_ref": ref, "amount": amount, "status": "processing", "eta": "3-5 business days"}


@tool
def update_ticket(ticket_id: str, status: str, resolution_summary: str) -> dict:
    """Update the status of an existing ticket.
    Use status: open / in_progress / resolved / escalated."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE tickets SET status=%s, resolution_summary=%s WHERE ticket_id=%s",
        (status, resolution_summary, ticket_id),
    )
    conn.commit()
    conn.close()
    return {"ticket_id": ticket_id, "new_status": status}


@tool
def log_action(conv_id: str, action_type: str, details: str) -> dict:
    """Log every agent action to the audit trail.
    Mandatory for compliance -- every refund, ticket, escalation must be logged."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO agent_actions (conv_id,action_type,action_details,timestamp) "
        "VALUES (%s,%s,%s,NOW())",
        (conv_id, action_type, json.dumps({"detail": details})),
    )
    conn.commit()
    conn.close()
    return {"logged": True, "action_type": action_type}


# ──────────────────────────────────────────────────────────────────────────
# Tool that calls the churn model
# ──────────────────────────────────────────────────────────────────────────

@tool
def get_churn_score(customer_id: str) -> dict:
    """Get the churn probability score for a customer.
    Returns score 0.0 to 1.0 and category LOW, MEDIUM or HIGH.
    Calls the SageMaker endpoint if configured, otherwise uses a
    deterministic fallback so the system still works in dev/test."""
    if settings.CHURN_ENDPOINT_NAME:
        try:
            sm = boto3.client("sagemaker-runtime", region_name=settings.AWS_REGION)
            payload = json.dumps({"customer_id": customer_id})
            response = sm.invoke_endpoint(
                EndpointName=settings.CHURN_ENDPOINT_NAME,
                ContentType="application/json",
                Body=payload,
            )
            result = json.loads(response["Body"].read())
            score = float(result.get("churn_score", 0.5))
        except Exception as e:
            logger.warning(f"SageMaker churn endpoint failed, using fallback: {e}")
            score = _fallback_churn_score(customer_id)
    else:
        score = _fallback_churn_score(customer_id)

    category = "HIGH" if score >= 0.70 else ("MEDIUM" if score >= 0.40 else "LOW")
    return {"customer_id": customer_id, "churn_score": round(score, 2), "churn_category": category}


def _fallback_churn_score(customer_id: str) -> float:
    seed = int(hashlib.md5(customer_id.encode()).hexdigest(), 16) % 100
    return seed / 100


ALL_TOOLS = [
    get_customer_profile, get_customer_tickets, get_billing_history,
    search_knowledge_base,
    create_ticket, initiate_refund, update_ticket, log_action,
    get_churn_score,
]
