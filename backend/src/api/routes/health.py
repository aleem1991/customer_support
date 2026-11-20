# src/api/routes/health.py
# Author: Suresh D R | AI Product Developer & Technology Mentor

from fastapi import APIRouter

from src.tools.database_tools import get_db
from src.utils.cache import get_redis

router = APIRouter()


@router.get("/health")
def health():
    status = {"status": "ok", "checks": {}}

    try:
        conn = get_db()
        conn.cursor().execute("SELECT 1;")
        conn.close()
        status["checks"]["rds"] = "ok"
    except Exception as e:
        status["checks"]["rds"] = f"failed: {e}"
        status["status"] = "degraded"

    r = get_redis()
    status["checks"]["redis"] = "ok" if r else "disabled_or_unreachable"

    return status
