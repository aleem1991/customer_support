# src/api/main.py
# Author: Suresh D R | AI Product Developer & Technology Mentor

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import message, ingest, health
from src.utils.config import settings
from src.utils.chroma_loader import load_chroma_collection
from src.tools.database_tools import set_chroma_collection

logging.basicConfig(
    level=settings.LOG_LEVEL,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("support_agent.main")

app = FastAPI(title="Intelligent Customer Support Agent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    try:
        collection = load_chroma_collection()
        set_chroma_collection(collection)
        logger.info("Startup complete -- Chroma collection loaded")
    except Exception as e:
        logger.warning(
            f"Chroma collection not loaded at startup ({e}). "
            f"This is normal if NB02 hasn't uploaded the knowledge base to S3 yet. "
            f"Once it has, restart this service."
        )


app.include_router(health.router)
app.include_router(message.router, prefix="/api")
app.include_router(ingest.router, prefix="/api")
