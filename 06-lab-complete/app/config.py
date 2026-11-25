"""
Config — 12-Factor: mọi cấu hình đọc từ biến môi trường.

Tiêu chí 9 — Config từ environment variables:
  • Đọc toàn bộ cấu hình từ môi trường, có giá trị mặc định hợp lý khi chạy local.
  • Không hard-code secret (API key thật, mật khẩu...) trong code —
    AGENT_API_KEY mặc định rỗng, bắt buộc cấp qua biến môi trường.
  • Các biến này được liệt kê đủ trong .env.example.
"""
import os
from dataclasses import dataclass


def _getenv_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _getenv_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass
class Settings:
    # Mọi giá trị đọc từ biến môi trường (12-Factor config).
    port: int = _getenv_int("PORT", 8000)
    environment: str = os.getenv("ENVIRONMENT", "development")
    debug: bool = os.getenv("DEBUG", "false").lower() in ("1", "true", "yes")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # Secret — KHÔNG có giá trị mặc định thật, phải cấp qua env.
    agent_api_key: str = os.getenv("AGENT_API_KEY", "")

    # Redis: có default non-empty để from_url() không lỗi khi chưa cấu hình,
    # nhưng app vẫn khởi động được kể cả khi không kết nối được Redis.
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Rate limit & cost guard.
    rate_limit_per_minute: int = _getenv_int("RATE_LIMIT_PER_MINUTE", 10)
    daily_budget_usd: float = _getenv_float("DAILY_BUDGET_USD", 10.0)
    monthly_budget_usd: float = _getenv_float("MONTHLY_BUDGET_USD", 0.0)


settings = Settings()
