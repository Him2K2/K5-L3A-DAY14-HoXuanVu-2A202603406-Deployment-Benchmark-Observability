# Deployment Information — Day 14 (agent Part 6)

> **Agent Part 6** (`06-lab-complete/`) đã deploy lên Railway bằng `railway.toml`, kèm Redis. Cả 4 lệnh tự kiểm CP6 đều đạt.

## Public URL

**https://agent-api-production-f5fdfe9c.up.railway.app**

App đã được deploy từ `06-lab-complete/` bằng Railway CLI; Redis service cũng đang chạy. Đã kiểm tra:

- `GET /health` → HTTP 200
- `GET /ready` → HTTP 200 (Redis kết nối được)
- `POST /ask` với JSON hợp lệ nhưng không có key → HTTP 401

Chạy 4 lệnh tự kiểm lúc 2026-11-25 21:35:27 (deployment `6954ddbc`):

```
GET  /health              -> 200
GET  /ready               -> 200
POST /ask without key     -> 401
POST /ask with X-API-Key  -> 200
```

## Platform

Railway (builder `DOCKERFILE`, `healthcheckPath = /health`) + Redis add-on.
(Có thể dùng Render thay thế — xem `06-lab-complete/render.yaml`.)

## Environment Variables Set (đặt trên nền tảng, KHÔNG ghi trong code)

- `AGENT_API_KEY` — đã đặt trong Railway Variables, không ghi trong repo.
- `REDIS_URL` — đã liên kết tới biến của Redis add-on.
- `RATE_LIMIT_PER_MINUTE=10`, `DAILY_BUDGET_USD=10`, `MONTHLY_BUDGET_USD=0`, `ENVIRONMENT=production`, `LOG_LEVEL=INFO`, `DEBUG=false` — đã cấu hình.
- `PORT` — nền tảng tự cấp (Dockerfile đã dùng `${PORT:-8000}`)

## Các bước deploy lại (Railway)

```bash
npm i -g @railway/cli
railway login
cd 06-lab-complete
railway init
railway add --database redis            # tạo Redis, Railway tự set REDIS_URL
railway variables set AGENT_API_KEY=<key-bi-mat>
railway variables set RATE_LIMIT_PER_MINUTE=10 DAILY_BUDGET_USD=10 ENVIRONMENT=production
railway up
railway domain                          # nhận URL public
```

## Test Commands (4 lệnh tự kiểm CP6 — chỉ in mã HTTP, không lộ key)

```bash
BASE="https://agent-api-production-f5fdfe9c.up.railway.app"
AGENT_API_KEY="<key-bi-mat>"

curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/health"                                   # 200
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/ready"                                    # 200
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
     -H 'Content-Type: application/json' -d '{"question":"Hello"}'                          # 401 (thiếu key)
curl -sS -o /dev/null -w '%{http_code}\n' -X POST "$BASE/ask" \
     -H 'Content-Type: application/json' -H "X-API-Key: $AGENT_API_KEY" \
     -d '{"question":"Hello"}'                                                              # 200 (có key)
```

Kết quả mong đợi: `200 / 200 / 401 / 200`. Che token khi dán output vào bài.

## Verify local (đã chạy, PASS 12/12)

Trước khi deploy đã xác nhận agent đạt chuẩn production ngay tại máy:

```bash
cd 06-lab-complete
python check_production_ready.py        # → 🎉 PASS 12/12 · 43/43 checks passed
```

Sau khi có URL: `python check_production_ready.py --public-url "$BASE"` để kiểm tra luôn cả bản deploy.

## Screenshots

- Đã có ảnh endpoint đang chạy: `screenshots/running.png`.
- Railway Dashboard (agent-api và Redis Online): `screenshots/dashboard.png`.
- Kết quả 4 lệnh tự kiểm: `screenshots/test.png` (dựng lại từ output terminal).
- Ảnh benchmark/observability hiện có được liệt kê trong `BENCHMARK_REPORT.md`.
