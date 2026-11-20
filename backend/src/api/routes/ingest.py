# src/api/routes/ingest.py
# Author: Suresh D R | AI Product Developer & Technology Mentor
#
# This is the endpoint the Streamlit "Load Documents from S3" button calls.
# It runs synchronously here for simplicity (6 small text files take only
# a few seconds). For larger document sets in production, wrap run_ingestion()
# in a Celery task and return a job_id immediately instead.

from fastapi import APIRouter, HTTPException

from src.api.schemas import IngestResponse
from src.utils.ingest import run_ingestion

router = APIRouter()


@router.post("/ingest", response_model=IngestResponse)
def ingest_documents():
    try:
        result = run_ingestion()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")
