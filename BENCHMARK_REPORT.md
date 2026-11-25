# Benchmark & Observability Report — Day 14

**Họ tên:** Hồ Xuân Vũ — 2A202603406
**Ngày chạy:** 2026-11-25
**Môi trường:** Windows 11 + WSL2 (Ubuntu 22.04, Python 3.10), Docker Desktop 28.0.4

> Số ở mục 2, 3 lấy từ `reports/load_*.json`, `reports/eval_*.json`; mục 4 từ `reports/grafana_ex74.json`, `reports/alert_timing.json` và API của Jaeger; mục 5 từ CSV trong `benchmark-results/`.
> Mỗi cấu hình chỉ đo một lần trên một máy cá nhân, nên chênh lệch nhỏ có thể là nhiễu.

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < **500** ms | Người dùng cảm nhận "nhanh" dưới ~0,5s; dùng p95 để 95% request đạt, không bị 1 request chậm kéo lệch như average |
| Error rate `/ask` | < **2** % | Cho phép error budget nhỏ vì mock LLM có ~1% lỗi upstream ngẫu nhiên (giống 429/503 thật) |
| Accuracy golden dataset | ≥ **80** % | Ngưỡng tối thiểu để không regression; agent v2 (RAG) phải đạt cao hơn hẳn v1 |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2, 300 request/mức)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO p95≤500 & err≤2% |
|---|---|---|---|---|---|---|
| 1 | 4.01 | 191.2 | 223.1 | 1699.0 | 1.00% | ✅ PASS |
| 10 | 39.53 | 193.1 | 219.7 | 1671.4 | 1.33% | ✅ PASS |
| 50 | 110.05 | 231.3 | 712.5 | 1715.7 | 0.33% | ❌ FAIL (p95 712 > 500) |
| 100 | 42.21 | 1192.7 | 5303.5 | 5551.7 | 0.67% | ❌ FAIL (p95 5303 > 500) |

**Nhận xét — RPS có tăng tuyến tính không? Vì sao?**
Chỉ tuyến tính lúc đầu. Từ c=1 lên c=10 (gấp 10) RPS tăng 9,9 lần (4,01 → 39,53) vì thời gian mỗi request gần như chỉ là chờ mock LLM, và nhiều request chờ song song được trên một event loop. Từ c=10 lên c=50 (gấp 5) RPS chỉ tăng 2,8 lần, p95 tăng từ 220 lên 713 ms. Ở c=100 RPS giảm còn 42,21 và p50 lên 1.193 ms: thêm concurrency chỉ làm request xếp hàng lâu hơn.
Agent chạy **một** process uvicorn và client load test chạy cùng máy, nên cả hai có thể là nút thắt. Tôi chưa đo CPU của từng bên và chỉ chạy c=100 một lần, vì vậy chưa kết luận được bên nào bão hoà trước.

### 2.2 Tail latency (agent v2, concurrency=20, 300 request)

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 194.9 | 225.6 | 255.3 |
| 0.03 (mặc định) | 236.4 | 252.5 | 1698.6 |
| 0.1 | 313.3 | 1690.2 | 1714.5 |

**Nhận xét:** **p99** nhạy nhất: chỉ 3% request chậm đã đẩy p99 từ 255 lên 1.699 ms, trong khi avg chỉ tăng 42 ms (195 → 236) và p95 tăng 27 ms. Khi tỉ lệ chậm vượt 5% (0.1), p95 cũng nhảy lên 1.690 ms còn avg mới là 313 ms (tăng 118 ms). Ở mức 0.1, avg 313 ms vẫn nằm dưới ngưỡng 500 ms dù cứ 10 người có khoảng 1 người chờ gần 1,7 giây. Vì avg trộn nhóm chậm vào số đông nhanh, SLO phải đặt theo p95/p99.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`, 23 câu)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | **100% (23/23)** |
| Avg tokens / câu | 55.8 | 108.7 | 115.0 |
| Tổng cost (USD) | 0.000386 | 0.000756 | 0.000802 |
| Cost / câu đúng (USD) | 0.00038595 | 0.00003599 | 0.00003485 |
| Quality gate | ❌ FAIL | ✅ PASS | ✅ PASS (exit 0) |

**Những câu v2 trả lời sai ban đầu và cách sửa (chỉ sửa `KNOWLEDGE_BASE`, không đụng `golden_dataset`):**

| ID | Keyword bị thiếu | Đã sửa gì |
|---|---|---|
| `scaling-03` | cpu, memory, custom metrics | Thêm entry KB kích hoạt bởi `kubernetes`/`hpa`, nội dung nêu HPA scale theo CPU, memory, custom metrics |
| `security-02` | token, hết hạn, chữ ký | Thêm entry KB kích hoạt bởi `jwt`/`api key`, nội dung nêu JWT có chữ ký số + thời gian hết hạn, khác API key tĩnh |

**Trade-off v1 ↔ v2:** v2 (có retrieval/RAG) tốn **~2× token** mỗi câu (108.7 vs 55.8) và cost cao hơn, nhưng accuracy nhảy từ 4.3% lên 91.3%→100%. Vì vậy **cost / câu đúng** của v2 (~$0.000036) lại **rẻ hơn ~10,7×** so với v1 (~$0.000386): đo "cost / câu" thì v1 rẻ hơn, nhưng đo "cost / câu *đúng*" — thứ thực sự có giá trị — thì v2 vượt trội. Đây là lý do nên so hai phiên bản bằng cost / câu đúng.

Về latency: eval chỉ có 23 câu nên không dùng để kết luận (v1 p50 = 160,0 ms, v2 p50 = 189,6 ms; p95 của v1 là 1.494 ms chỉ vì trúng request chậm). Hai entry KB được viết để trả lời đúng hai câu đang sai trong golden dataset, nên 100% chỉ chứng minh agent đúng trên 23 câu này, không phải trên câu hỏi mới.

Ghi chú: lần chạy eval v1 đầu tiên bị hỏng vì cổng 8001 đang do một project khác dùng (mọi request trả 404). `eval_v1.json` là bản chạy lại trên cổng trống. `eval_v2.json` từng so với bản hỏng đó; so lại với `eval_v1.json` hiện tại vẫn không có regression (câu duy nhất v1 đúng là `basic-01`, v2 cũng đúng).

**Quality gate chặn merge (Exercise 7.3 bài 4):** `run_eval.py` trả **exit code 1** khi `accuracy < --min-accuracy` hoặc có regression so với baseline → CI dừng. Bước GitHub Actions:

```yaml
- name: Eval quality gate
  run: |
    python eval/run_eval.py --url http://localhost:8002 \
      --min-accuracy 0.9 --baseline reports/eval_v2.json
    # exit code != 0 → step fail → chặn merge
