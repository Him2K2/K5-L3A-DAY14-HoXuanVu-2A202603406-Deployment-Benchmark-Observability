# Day 14 Lab — Mission Answers

**Họ tên:** Hồ Xuân Vũ
**MSSV:** 2A202603406
**Lớp:** K5 · L3A
**Ngày chạy:** 2026-11-25
**Môi trường:** Windows 11 + WSL2 (Ubuntu 22.04, Python 3.10) + Docker Desktop 28.0.4

> Tất cả lệnh runtime chạy trong WSL2 (`os.name == posix`) để `check_production_ready.py` gửi được SIGTERM.
> App bản develop ở Part 1/Part 2 nhận `question` qua **query param**, không nhận JSON (gửi JSON → 422).

---

## Part 1 — Localhost vs Production

### Exercise 1.1: Anti-patterns trong `01-localhost-vs-production/develop/app.py`

Tìm được **8** anti-pattern (yêu cầu ≥ 5):

| # | Anti-pattern | Dòng code trong `develop/app.py` | Vì sao nguy hiểm |
|---|---|---|---|
| 1 | Hardcode secret trong code | `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` (dòng 17) | Push lên GitHub là lộ key ngay, ai cũng dùng được → cháy quota/tiền |
| 2 | Hardcode DB credential | `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"` (dòng 18) | Lộ user/mật khẩu DB; không đổi được giữa dev/prod |
| 3 | Không có config management | `DEBUG = True`, `MAX_TOKENS = 500` cứng trong code (dòng 21–22) | Muốn đổi phải sửa code + build lại; vi phạm 12-Factor |
| 4 | `print` thay cho logging | `print(f"[DEBUG] Got question: {question}")` (dòng 33) | Không có level/timestamp, không parse được trong log aggregator |
| 5 | Log ra secret | `print(f"[DEBUG] Using key: {OPENAI_API_KEY}")` (dòng 34) | Secret rò rỉ vào log |
| 6 | Không có `/health` | (thiếu hẳn, comment dòng 42–43) | Platform không biết agent sống/chết để restart |
| 7 | Bind `localhost` + port cứng | `host="localhost", port=8000` (dòng 51–52) | Trong container không nhận kết nối ngoài; không đọc `PORT` của platform |
| 8 | `reload=True` trong "production" | dòng 53 | Reloader tốn RAM, không an toàn khi chạy thật |

### Exercise 1.2: Chạy bản develop

Chạy `uvicorn app:app` rồi gọi (develop nhận `question` qua query):

```
GET /                      → {"message":"Hello! Agent is running on my machine :)"}
POST /ask?question=What%20is%20docker
                           → {"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}
GET /health                → HTTP 404   (bản develop KHÔNG có health endpoint)
```

### Exercise 1.3: So sánh develop ↔ production (`production/app.py` + `config.py`)

| Feature | Develop | Production | Vì sao quan trọng |
|---------|---------|------------|-------------------|
| Config | Hardcode trong code | `os.getenv(...)` trong `config.py` (12-Factor) | Cùng 1 image chạy được ở dev/staging/prod, đổi config không build lại |
| Secret | `sk-...` trong code | Đọc từ env, `validate()` fail-fast khi prod thiếu `AGENT_API_KEY` | Không lộ secret, phát hiện thiếu config ngay khi khởi động |
| Logging | `print(...)` | `logging` JSON, **không** log secret | Parse được, không rò rỉ secret |
| Health check | Không có | `GET /health` (liveness) + `GET /ready` (readiness) | Platform restart khi chết; LB chỉ route khi sẵn sàng |
| Binding | `host="localhost"` | `host="0.0.0.0"`, `port=PORT` env | Chạy được trong container, nhận port platform cấp |
| Shutdown | Không xử lý | `lifespan` + handler `SIGTERM` | Tắt êm, không cắt ngang request |
| Reload | `reload=True` | `reload=settings.debug` (chỉ khi DEBUG) | Production không bật reloader |
| CORS | Không có | `CORSMiddleware` theo `ALLOWED_ORIGINS` | Chặn origin lạ |

