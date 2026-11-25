"""
Rate limiting (tiêu chí 7).

  • Mỗi API key tối đa RATE_LIMIT_PER_MINUTE request trong 60 giây (sliding window).
  • Vượt giới hạn → HTTP 429, kèm header Retry-After.
  • State lưu trong Redis (sorted set) để mọi worker / instance dùng chung và
    vẫn còn sau khi restart agent (script chấm restart agent để kiểm tra stateless).
"""
import secrets
import time

from fastapi import HTTPException, status

from app.config import settings
from app.redis_client import r

WINDOW_SECONDS = 60


def check_rate_limit(key: str) -> None:
    """Đếm số request của `key` trong 60s qua Redis sorted set; vượt → 429."""
    limit = settings.rate_limit_per_minute
    redis_key = f"ratelimit:{key}"
    now = time.time()
    window_start = now - WINDOW_SECONDS

    # Dọn các entry cũ, rồi đếm số request còn trong cửa sổ.
    pipe = r.pipeline()
    pipe.zremrangebyscore(redis_key, 0, window_start)
    pipe.zcard(redis_key)
    _, current = pipe.execute()

    if current >= limit:
        # Lấy entry cũ nhất còn trong cửa sổ để tính thời điểm được phép gọi lại.
        oldest = r.zrange(redis_key, 0, 0, withscores=True)
        retry_after = WINDOW_SECONDS
        if oldest:
            retry_after = max(1, int(oldest[0][1] + WINDOW_SECONDS - now))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(retry_after)},
        )

    # Ghi nhận request này (member duy nhất để không đè nhau trong cùng ms).
    member = f"{now}:{secrets.token_hex(6)}"
    pipe = r.pipeline()
    pipe.zadd(redis_key, {member: now})
    pipe.expire(redis_key, WINDOW_SECONDS)
    pipe.execute()
