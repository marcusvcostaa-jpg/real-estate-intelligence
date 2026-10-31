import logging

import redis
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.session import get_db

router = APIRouter(tags=["health"])
log = logging.getLogger(__name__)


@router.get("/health")
def health(response: Response, db: Session = Depends(get_db)) -> dict:
    checks = {}
    try:
        db.execute(text("SELECT 1"))
        checks["db"] = "ok"
    except Exception:
        log.exception("health: database check failed")
        checks["db"] = "error"
    try:
        redis.Redis.from_url(get_settings().redis_url, socket_timeout=2).ping()
        checks["redis"] = "ok"
    except Exception:
        log.exception("health: redis check failed")
        checks["redis"] = "error"
    healthy = all(v == "ok" for v in checks.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if healthy else "degraded", **checks}