**Một anti-pattern develop đã sửa ở production:** hardcode key `OPENAI_API_KEY = "sk-..."` (develop dòng 17) → ở production đọc `os.getenv("OPENAI_API_KEY","")` trong `config.py` dòng 27, và `validate()` raise lỗi nếu prod thiếu `AGENT_API_KEY`.

---

## Part 2 — Docker

### Exercise 2.1: Đọc `02-docker/develop/Dockerfile`

1. **Base image là gì?** `python:3.11` — bản full (~1 GB), có sẵn toàn bộ toolchain Python.
2. **Working directory là gì?** `/app` (lệnh `WORKDIR /app`); mọi lệnh sau chạy trong thư mục này.
3. **Tại sao COPY requirements.txt trước?** Để tận dụng **Docker layer cache**: chừng nào `requirements.txt` không đổi thì layer `pip install` được cache, sửa code (`app.py`) không phải cài lại dependencies → build nhanh hơn nhiều.
4. **CMD vs ENTRYPOINT khác nhau thế nào?** `CMD` đặt lệnh/tham số **mặc định**, dễ bị override khi `docker run <image> <lệnh khác>`. `ENTRYPOINT` cố định lệnh chính, tham số truyền thêm được **append** vào. Thực tế hay dùng `ENTRYPOINT` cho binary cố định + `CMD` cho tham số mặc định.

### Exercise 2.2: Build & run — kết quả gọi container

```
# develop (single-stage, python:3.11)
GET  /health                → {"status":"ok","uptime_seconds":2.9,"container":true}
POST /ask (JSON)            → 422 (bản develop nhận question qua query param)

# advanced (multi-stage, slim)
GET  /health                → {"status":"ok","version":"2.0.0","timestamp":"2026-11-25T08:47:48Z"}
POST /ask {"question":"What is deployment?"}
                            → {"answer":"Deployment là quá trình đưa code từ máy bạn lên server..."}
```

### Exercise 2.3: Multi-stage build — so sánh image size (đo bằng `docker images`)

Build từ gốc repo (Dockerfile `COPY` theo path tính từ root):

```bash
docker build -f 02-docker/develop/Dockerfile    -t my-agent:develop  .
docker build -f 02-docker/production/Dockerfile -t my-agent:advanced .
docker images my-agent
```

| Image | Size (đo được) |
|---|---|
| `my-agent:develop` (single-stage, `python:3.11`) | **1.67 GB** |
| `my-agent:advanced` (multi-stage, `python:3.11-slim`) | **240 MB** |
| **Chênh lệch** | **nhỏ hơn ~85,6%** (≈ 7× nhẹ hơn) |

- **Stage 1 (builder)** làm gì? Cài `gcc`, `libpq-dev` và `pip install --user` toàn bộ dependencies vào `/root/.local`.
- **Stage 2 (runtime)** làm gì? Base `python:3.11-slim`, chỉ `COPY --from=builder /root/.local`, copy source, tạo user non-root, chạy uvicorn.
- **Tại sao nhỏ hơn?** Image cuối **không** mang theo compiler/`gcc`/apt cache/build tools — chỉ giữ Python slim + site-packages cần để **chạy**. Base `python:3.11` full ~1 GB còn `slim` ~130 MB.

### Exercise 2.4: Docker Compose stack (`02-docker/production/docker-compose.yml`)

**Sơ đồ kiến trúc:**

```
                 ┌──────────────┐
  Client ──:80──▶│ nginx:alpine │  (reverse proxy / LB, cổng 80/443)
                 └──────┬───────┘
                        │ proxy_pass  (network: internal, bridge)
                        ▼
                 ┌──────────────┐    REDIS_URL=redis://redis:6379/0
                 │ agent (FastAPI)│──┬─────────────▶ ┌───────────────┐
                 │  build multi-  │  │               │ redis:7-alpine│ (cache / rate-limit)
                 │  stage, /health│  │               └───────────────┘
                 └──────────────┘  └─ QDRANT_URL=http://qdrant:6333 ─▶ ┌──────────────┐
                                                                       │ qdrant v1.9.0│ (vector DB)
                                                                       └──────────────┘
```

