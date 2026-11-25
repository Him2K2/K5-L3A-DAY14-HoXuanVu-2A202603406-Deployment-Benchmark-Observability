"""
Production AI Agent — Part 6 Final Project.

Đạt đủ 12 tiêu chí trong README.md:
  4  GET /health   10 Structured logging (JSON)
  5  GET /ready    11 Graceful shutdown (lifespan)
  6  API key        7 Rate limit (Redis)      8 Cost guard (Redis)
  9  Config từ env
"""
import json
import logging
import sys
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, estimate_tokens, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import redis_healthy
from utils.mock_llm import ask as llm_ask


# ───────────────────────── Structured logging (tiêu chí 10) ─────────────────────────
_STANDARD = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    """Mỗi dòng log của app là 1 JSON object hợp lệ."""

    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "lvl": record.levelname,
            "logger": record.name,
            "event": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _STANDARD and not key.startswith("_"):
                data[key] = value
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        return json.dumps(data, default=str, ensure_ascii=False)


_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(JsonFormatter())
logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO),
                    handlers=[_handler], force=True)
logger = logging.getLogger("agent")


# ───────────────────────── Graceful shutdown (tiêu chí 11) ─────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: uvicorn tự xử lý SIGTERM — request đang chạy sẽ chạy xong rồi process thoát (exit 0).
    logger.info("startup", extra={"environment": settings.environment,
                                   "rate_limit_per_minute": settings.rate_limit_per_minute})
    yield
    logger.info("shutdown", extra={"event": "shutdown"})


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = None


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    logger.info("request", extra={"event": "request", "method": request.method,
                                  "path": request.url.path, "status": response.status_code,
                                  "ms": elapsed_ms})
    return response


# ───────────────────────── Health & readiness (tiêu chí 4, 5) ─────────────────────────
@app.get("/health")
def health():
    """Liveness: luôn 200 khi process còn chạy (kể cả khi Redis chưa kết nối được)."""
    return {"status": "ok"}


@app.get("/ready")
def ready():
    """Readiness: 200 khi sẵn sàng; 503 khi Redis không kết nối được."""
    if redis_healthy():
        return {"status": "ready", "redis": "up"}
    return JSONResponse(status_code=503, content={"status": "not_ready", "redis": "down"})


# ───────────────────────── Core endpoint (tiêu chí 6, 7, 8) ─────────────────────────
@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    # 6: Depends(verify_api_key) đã chặn thiếu/sai key → 401.
    # 7: vượt rate limit → 429.
    check_rate_limit(api_key)
    # 8: hết budget → 402 (kiểm tra trước khi gọi LLM).
    check_budget()

    answer = llm_ask(body.question)

    cost = record_cost(estimate_tokens(body.question), estimate_tokens(answer))
    logger.info("ask", extra={"event": "ask", "chars": len(body.question), "cost_usd": cost})
    return {"question": body.question, "answer": answer}
