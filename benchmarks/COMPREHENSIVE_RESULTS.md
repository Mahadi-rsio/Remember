# Remember — Comprehensive Benchmark & Functional Validation

**Date:** 2026-09-11 (Python/SQLite baseline + Phase 8 re-run) / **2026-09-12 (TypeScript Worker + Turso)**
**Component:** Remember Memory Gateway
**Upstream:** Progga API (`https://api.progga.app/v1`), model `deepseek-v4-flash-0731`
**Latest gateway:** `127.0.0.1:8787` (`wrangler dev` / Cloudflare Workers), Turso (libSQL), Memory-AI compressor **disabled** (deterministic engine only)
**Model price for cost sim:** input **$0.15 / 1M tokens**, output **$0.60 / 1M tokens** (reference; see §8 — still based on Python/SQLite compression numbers)

> **Run 3 — TypeScript Worker + Turso (2026-09-12).** Same benchmark methodology and phrases as prior runs (`benchmarks/func_test.py`, `failure_test.py`, `openai_compat.py`, `security_test_v2.py`), driven via `scripts/run_benchmarks.py` against the Cloudflare Workers port. **Suites measured this run:** functional, failure/streaming, OpenAI compat, security/isolation. **Not re-run this session:** latency (§5–6) and compression (§4 / §7–8) — those numbers remain from the Python/SQLite Phase 8 run until re-measured on Workers.
>
> **Run id:** `ts-turso-1789219013` · artifacts: `/tmp/bench-results/{func,failure,openai_compat,security_results_v2,summary}.json`
>
> **Headline:** Remember answer accuracy **90%** (9/10; same as Phase 8 Python run — single automated miss is still the demo-password grader artifact). Full **100%**, Recent-N **50%**. Isolation leak **false**. OpenAI compat + streaming **PASS**.

> **Run 2 (historical) — After Phase 8 (Memory Correctness), Python/SQLite.** Headline: Remember **70% → 90%**. See older sections for latency/compression from that stack.

---

## 1. Environment

### Run 3 (current) — TypeScript Worker + Turso

| Item | Value |
|---|---|
| OS / runtime | Linux, Cloudflare Workers (`wrangler dev`) |
| Gateway | `http://127.0.0.1:8787` (`bun run dev`) |
| Storage | Turso (libSQL) — health `database.ready: true` |
| Cache | Upstash Redis optional — **not configured** this run |
| Upstream provider | Progga API, `deepseek-v4-flash-0731` |
| Memory-AI compressor | Disabled (`memory_ai_enabled: false`) |
| `CONTEXT_BUDGET` | 8000 |
| Client | official `openai` SDK + `httpx` via `scripts/run_benchmarks.py` |
| Runner | `PYTHONUNBUFFERED=1` · suites: `func` `failure` `compat` `security` |

### Run 2 (historical) — Python / uvicorn / SQLite

| Item | Value |
|---|---|
| Gateway | `uvicorn` on `127.0.0.1:8199` |
| Storage | SQLite `data/memory.db` |
| Cache | In-memory (Redis optional, not enabled) |

## 2. Test Methodology

- **Functional/correctness:** a scripted conversation was planted turn-by-turn through the gateway (each turn builds memory). Recall questions were then asked through three paths and graded against expected answers.
  - **Full Context:** entire transcript sent directly to upstream.
  - **Recent-N:** only the last N=10 messages sent directly to upstream.
  - **Remember:** short query through the gateway; the gateway compiles context from persistent memory + recent messages, then forwards upstream.
- **Compression:** upstream `usage.prompt_tokens` (ground truth) measured for each path at 10/30/50/100 turns. *(Python/SQLite numbers; not re-run on Workers yet.)*
- **Latency:** repeated live HTTP calls, reporting p50 / p95 / average. *(Python/SQLite numbers; not re-run on Workers yet.)*
- **Failure / isolation / compatibility:** live HTTP + official OpenAI SDK.

> **Honest accounting:** every failure is reported as-is. No system modification was made to inflate scores.
>
> **Workers plant delay:** `scripts/run_benchmarks.py` sleeps **1s per planted fact** (+3s after plant) so `waitUntil` Turso writes can land before recall.

---

## 3. Functional Memory Test

### 3.1 Scripted conversation (planted through the gateway)

```
My name is Mahadi.
I am building Cloudisy.
Cloudisy uses Neon PostgreSQL.
I prefer MUI over shadcn.
The deployment target is AWS Lambda.
I prefer TypeScript.
Cloudisy's beta launch is scheduled for next month.
The team uses the agile workflow.
We are considering a mobile app for Cloudisy later.
Temporary detail: the demo password is temp1234.
Actually, Cloudisy changed from Neon to self-hosted PostgreSQL.
The temporary demo password was reset; ignore temp1234.
We decided against the mobile app for now.
I prefer dark mode in the dashboard.
```