**Services được start:** `nginx`, `agent`, `redis`, `qdrant` (4 service, chung network bridge `internal`).
**Giao tiếp:** client chỉ vào qua Nginx (cổng 80); Nginx `proxy_pass` tới `agent:8000`; agent gọi `redis` và `qdrant` bằng **tên service** (Docker DNS nội bộ). `depends_on … condition: service_healthy` đảm bảo agent chỉ start sau khi redis/qdrant healthy. Secret nạp từ `.env.local` (ngoài git), không đặt thẳng trong compose.

**Kết quả test qua Nginx:**

```
GET http://localhost/health → HTTP 200
POST http://localhost/ask với {"question":"Explain microservices"} → HTTP 200, JSON có trường answer
```

**Hiểu:** multi-stage giảm dung lượng ở chỗ bỏ toolchain build khỏi image runtime; `COPY requirements.txt` đứng trước `COPY . .` để layer cài dependencies được cache khi chỉ sửa source.

---

## Part 3 — Cloud Deployment

> Lớp K5 deploy **chính agent Part 6** (thư mục `06-lab-complete/`) lên cloud ở CP6, dùng `railway.toml`/`render.yaml` tự viết ở CP5. URL public + screenshot deploy nằm trong `DEPLOYMENT.md` và `screenshots/`.

### Exercise 3.1 / 3.2: Deploy (nền tảng chính)

- **Nền tảng chính:** Railway (builder `DOCKERFILE`).
- **URL public:** https://agent-api-production-f5fdfe9c.up.railway.app — app và Redis đã deploy; `/health`=200, `/ready`=200, `/ask` không key=401.
- **Còn cần làm:** tự đặt `AGENT_API_KEY` trong Railway Dashboard rồi xác nhận `/ask` với key hợp lệ trả 200. Không gửi key qua chat hoặc commit vào repo.
- **Biến môi trường:** `REDIS_URL` đã liên kết tới Redis add-on; các biến không bí mật gồm `RATE_LIMIT_PER_MINUTE`, `DAILY_BUDGET_USD`, `MONTHLY_BUDGET_USD`, `ENVIRONMENT`, `LOG_LEVEL`, `DEBUG` đã được cấu hình.
- **4 lệnh tự kiểm CP6** (`/health`=200, `/ready`=200, `/ask` không key=401, `/ask` có key=200): xem `DEPLOYMENT.md`.

### So sánh `railway.toml` ↔ `render.yaml` (cùng deploy agent Part 6)

| Khía cạnh | `railway.toml` | `render.yaml` |
|---|---|---|
| Định dạng | TOML, mô tả 1 service | YAML (Blueprint), mô tả **nhiều** service một lúc |
| Chọn builder | `[build] builder = "DOCKERFILE"` | `runtime: docker` + `dockerfilePath: ./Dockerfile` |
| Health check | `[deploy] healthcheckPath = "/health"` | `healthCheckPath: /health` |
| Secret | Đặt trong dashboard / `railway variables set` (không trong file) | `AGENT_API_KEY: generateValue: true` (Render tự sinh, không ghi giá trị) |
| Redis | Tạo Redis add-on riêng, set `REDIS_URL` tay | Khai báo luôn `- type: redis` và `REDIS_URL` dùng `fromService … property: connectionString` |
| Khác nhau vì | Railway tách hạ tầng khỏi repo (cấu hình ở dashboard) | Render gom cả app + Redis + env vào 1 file "infrastructure as code" |

### Exercise 3.3: GCP Cloud Run — pipeline CI/CD (đọc `cloudbuild.yaml` + `service.yaml`)

