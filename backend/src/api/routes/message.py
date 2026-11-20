# src/api/routes/message.py
# Author: Suresh D R | AI Product Developer & Technology Mentor

from fastapi import APIRouter, HTTPException

from src.api.schemas import MessageRequest, MessageResponse
from src.agents.pipeline import run_pipeline

router = APIRouter()


@router.post("/message", response_model=MessageResponse)
def handle_message(req: MessageRequest):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    try:
        result = run_pipeline(
            message=req.message,
            customer_id=req.customer_id,
            channel=req.channel,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline error: {e}")