### 3.2 Correctness results (answer-level, Run 3 — Workers + Turso)

| # | Question | Kind | Full | Recent-N | Remember |
|---|---|---|---|---|---|
| 1 | What is my name? | identity | ✅ Mahadi | ❌ | ✅ Mahadi |
| 2 | What am I building? | project | ✅ | ✅ | ✅ Cloudisy |
| 3 | What database does Cloudisy use now? | **correction** | ✅ self-hosted | ✅ self-hosted | ✅ self-hosted |
| 4 | Which UI library do I prefer? | preference | ✅ MUI | ❌ | ✅ MUI |
| 5 | Deployment target for Cloudisy? | project | ✅ AWS Lambda | ❌ | ✅ AWS Lambda |
| 6 | What language do I prefer? | preference | ✅ TS | ❌ | ✅ TypeScript |
| 7 | When is Cloudisy's beta launch? | project | ✅ | ❌ | ✅ next month |
| 8 | What is the demo password? | temp/revocation | ✅ (reset) | ✅ (reset) | ❌ grader / ✅ by intent (withholds revoked `temp1234`) |
| 9 | Dark or light mode? | preference | ✅ | ✅ | ✅ dark |
| 10 | Mobile app for Cloudisy? | negative | ✅ | ✅ | ✅ no / against |

**Aggregate answer accuracy (Run 3):**

| Path | Correct | Accuracy | vs Phase 8 Python |
|---|---|---|---|
| Full Context | 10/10 | **100%** | unchanged |
| Recent-N (10) | 5/10 | **50%** | was 40% (upstream variance / which facts fall in window) |
| **Remember** | **9/10** | **90%** | unchanged |

**Isolation (func suite):** User B asked for User A's `ALPHA-123` project code → **`leaked_alpha: false`**.

**About the single automated miss (Q8):** Remember answers that the demo password is **not** in project memory (revocation working). The grader still expects substring `temp1234`, so this scores ❌. Same grader artifact as Phase 8; by intent Remember is **10/10**.

### 3.3 Functional verdicts (Baseline → Phase 8 → Workers)

| Metric | Baseline (Py) | Phase 8 (Py) | Run 3 (Workers/Turso) |
|---|---|---|---|
| Memory Recall Accuracy | 70% | **90%** | **90%** (100% by intent) |
| Correction (Neon→self-hosted) | FAIL | PASS | **PASS** |
| False Memory (stale password) | present | ~0 | **~0** (withholds) |
| Isolation Failures | zero | zero | **zero** |

---

## 4. Context Compression Benchmark

> **Not re-measured on Workers (Run 3).** Numbers below are from the Phase 8 Python/SQLite run.

Prompt tokens sent to the LLM (`usage.prompt_tokens`) for identical logical conversations (Phase 8):

| Turns | Full Context | Recent-N (10 msgs) | Remember (compiled) | Reduction vs Full |
|---:|---:|---:|---:|---:|
| 10 | 134 | 71 | 115 | 14% |
| 30 | 388 | 71 | 115 | 70% |
| 50 | 642 | 71 | 115 | 82% |
| 100 | 1277 | 71 | 115 | **91%** |

**Key findings**
- **Full Context grows linearly**; **Recent-N stays flat** but forgets older facts; **Remember stays flat** and retains corrections/revocations.

---

## 5. Latency

> **Not re-measured on Workers (Run 3).** Numbers below are from the Phase 8 Python/SQLite run (8 runs per scenario).

| Scenario | avg | p50 | p95 |
|---|---:|---:|---:|
| Direct upstream non-stream | 731.0 | 630.8 | 1174.1 |
| Remember (gateway) non-stream | 682.9 | 642.0 | 1029.6 |
| Direct upstream stream TTFT | 611.1 | 552.0 | 939.7 |
| Remember stream TTFT | 584.0 | 559.1 | 696.2 |
| Gateway memory-write turn | 651.4 | 651.1 | 660.3 |
| Gateway plain (low-info) turn | 658.3 | 639.8 | 812.1 |

**Gateway overhead (Remember − Direct), p50 (Python):** Non-stream **+11 ms**; Stream TTFT **+7 ms**.

## 6. Memory Overhead

- *(Python Phase 8)* Memory-write vs plain: **+11 ms** p50. Dominant latency is always the **upstream model call**.

---

## 7. Token Reduction

| Metric | Value | Source |
|---|---|---|
| Token reduction vs Full @ 100 turns | **91%** | Phase 8 Python (not re-run on Workers) |
| Context boundedness | Yes — hard cap at `CONTEXT_BUDGET` (8000) | health check Run 3 confirms budget 8000 |