Pipeline trong `03-cloud-deployment/production-cloud-run/cloudbuild.yaml` chạy tự động khi push lên `main`, gồm 4 bước tuần tự (mỗi bước `waitFor` bước trước):

1. **test** — image `python:3.11-slim`: `pip install` + `pytest tests/`; fail test là dừng pipeline.
2. **build** — `gcr.io/cloud-builders/docker build` image gắn 2 tag `:$COMMIT_SHA` và `:latest`, dùng `--cache-from :latest` để tái dùng layer.
3. **push** — đẩy `--all-tags` lên Container Registry (`gcr.io/$PROJECT_ID/ai-agent`).
4. **deploy** — `gcloud run deploy ai-agent` với image `:$COMMIT_SHA`, `--region asia-southeast1`, `--allow-unauthenticated`, `--min-instances=1` (tránh cold start), `--max-instances=10`, secret lấy từ **Secret Manager** (`--set-secrets=OPENAI_API_KEY=openai-key:latest`).

`service.yaml` (Knative) khai báo cùng cấu hình dạng IaC: autoscale 1→10, `containerConcurrency: 80`, `livenessProbe: /health`, `startupProbe: /ready`, env secret lấy từ `secretKeyRef`. Tức là: **push → test → build → push registry → deploy Cloud Run**, secret không bao giờ nằm trong image.

---

## Part 4 — API Security

### Exercise 4.1: API Key (bản develop, `04-api-gateway/develop`)

Chạy `AGENT_API_KEY=secret-key-123 python app.py`. Header `X-API-Key`: thiếu → **401**, sai → **403**, đúng → **200** (`APIKeyHeader(auto_error=False)` + check thủ công).

### Exercise 4.2 / 4.3: JWT + Rate limit (bản production, `04-api-gateway/production`)

Lấy token ở `POST /auth/token` với `student` / `demo123` (giới hạn 10 req/phút). Output `curl -i` (token đã che):

```
# [401] POST /ask khi KHÔNG có token
HTTP/1.1 401 Unauthorized
www-authenticate: Bearer

# token lấy từ POST /auth/token (student/demo123) → Authorization: Bearer <TOKEN-ĐÃ-CHE>

# [200] POST /ask với token hợp lệ
HTTP/1.1 200 OK
{"question":"what is deployment?","answer":"Deployment là quá trình đưa code...","usage":{"requests_remaining":8,"budget_remaining_usd":3.9e-05}}

# [429] gọi lặp vượt 10 req/phút (sliding window) — kèm Retry-After
req 1..8  -> HTTP 200
req 9     -> HTTP 429   retry-after: 59
req 10..  -> HTTP 429   retry-after: 59
```

(8 lần 200 còn lại vì 2 request 200 trước đó đã dùng hết hạn mức 10/phút của `student`.)

### Exercise 4.4: Cost guard (cách làm)

`cost_guard.py` (`04-api-gateway/production`) cộng dồn chi phí theo **token** cho mỗi user mỗi ngày:
`cost = input_tokens/1000 × $0.00015 + output_tokens/1000 × $0.0006` (bảng giá gpt-4o-mini).
- `check_budget(user)` gọi **trước** khi gọi LLM: vượt `daily_budget_usd` ($1/user) → **HTTP 402 Payment Required**; vượt `global_daily_budget_usd` ($10) → **503**; dùng ≥ 80% → log warning.
- `record_usage(...)` gọi **sau** khi gọi LLM để cộng token vào tổng.

**Vì sao cần cả rate limit lẫn cost guard?** Rate limit bảo vệ **tốc độ** (chặn spam/DoS, trả 429) nhưng không ngăn được tiền: vài request với prompt rất dài vẫn đốt hết budget. Cost guard bảo vệ **tiền** (chặn khi hết ngân sách, trả 402). Hai lớp bảo vệ hai thứ khác nhau.

---

## Part 5 — Scaling & Reliability

### Exercise 5.1: Liveness (`/health`) vs Readiness (`/ready`)

