"""
Kết nối Redis dùng chung cho rate limiter và cost guard.

  • Đọc REDIS_URL từ config.
  • App vẫn KHỞI ĐỘNG ĐƯỢC khi Redis chưa sẵn sàng: redis-py chỉ mở kết nối
    ở lần gọi lệnh đầu tiên (lazy), nên ở đây KHÔNG ping lúc import.
  • redis_healthy() dùng cho GET /ready: Redis không kết nối được → False.
"""
import redis

from app.config import settings

# Client lazy: tạo object không mở socket ngay. socket_connect_timeout nhỏ để
# khi Redis chết thì /ready trả 503 nhanh thay vì treo.
r = redis.from_url(
    settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=2,
    retry_on_timeout=False,
)


def redis_healthy() -> bool:
    """True khi PING Redis thành công; mọi lỗi kết nối → False."""
    try:
        return bool(r.ping())
    except Exception:
        return False