```

File CI: `.github/workflows/eval-gate.yml`. Muốn thực sự chặn merge, phải bật branch protection và đặt job này là required check.

---

## 4. Observability stack (production)

### 4.1 Screenshot (trong `screenshots/`)

- [x] `grafana-dashboard.png` — dashboard khi Locust chạy 30 users, cấu hình mặc định
- [x] `grafana-during-chaos.png` — dashboard ngay sau thí nghiệm A và B
- [x] `jaeger-slow-trace.png` — trace chậm (span LLM chiếm gần hết thời gian)
- [x] `jaeger-error-trace.png` — trace lỗi (event `exception`)
- [x] `prometheus-alert-firing.png` — hai alert cùng **firing**

**Exercise 7.4** (Locust 30 users, ramp up 5, 2 instance; lúc 20:55:39, cửa sổ 1 phút, `reports/grafana_ex74.json`):

1. **p95 và avg?** avg = 242 ms, p50 = 174 ms, p95 = 296 ms, p99 = 1.863 ms; error rate 1,08%. p95 chỉ hơn avg khoảng 54 ms vì nhóm chậm (~3%) nằm ngoài p95. avg cao hơn p50 68 ms vì bị nhóm chậm kéo lên. Tail thật chỉ lộ ở p99, nên nhìn riêng avg hoặc p95 sẽ bỏ sót 3% người dùng chờ gần 2 giây.
2. **Nginx có chia đều không?** Có: 9,24 và 9,20 req/s trên tổng 18,44 req/s.
3. **Vì sao input tokens/s lớn hơn output?** 1.328 so với 705 token/s. Prompt của v2 gồm system prompt, tài liệu retrieval và câu hỏi, còn output chỉ là câu trả lời ngắn (mock trả về chính đoạn tài liệu).
4. **`curl http://localhost:8080/metrics`?** Trả **404** từ Nginx (`location = /metrics { return 404; }`). Metrics lộ route, lưu lượng, chi phí nên không public; Prometheus scrape thẳng các agent trong mạng nội bộ Docker.

### 4.2 Thí nghiệm "phá hệ thống"