| | `/health` (liveness) | `/ready` (readiness) |
|---|---|---|
| Trả lời | "Process còn sống không?" | "Sẵn sàng nhận traffic chưa?" |
| Ai dùng | Platform/orchestrator | Load balancer |
| Fail thì sao | **Restart** container | **Ngừng route** traffic (không restart) |
| Dependency | Không phụ thuộc Redis (luôn 200 khi process sống) | Phụ thuộc Redis — mất Redis → **503** |

### Exercise 5.2: Graceful shutdown

Nhận `SIGTERM` → ngừng nhận request mới, chờ request in-flight chạy xong rồi thoát (exit 0) → không mất request. Dùng `lifespan` của FastAPI; nếu tự đăng ký signal handler phải gọi lại handler của uvicorn, nếu không process không bao giờ tắt (Docker chờ 10s rồi SIGKILL → exit 137).

### Exercise 5.3: Stateless design

State (session/history) lưu ở **Redis**, không giữ trong RAM của instance. Vì sao RAM hỏng khi scale: request 1 của user A vào instance 1 (lưu session RAM), request 2 vào instance 2 (không có session đó) → mất ngữ cảnh. Để trong Redis thì **mọi** instance đọc được.

### Exercise 5.4: Load balancing (Nginx + 3 instance)

`docker compose -p k5-day14-scaling up -d --build --scale agent=3`: Nginx (cổng 8080) phân phối request round-robin tới 3 agent; agent dùng chung 1 Redis. Mỗi agent có `INSTANCE_ID` riêng, trả về trong field `served_by`.

### Exercise 5.5: Test stateless (`python test_stateless.py`)

```
Total requests: 5
Instances used: 3 (instance-3b1585, instance-e69769, instance-77c10a)
Total messages (history): 10
Kết quả: Session history preserved across all instances via Redis.
```
Ý nghĩa: 5 request cùng một `session_id` được phục vụ bởi các instance khác nhau nhưng history vẫn đầy đủ → chứng minh state nằm trong Redis chứ không phải RAM.

---

## Part 6 — Final Project: output `check_production_ready.py`

Chạy đầy đủ (có Docker, trong WSL2 posix) trong `06-lab-complete/`:

```
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)          [image 56 MB, build OK]
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)            [Redis down → /ready 503, /health vẫn 200]
     ✅ API Key authentication                     [thiếu/sai key → 401; đúng → 200]
     ✅ Rate limiting                              [429 sau 5 request; state trong Redis, restart vẫn 429]
     ✅ Cost guard                                 [402 khi hết budget]
     ✅ Config từ environment variables
     ✅ Structured logging                         [17 dòng JSON hợp lệ]
     ✅ Graceful shutdown                          [SIGTERM: request vẫn 200, exit 0; docker stop 0.6s]
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

---

## AI log

- **Công cụ:** Claude (Anthropic) — trợ lý lập trình.
- **Hỏi gì:** đọc toàn bộ đề (README/RULES/CHECKPOINTS/RUBRIC) rồi hoàn thiện các `TODO` của Part 6 (`app/config.py`, `redis_client.py`, `auth.py`, `rate_limiter.py`, `cost_guard.py`, `main.py`, `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `railway.toml`, `render.yaml`); chạy các ví dụ Part 1–5 và benchmark Part 7.
- **Nhận được gì:** code điền vào các khung TODO và các lệnh chạy/benchmark.
- **Tự kiểm tra thế nào:** chạy `python check_production_ready.py` (đầy đủ, có Docker, trong WSL2) tới khi **PASS 12/12 · 43/43 checks**; tự chạy lại từng lệnh curl 401/200/429 (Part 4), đo image size bằng `docker images` (Part 2), chạy load test + eval và đối chiếu số trong `BENCHMARK_REPORT.md` với file JSON/CSV trong `reports/` và `benchmark-results/`. Không có số nào bịa — mọi con số lấy từ lệnh đã chạy.