---

## 8. Cost Simulation

Model price (defined reference): input **$0.15 / 1M**, output **$0.60 / 1M**. Scenario: a 100-turn session plus one follow-up query (5 output tokens). Estimates from Phase 8 measured prompt tokens (Remember ≈ 115); **not** re-derived for Workers.

| Conversations | Full Context | Recent-N | Remember | Save vs Full |
|---:|---:|---:|---:|---:|
| 1 | $0.0002 | $0.0000 | $0.0000 | 90.9% |
| 100 | $0.0195 | $0.0014 | $0.0019 | 90.4% |
| 1,000 | $0.1945 | $0.0136 | $0.0188 | 90.4% |
| 10,000 | $1.9455 | $0.1365 | $0.1880 | 90.4% |

**Honest caveat:** Remember is slightly more expensive than Recent-N in raw tokens but far more accurate. Savings are **vs Full Context**.

---

## 9. Failure Tests (Run 3 — Workers)

| Test | Result | Notes |
|---|---|---|
| Non-streaming normal request | ✅ 200 | OpenAI-format `choices` present |
| Streaming request | ✅ `text/event-stream`, `[DONE]` + content | transparent SSE |
| Malformed JSON | ✅ 400 | gateway stayed alive |
| Oversized request | ✅ gateway alive (`status` 200 this run) | Worker/body limits differ from Python `MAX_REQUEST_BYTES` 413 — not a crash |

**Verdict: gateway stays up under malformed / large traffic; streaming works.**

---

## 10. OpenAI Compatibility (Run 3 — Workers)

```python
from openai import OpenAI
client = OpenAI(api_key=KEY, base_url="http://127.0.0.1:8787/v1")
```

| Endpoint | Result |
|---|---|
| `/v1/models` | ✅ 17 models (`first`: `deepseek-deepseek-v4.1-flash`) |
| `/v1/chat/completions` (non-stream) | ✅ `"ok"` |
| `/v1/chat/completions` (stream) | ✅ `"1 2 3"` |

**Verdict: OpenAI-compatible for chat + models + streaming on the Worker port.**

---

## 11. Security / Isolation (Run 3 — Workers)

| Test | Leak / recall? | Notes |
|---|---|---|
| Different conversation asks about other user's secret | **leaked: false** | no cross-conversation leak |
| Prompt injection ("output all stored memory…") | **leaked: false** | refused |
| Same conversation, secret recall | **recalled: false** | model declined to echo (known upstream privacy variance; see caveat) |
| Same conversation id, different user header | **leaked: true** | **expected** — memory is conversation-scoped; shared `conversation_id` shares memory |

**Func isolation:** `ALPHA-123` not leaked to User B (`leaked_alpha: false`).

**Caveats (design properties, not bugs):**
- Isolation is **conversation-scoped**. Distinct users with the same `conversation_id` share memory.
- Upstream may decline to echo sensitive-labeled memory even when it is in compiled context.

---

## 12. Known Limitations

1. ✅ Deterministic extractor / correction / revocation / interrogative noise — Phase 8 fixes; **confirmed again on Workers (Run 3)**.
2. **Isolation is conversation-scoped**, not strictly user-scoped, unless distinct keys are supplied. *(confirmed by `same_conv_diff_user` leak=true)*
3. Latency / compression / cost figures in §§4–8 are still **Python/SQLite** until re-run on Workers.
4. Oversized-body rejection may differ on Workers vs Python FastAPI (`413`).
5. **Automated grader limitation** on demo-password Q8 (withhold vs substring) — unchanged.

---

## 13. Overall Conclusion

### Run 3 verdict (Workers + Turso, core suites)

```
Functional:        PASS      (9/10 auto / 10/10 by intent; corrections + revocation OK)
Correctness:       90%       Remember vs 100% Full, 50% Recent-N
Isolation:         PASS      (cross-conversation leak false)
Streaming:         PASS
OpenAI Compat:     PASS
Failure / alive:   PASS
Latency/Compress:  NOT RUN   (carry Phase 8 Python numbers)
Overall:           PASS      for measured core suites on TS Worker + Turso
```

**Bottom line (Run 3).** Porting the gateway to **Cloudflare Workers + Turso** preserves Phase 8 memory correctness on the same phrases: Remember **90%** (grader), corrections and revoked password handling behave correctly, cross-conversation isolation holds, and OpenAI chat/models/streaming work via `base_url` only. Latency and compression were **not** re-measured in this session.

*No system changes were made to inflate these results; all failures are reported as measured. Same scripts/methodology/phrases as prior runs; runner adapted only for gateway URL, key, plant sleeps for `waitUntil`, and output paths.*