Locust giữ 30 users. Thời gian tính từ lúc chạy `docker compose up -d agent` với biến mới tới lúc API `/api/v1/alerts` báo firing, hỏi mỗi giây (`reports/alert_timing.json`).

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` | 92 s (pending ở 32 s, `for: 1m`) | Error rate, Requests/s theo status code |
| B | `MOCK_SLOW_RATE=0.3` (giữ error rate 0.2 để hai alert cùng firing) | `AgentHighLatencyP95` | 150 s (pending ở 30,5 s, `for: 2m`) | Latency p95 |
| C | `LLM_MODEL=mock-llm-large` | Không chạy | — | — |
| D | `docker pause` 1 instance | Không chạy | — | — |
| E | `AGENT_VERSION=v1` | Không chạy; theo đề không có alert | — | — |

Mỗi alert mất khoảng 30 giây để rate trong cửa sổ 1 phút vượt ngưỡng, cộng thêm thời gian `for`. `promtool test rules` trên `alert_rules_test.yml`: SUCCESS.

**Phát hiện ngoài kế hoạch:** với tải 30 users bình thường và `mock-llm-small`, `LLMCostBurnRateHigh` cũng đã firing (lịch sử `ALERTS` của Prometheus, khoảng 20:55:00–20:57:45), vì chi phí ~$2,28/giờ vượt ngưỡng $2/giờ. Ngưỡng tuyệt đối này quá thấp so với lưu lượng ~18 req/s; nên đặt theo cost/request hoặc theo baseline.

**Vì sao lỗi 504 ở Nginx không hiện trên metric của agent?** Khi agent treo, Nginx hết `proxy_read_timeout` và tự trả 504; agent chưa xử lý xong request nên không tăng counter. Cần metric ở load balancer hoặc synthetic check từ bên ngoài.

**Thí nghiệm E không làm alert firing — phát hiện bằng cách nào?** Lỗi **chất lượng** (trả lời sai) không làm metric hạ tầng (latency/error/CPU) đỏ, nên observability hạ tầng không bắt được. Phải bắt bằng **eval chất lượng** trên golden dataset chạy trong CI trước deploy, cộng feedback người dùng (thumbs up/down) và LLM-as-judge/sampling câu trả lời thật trong production.

### 4.3 Debug bằng trace

- Trace chậm — `trace_id`: `b737abb0ad40a30336e9e98c88b9bff5` (`jaeger-slow-trace.png`)
- Tổng thời gian: **1.711,0 ms**
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small` (**1.685,0 ms, 98,5%**); `agent.retrieve_context` chỉ 23,5 ms (1,4%). Nút thắt là LLM, không phải code agent hay retrieval.
- Dòng log tương ứng (grep theo `trace_id`):

```json
{"ts": "2026-11-25T14:01:01.059708+00:00", "level": "INFO", "service": "observable-agent", "instance": "6ecd47e4fbe9", "event": "llm_call", "trace_id": "b737abb0ad40a30336e9e98c88b9bff5", "span_id": "d9aad135daa1f629", "request_id": "a31592eee94b", "model": "mock-llm-small", "agent_version": "v2", "input_tokens": 73, "output_tokens": 35, "cost_usd": 3.2e-05, "llm_ms": 1685.0}
{"ts": "2026-11-25T14:01:01.060173+00:00", "level": "INFO", "service": "observable-agent", "instance": "6ecd47e4fbe9", "event": "http_request", "trace_id": "b737abb0ad40a30336e9e98c88b9bff5", "span_id": "d9aad135daa1f629", "request_id": "a31592eee94b", "method": "POST", "route": "/ask", "status": 200, "ms": 1710.4}
```

- Trace lỗi — `trace_id`: `422c849b60a17d4fbcfeb44c7e6dd8f1` (`jaeger-error-trace.png`, đo ở lần chạy stack trước lúc 16:28): `chat mock-llm-small` dài 96,4 ms, có event `exception` với message "Upstream LLM erro…".

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 46.08 | 280 | 2,300 | 4,900 | 74 / 5,393 (1.37%) |
| 3 | 51.45 | 230 | 1,800 | 2,900 | 69 / 5,983 (1.15%) |

Bảng trên là dòng `/ask` trong CSV. Dòng `Aggregated` (tính cả `/health`): 50.60 → 56.17 RPS, p95 2,200 → 1,700 ms. Mọi failure đều là 503 từ mock LLM (`scale_*_failures.csv`).

**Giải thích kết quả:** 1 → 3 instance tăng RPS 11,7%, giảm p95 21,7% và p99 40,8%, tức hàng đợi ngắn lại nhưng RPS xa mức gấp 3. Locust là tải vòng kín: mỗi user nghỉ 0,5–2 giây rồi mới gửi tiếp, nên 100 users chỉ tạo được một lượng request giới hạn dù agent nhanh hơn. Phần chờ LLM (120–180 ms, cộng ~1,5 s với 3% request) cũng không giảm khi thêm instance. p95 = 1,8 s với 3 instance vẫn cao hơn mức 3% request chậm có thể gây ra, nên vẫn còn xếp hàng ở đâu đó; agent bị giới hạn 0,5 CPU mỗi container và cả stack chạy chung một máy là khả năng hợp lý, nhưng tôi chưa đo CPU để xác nhận.

---

## 6. Kết luận

- 3 điều học được về benchmark & observability:
  1. **Average nói dối** — phải nhìn p95/p99 mới thấy tail latency mà người dùng thật chịu.
  2. **Chất lượng ≠ hạ tầng** — dashboard xanh vẫn có thể trả lời sai; cần eval + quality gate trong CI, không chỉ metrics.
  3. **So sánh phải đúng đơn vị** — "cost / câu đúng" cho quyết định tốt hơn "cost / câu" khi chọn giữa 2 phiên bản.
- Thêm cho production thật: metric theo endpoint/model, alert error-budget burn-rate (multi-window), tracing sampling, synthetic check ngoài LB (bắt lỗi 504 mà metric agent không thấy), và dashboard chất lượng (accuracy theo thời gian).
