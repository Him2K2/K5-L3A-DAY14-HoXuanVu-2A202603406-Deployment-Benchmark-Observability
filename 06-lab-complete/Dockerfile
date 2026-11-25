# ============================================================
# Production multi-stage Dockerfile (tiêu chí 1)
#   • Stage builder: cài dependencies vào /install
#   • Stage runtime: base slim, chỉ copy kết quả + source, chạy user non-root
#   • HEALTHCHECK gọi GET /health
#   • CMD lắng nghe theo biến PORT (mặc định 8000), uvicorn là PID 1 (exec form)
# ============================================================

# ---- Stage 1: builder ----
FROM python:3.11-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- Stage 2: runtime ----
FROM python:3.11-slim

WORKDIR /app

# Copy dependencies đã cài từ stage builder (không kéo theo pip cache, build tools).
COPY --from=builder /install /usr/local

# Chỉ copy code cần thiết để chạy.
COPY app ./app
COPY utils ./utils

# User non-root.
RUN useradd --create-home --uid 1000 appuser
USER appuser

ENV PORT=8000 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8000')+'/health').read()" || exit 1

# uvicorn là PID 1 (exec) để nhận SIGTERM khi `docker stop` → graceful shutdown.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 2"]
