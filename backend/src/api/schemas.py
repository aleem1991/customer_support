# src/api/schemas.py
# Author: Suresh D R | AI Product Developer & Technology Mentor

from pydantic import BaseModel


class MessageRequest(BaseModel):
    message: str
    customer_id: str
    channel: str = "web"


class MessageResponse(BaseModel):
    conv_id: str
    customer_name: str
    account_type: str
    intent: str
    sentiment: str
    churn_score: float
    churn_category: str
    priority: str
    response: str
    actions_taken: list
    escalated: bool
    blocked: bool
    block_reason: str
    elapsed_seconds: float


class IngestResponse(BaseModel):
    documents_processed: int
    chunks_created: int
    embeddings_generated: int
    collection_name: str
    status: str
