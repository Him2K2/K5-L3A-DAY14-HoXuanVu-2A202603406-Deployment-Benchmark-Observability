# Benchmark & Observability Report — Day 14

**Họ tên:** Hồ Xuân Vũ
**MSSV:** 2A202603406
**Ngày chạy:** 2026-11-25
**Môi trường:** Windows 11 + WSL2 (Ubuntu 22.04, Python 3.10), Docker Desktop 28.0.4

> Mọi con số lấy từ file JSON trong `reports/` và CSV trong `benchmark-results/`. Không ước lượng.

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
Không. RPS tăng gần tuyến tính từ c=1 (4) → c=10 (40) → c=50 (110), nhưng đến c=100 thì **sụp** (42) và latency bùng nổ (p50 1,2s, p95 5,3s). Nguyên nhân: agent develop chạy **một uvicorn worker / một event loop**; mock LLM là `asyncio.sleep` nên chịu được song song cho tới khi event loop + CPU bão hoà. Vượt điểm bão hoà (~c=50), request xếp hàng → latency tăng vọt trong khi throughput không tăng thêm (Little's Law: khi vượt công suất, thêm concurrency chỉ làm dài hàng đợi). Muốn tăng RPS phải thêm worker/instance, không phải thêm concurrency của client.

### 2.2 Tail latency (agent v2, concurrency=20, 300 request)

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 194.9 | 225.6 | 255.3 |
| 0.03 (mặc định) | 236.4 | 252.5 | 1698.6 |
| 0.1 | 313.3 | 1690.2 | 1714.5 |

**Nhận xét:** **p99 rồi p95** là chỉ số nhạy nhất với request chậm: ở slow=0.03, p99 đã nhảy lên ~1700ms trong khi avg chỉ 236ms; ở slow=0.1, cả p95 lẫn p99 đều ~1700ms. **avg** gần như không đổi (195→313) vì nó bị "pha loãng" bởi đa số request nhanh → **không nên đặt SLO theo average** vì nó che giấu tail latency mà người dùng thực sự chịu. Đó là lý do SLO dùng p95/p99.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`, 23 câu)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | **100% (23/23)** |
| Avg tokens / câu | 55.8 | 108.7 | 115.0 |
| Tổng cost (USD) | 0.000386 | 0.000756 | 0.000802 |
| Cost / câu đúng (USD) | 0.00038595 | 0.00003599 | 0.00003487 |
| Quality gate | ❌ FAIL | ✅ PASS | ✅ PASS (exit 0) |

**Những câu v2 trả lời sai ban đầu và cách sửa (chỉ sửa `KNOWLEDGE_BASE`, không đụng `golden_dataset`):**

| ID | Keyword bị thiếu | Đã sửa gì |
|---|---|---|
| `scaling-03` | cpu, memory, custom metrics | Thêm entry KB kích hoạt bởi `kubernetes`/`hpa`, nội dung nêu HPA scale theo CPU, memory, custom metrics |
| `security-02` | token, hết hạn, chữ ký | Thêm entry KB kích hoạt bởi `jwt`/`api key`, nội dung nêu JWT có chữ ký số + thời gian hết hạn, khác API key tĩnh |

**Trade-off v1 ↔ v2:** v2 (có retrieval/RAG) tốn **~2× token** mỗi câu (108.7 vs 55.8) và cost cao hơn, nhưng accuracy nhảy từ 4.3% lên 91.3%→100%. Vì vậy **cost / câu đúng** của v2 (~$0.000036) lại **rẻ hơn ~10×** so với v1 (~$0.000386): đo "cost / câu" thì v1 rẻ hơn, nhưng đo "cost / câu *đúng*" — thứ thực sự có giá trị — thì v2 vượt trội. Đây là lý do nên so hai phiên bản bằng cost / câu đúng.

**Quality gate chặn merge (Exercise 7.3 bài 4):** `run_eval.py` trả **exit code 1** khi `accuracy < --min-accuracy` hoặc có regression so với baseline → CI dừng. Bước GitHub Actions:

```yaml
- name: Eval quality gate
  run: |
    python eval/run_eval.py --url http://localhost:8002 \
      --min-accuracy 0.9 --baseline reports/eval_baseline.json
    # exit code != 0 → step fail → chặn merge
```

(File CI mẫu: `.github/workflows/eval-gate.yml` trong repo.)

---

## 4. Observability stack (production)

### 4.1 Screenshot (trong `screenshots/`)

- [x] `grafana-dashboard.png` — Dashboard Grafana khi đang có tải (Golden Signals)
- [x] `jaeger-slow-trace.png` — trace chậm (span LLM chiếm thời gian)
- [x] `jaeger-error-trace.png` — trace lỗi (event `exception`)
- [x] `prometheus-alert-firing.png` — trang Alerts, ≥ 2 alert đang **firing**

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert firing | Thời gian đổi → firing | Panel phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `AgentHighErrorRate` | ~1 min 27 s from injection (firing after its 1-minute `for`) | Error rate (Golden Signals) |
| B | `MOCK_SLOW_RATE=0.3` | `AgentHighLatencyP95` | ~2 min 27 s from injection (firing after its 2-minute `for`) | p95 latency |
| (C) | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` | (không chạy ở lab K5) | Cost USD/giờ |
| (D) | `docker pause` 1 instance | `AgentInstanceDown` | (tham khảo) | Instances up |
| (E) | `AGENT_VERSION=v1` | *không alert nào* | — | — |

**Thí nghiệm E không làm alert firing — phát hiện bằng cách nào?** Lỗi **chất lượng** (trả lời sai) không làm metric hạ tầng (latency/error/CPU) đỏ, nên observability hạ tầng không bắt được. Phải bắt bằng **eval chất lượng** trên golden dataset chạy trong CI trước deploy, cộng feedback người dùng (thumbs up/down) và LLM-as-judge/sampling câu trả lời thật trong production.

### 4.3 Debug bằng trace

- Trace chậm — `trace_id`: `a17bf0ce7c81f4a60c0a471cd392c4aa`
- Tổng thời gian: **1,900 ms**
- Span chiếm nhiều thời gian nhất: `chat mock-llm-small`, khoảng **1,700 ms** (LLM); span retrieval khoảng 92.7 ms.
- Trace lỗi — `trace_id`: `422c849b60a17d4fbcfeb44c7e6dd8f1`; `/ask` trả HTTP 503 và span LLM có lỗi upstream.
- Dòng log tương ứng (grep theo `trace_id`):

```json
{"ts":"2026-11-25T09:23:37.756984+00:00","level":"INFO","service":"observable-agent","instance":"6d3fc25b3134","event":"llm_call","trace_id":"a17bf0ce7c81f4a60c0a471cd392c4aa","span_id":"44550a60446d15f8","request_id":"1f67da82e9b7","model":"mock-llm-small","agent_version":"v2","input_tokens":37,"output_tokens":24,"cost_usd":2e-05,"llm_ms":1660.4}
```

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 50.60 | 250 | 2,200 | 4,800 | 74 / 5,923 (1.25%) |
| 3 | 56.17 | 230 | 1,700 | 2,800 | 69 / 6,532 (1.06%) |

**Giải thích:** tăng từ 1 lên 3 instance cải thiện RPS khoảng 11%, p95 khoảng 23% và p99 khoảng 42%, nhưng không tăng tuyến tính. Mỗi request vẫn chịu độ trễ của mock LLM và request pacing của Locust; thêm instance giúp giảm hàng đợi nhưng không làm phần chờ LLM biến mất. Kết quả này chỉ phản ánh mock stack và giới hạn tài nguyên cục bộ.

---

## 6. Kết luận

- 3 điều học được về benchmark & observability:
  1. **Average nói dối** — phải nhìn p95/p99 mới thấy tail latency mà người dùng thật chịu.
  2. **Chất lượng ≠ hạ tầng** — dashboard xanh vẫn có thể trả lời sai; cần eval + quality gate trong CI, không chỉ metrics.
  3. **So sánh phải đúng đơn vị** — "cost / câu đúng" cho quyết định tốt hơn "cost / câu" khi chọn giữa 2 phiên bản.
- Thêm cho production thật: metric theo endpoint/model, alert error-budget burn-rate (multi-window), tracing sampling, synthetic check ngoài LB (bắt lỗi 504 mà metric agent không thấy), và dashboard chất lượng (accuracy theo thời gian).
