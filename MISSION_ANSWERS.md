# Day 14 Lab — Mission Answers

**Lớp:** K5 · L3A
**Ngày chạy:** 2026-11-25
**Môi trường:** Windows 11 + WSL2 (Ubuntu 22.04, Python 3.10) + Docker Desktop 28.0.4

> Lệnh Python chạy trong WSL2 (`os.name == posix`) để `check_production_ready.py` gửi được SIGTERM; `docker compose` chạy từ Windows.
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
# my-agent:develop
POST /ask?question=What%20is%20Docker        → HTTP/1.1 200 OK
{"answer":"Container là cách đóng gói app để chạy ở mọi nơi. Build once, run anywhere!"}

POST /ask với body JSON (lệnh trong CODE_LAB) → HTTP/1.1 422 Unprocessable Entity
{"detail":[{"type":"missing","loc":["query","question"],"msg":"Field required","input":null}]}

GET /health                                  → HTTP/1.1 200 OK
{"status":"ok","uptime_seconds":6.1,"container":true}
```

422 vì hàm khai báo `question: str`, FastAPI hiểu là query param nên không đọc JSON body.

### Exercise 2.3: Multi-stage build — so sánh image size (đo bằng `docker images`)

Build từ gốc repo (Dockerfile `COPY` theo path tính từ root):

```bash
docker build -f 02-docker/develop/Dockerfile    -t my-agent:develop  .
docker build -f 02-docker/production/Dockerfile -t my-agent:advanced .
docker images my-agent
```

| Image | Size (đo được) |
|---|---|
| `my-agent:develop` (single-stage, `python:3.11`) | **1.15 GB** |
| `my-agent:advanced` (multi-stage, `python:3.11-slim`) | **163 MB** |
| **Chênh lệch** | **nhỏ hơn ~85,8%** (≈ 7× nhẹ hơn) |

Lần build đầu trong ngày, `docker images` hiện 1.67 GB và 240 MB (giảm ~85,6%). Docker Desktop bị reset giữa hai lần; có thể cách lưu image (containerd hay overlay2) khác nhau nên con số khác. Tỉ lệ giảm gần như không đổi.

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
$ docker compose -p k5-day14-docker ps
agent  | Up (healthy) | 8000/tcp
nginx  | Up           | 0.0.0.0:80->80/tcp, 0.0.0.0:443->443/tcp
qdrant | Up (healthy) | 6333-6334/tcp
redis  | Up (healthy) | 6379/tcp

$ curl -i http://localhost/health
HTTP/1.1 200 OK
Server: nginx
{"status":"ok","uptime_seconds":127.2,"version":"2.0.0","timestamp":"2026-11-25T14:06:27.304322"}

$ curl -i -X POST http://localhost/ask -H "Content-Type: application/json" -d '{"question":"Explain microservices"}'
HTTP/1.1 200 OK
Server: nginx
{"answer":"Đây là câu trả lời từ AI agent (mock). Trong production, đây sẽ là response từ OpenAI/Anthropic."}
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

- **Key được check ở đâu?** Dependency `verify_api_key` (dòng 39–54) gắn vào `/ask` qua `Depends`, đọc header `X-API-Key` và so với biến môi trường `AGENT_API_KEY`.
- **Sai key thì sao?** Thiếu → 401, sai → 403.
- **Rotate key thế nào?** Đổi `AGENT_API_KEY` rồi restart. Đã thử đổi sang `secret-key-456`: key cũ → 403, key mới → 200. App chỉ nhận một key nên lúc đổi client dùng key cũ bị gián đoạn; production nên chấp nhận cả hai key trong thời gian chuyển.

App chạy với `AGENT_API_KEY=secret-key-123` (key mẫu của đề), output `curl -i`:

```
[không key]  HTTP/1.1 401 Unauthorized
{"detail":"Missing API key. Include header: X-API-Key: <your-key>"}

[sai key]    HTTP/1.1 403 Forbidden
{"detail":"Invalid API key."}

