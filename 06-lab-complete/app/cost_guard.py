"""
Cost guard (tiêu chí 8).

  • Cộng dồn chi phí LLM (tính theo token) vào Redis (theo ngày và theo tháng).
  • Tổng chi phí vượt DAILY_BUDGET_USD (hoặc MONTHLY_BUDGET_USD) → HTTP 402.
"""
import time

from fastapi import HTTPException, status

from app.config import settings
from app.redis_client import r

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006


def _daily_key() -> str:
    return "cost:daily:" + time.strftime("%Y-%m-%d", time.gmtime())


def _monthly_key() -> str:
    return "cost:monthly:" + time.strftime("%Y-%m", time.gmtime())


def _spent(key: str) -> float:
    try:
        val = r.get(key)
        return float(val) if val else 0.0
    except Exception:
        return 0.0


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    daily_budget = settings.daily_budget_usd
    monthly_budget = settings.monthly_budget_usd

    if daily_budget and daily_budget > 0 and _spent(_daily_key()) >= daily_budget:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Daily budget of ${daily_budget} exceeded",
        )
    if monthly_budget and monthly_budget > 0 and _spent(_monthly_key()) >= monthly_budget:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=f"Monthly budget of ${monthly_budget} exceeded",
        )


def estimate_tokens(text: str) -> int:
    """Ước lượng thô số token (~4 ký tự / token)."""
    return max(1, len(text) // 4)


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí request vào tổng (daily + monthly), trả về chi phí request."""
    cost = (input_tokens / 1000 * PRICE_INPUT_PER_1K
            + output_tokens / 1000 * PRICE_OUTPUT_PER_1K)
    try:
        pipe = r.pipeline()
        dk, mk = _daily_key(), _monthly_key()
        pipe.incrbyfloat(dk, cost)
        pipe.expire(dk, 60 * 60 * 24 * 2)       # giữ 2 ngày
        pipe.incrbyfloat(mk, cost)
        pipe.expire(mk, 60 * 60 * 24 * 40)      # giữ 40 ngày
        pipe.execute()
    except Exception:
        # Không chặn request chỉ vì ghi nhận chi phí lỗi.
        pass
    return cost