[đúng key]   HTTP/1.1 200 OK
{"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
```

### Exercise 4.2 / 4.3: JWT + Rate limit (bản production, `04-api-gateway/production`)

**JWT flow (4.2):** `POST /auth/token` kiểm username/password rồi ký JWT (HS256) chứa `sub`, `role`, `iat`, `exp` (60 phút). Các request sau gửi `Authorization: Bearer <token>`; `verify_token` kiểm chữ ký và hạn dùng, không cần tra database. Thiếu hoặc hết hạn → 401, token sai → 403.

**Rate limit (4.3):** thuật toán **sliding window** (deque timestamp mỗi user, cửa sổ 60 giây). User **10 req/phút**, admin **100 req/phút**. Admin không bỏ qua hẳn limit: `app.py` chọn `rate_limiter_admin` khi `role == "admin"`. State nằm trong RAM nên không dùng chung giữa nhiều instance.

Token lấy bằng `student` / `demo123`, đã che. Output `curl -i` (bỏ bớt các security header):

```
[không token] HTTP/1.1 401 Unauthorized
www-authenticate: Bearer
{"detail":"Authentication required. Include: Authorization: Bearer <token>"}

[có token]    HTTP/1.1 200 OK
{"question":"Explain JWT","answer":"Tôi là AI agent được deploy lên cloud. Câu hỏi của bạn đã được nhận.","usage":{"requests_remaining":9,"budget_remaining_usd":1.9e-05}}

[gọi tiếp 20 lần, student] 200 ×9 rồi 429 ×11   (request đầu ở trên đã dùng 1 lượt, tổng 10)
[429]         HTTP/1.1 429 Too Many Requests
x-ratelimit-limit: 10
x-ratelimit-remaining: 0
retry-after: 59
{"detail":{"error":"Rate limit exceeded","limit":10,"window_seconds":60,"retry_after_seconds":59}}

[20 lần, teacher (admin)]  200 ×20
```

Trường `budget_remaining_usd` của app mẫu thực ra trả `total_cost_usd` (số đã tiêu), không phải số còn lại.

### Exercise 4.4: Cost guard (cách làm)

`cost_guard.py` (`04-api-gateway/production`) cộng dồn chi phí theo **token** cho mỗi user mỗi ngày:
`cost = input_tokens/1000 × $0.00015 + output_tokens/1000 × $0.0006` (bảng giá gpt-4o-mini).
- `check_budget(user)` gọi **trước** khi gọi LLM: vượt `daily_budget_usd` ($1/user) → **HTTP 402 Payment Required**; vượt `global_daily_budget_usd` ($10) → **503**; dùng ≥ 80% → log warning.
- `record_usage(...)` gọi **sau** khi gọi LLM để cộng token vào tổng.

Bản mẫu giữ số liệu trong RAM nên restart là mất và nhiều instance không dùng chung. Phần cài đặt bằng Redis nằm ở `06-lab-complete/app/cost_guard.py`: cộng dồn bằng `INCRBYFLOAT` vào `cost:daily:YYYY-MM-DD` và `cost:monthly:YYYY-MM` (key đổi theo ngày/tháng nên tự reset, có `EXPIRE` để dọn), vượt `DAILY_BUDGET_USD` hoặc `MONTHLY_BUDGET_USD` → 402. Khác lời giải mẫu: ngân sách tính chung cho cả service, không theo từng user.

Hạn chế đã biết: kiểm tra trước, cộng sau, nên các request song song ở sát ngưỡng có thể vượt budget một chút; nếu Redis lỗi khi đọc hoặc ghi chi phí, hàm bỏ qua lỗi thay vì chặn. Rate limiter cũng kiểm tra rồi mới ghi nên request song song có thể vượt limit một chút.

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

Kết quả chạy `05-scaling-reliability/develop`:

```
GET /health → HTTP/1.1 200 OK
{"status":"ok","uptime_seconds":0.6,"version":"1.0.0","environment":"development",...,"checks":{"memory":{"status":"ok","used_percent":17.6}}}
GET /ready  → HTTP/1.1 200 OK
{"ready":true,"in_flight_requests":1}
```

Bản develop chưa có Redis. Bản production khi tắt Redis: `/health` vẫn 200 với `"status":"degraded","redis_connected":false`. `/ready` gọi qua Nginx ra 502: agent trả 503, nhưng `proxy_next_upstream ... http_503` khiến Nginx thử các instance khác và tất cả đều thất bại. Agent Part 6 gọi trực tiếp trả đúng 503 (script chấm kiểm tra).

### Exercise 5.2: Graceful shutdown

Nhận `SIGTERM` → ngừng nhận request mới, chờ request in-flight chạy xong rồi thoát (exit 0) → không mất request. Dùng `lifespan` của FastAPI; nếu tự đăng ký signal handler phải gọi lại handler của uvicorn, nếu không process không bao giờ tắt (Docker chờ 10s rồi SIGKILL → exit 137).

Kết quả: gửi `POST /ask` rồi `kill -TERM` ngay khi request đang chạy.

```
in-flight request -> 200
app exit code 0
INFO:     Shutting down
INFO:     127.0.0.1:42960 - "POST /ask?question=Long%20task HTTP/1.1" 200 OK
INFO:     Waiting for application shutdown.
🔄 Graceful shutdown initiated...
✅ Shutdown complete
INFO:     Finished server process [562]
```

### Exercise 5.3: Stateless design

State (session/history) lưu ở **Redis**, không giữ trong RAM của instance. Vì sao RAM hỏng khi scale: request 1 của user A vào instance 1 (lưu session RAM), request 2 vào instance 2 (không có session đó) → mất ngữ cảnh. Để trong Redis thì **mọi** instance đọc được.

### Exercise 5.4: Load balancing (Nginx + 3 instance)

`docker compose -p k5-day14-scaling up -d --build --scale agent=3`: Nginx (cổng 8080) phân phối request round-robin tới 3 agent; agent dùng chung 1 Redis. Mỗi agent có `INSTANCE_ID` riêng, trả về trong field `served_by`.

### Exercise 5.5: Test stateless (`python test_stateless.py`)

```
Request 1: [instance-1f7bb8]   Request 2: [instance-c003a8]   Request 3: [instance-5a0894]
Request 4: [instance-1f7bb8]   Request 5: [instance-c003a8]
Total requests: 5
Instances used: {'instance-c003a8', 'instance-1f7bb8', 'instance-5a0894'}
✅ All requests served despite different instances!
Total messages: 10
✅ Session history preserved across all instances via Redis!
```

Script không tự tắt instance, nên thử thêm: tạo session trên `instance-1f7bb8`, `docker kill k5-day14-scaling-agent-1`, rồi gửi tiếp 4 câu cùng `session_id`. Cả 4 trả **200** (phục vụ bởi `c003a8` và `5a0894`), history có đủ **10** message.

Ý nghĩa: cùng một `session_id` được nhiều instance phục vụ, mất một instance, history vẫn đủ → state nằm trong Redis chứ không phải RAM.

---

## Part 6 — Final Project: output `check_production_ready.py`

Chạy đầy đủ (có Docker, trong WSL2 posix) trong `06-lab-complete/`:

Chạy `python check_production_ready.py --public-url https://agent-api-production-f5fdfe9c.up.railway.app`, trích nguyên văn:

```
================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 44/44 checks passed
  🎉 PASS 12/12 — PRODUCTION READY! Deploy nào!
================================================================
```

Chi tiết trong cùng lần chạy: image 160 MB; `docker stop` exit code 0 sau 1.0s; 429 sau 5 request thành công và vẫn 429 sau khi restart agent; Redis mất kết nối → `/ready` 503, `/health` 200.

---

## AI log

- **Công cụ:** Claude (Claude Code); GitHub Copilot (đồng tác giả ghi trong commit `743d526`).
- **Hỏi gì:** nhờ Claude đọc đề và làm bài lab; sau đó nhờ kiểm tra lại bài, sửa chỗ thiếu và chạy lại.
- **Claude đã làm:**
  - Viết code Part 6: `app/*.py`, `Dockerfile`, `docker-compose.yml`, `.dockerignore`, `.env.example`, `railway.toml`, `render.yaml`.
  - Viết phần lớn câu trả lời trong `MISSION_ANSWERS.md`, `BENCHMARK_REPORT.md`, `DEPLOYMENT.md` và `.github/workflows/eval-gate.yml`.
  - Thêm 2 entry vào `KNOWLEDGE_BASE` (Exercise 7.3).
  - Sửa `benchmark-observability/production/Dockerfile` của đề (đặt `HOME`, `PYTHONPATH`) vì container báo `No module named 'uvicorn'`.
  - Chạy các lệnh đo Part 1, 2, 4, 5, load test, eval, Exercise 7.4, thí nghiệm alert và script chấm; chụp ảnh Grafana, Prometheus, trace chậm bằng Chrome headless.
- **Kiểm tra lại phát hiện gì:** cost/câu đúng ghi sai (0.00003487, JSON là 0.00003485); nhận xét "avg gần như không đổi" và "gần tuyến tính" sai; Part 4.1 ghi như đã chạy nhưng chưa chạy; ảnh Grafana chỉ có một panel. Các lỗi này đã được sửa, số đo lại bằng lệnh thật.
- **Cách kiểm tra:** `check_production_ready.py` báo PASS 12/12; đối chiếu số trong báo cáo với JSON/CSV bằng script. Các lệnh này do Claude chạy.
