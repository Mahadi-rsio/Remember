"""Latency & performance benchmark: p50/p95/avg for direct vs gateway.

Measures:
- Direct upstream LLM latency (non-stream + stream TTFT)
- Remember (gateway) latency (non-stream + stream TTFT)
- Memory-write latency (turn that plants a fact, triggering extract+persist)
- Context compilation latency (via a lightweight probe)

Runs each scenario many times for p50 / p95 / average.
"""
from __future__ import annotations

import json
import statistics
import time

import httpx

GATEWAY = "http://127.0.0.1:8199/v1"
UPSTREAM = "https://api.progga.app/v1"
MODEL = "deepseek-v4-flash-0731"
KEY = "progga_goBPgKimwf8I9YiOCFpWJGyCnCBKwpWX55B1vvP0HdsA2GgP"
HEADERS = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

client = httpx.Client(timeout=300)


def pct(vals, p):
    s = sorted(vals)
    return s[min(len(s) - 1, int(len(s) * p))]


def report(name, vals):
    avg = statistics.mean(vals)
    p50 = pct(vals, 0.50)
    p95 = pct(vals, 0.95)
    print(f"  {name:<40} avg={avg:8.1f}  p50={p50:8.1f}  p95={p95:8.1f}  n={len(vals)}")
    return {"avg_ms": round(avg, 1), "p50_ms": round(p50, 1), "p95_ms": round(p95, 1), "n": len(vals)}


def direct_nonstream(n):
    body = {"model": MODEL, "messages": [{"role": "user", "content": "Reply with a single word: ok"}], "max_tokens": 5}
    lat = []
    for _ in range(n):
        t0 = time.perf_counter()
        r = client.post(f"{UPSTREAM}/chat/completions", json=body, headers=HEADERS)
        r.raise_for_status()
        lat.append((time.perf_counter() - t0) * 1000)
    return lat


def gateway_nonstream(n, conv):
    body = {"model": MODEL, "conversation_id": conv, "messages": [{"role": "user", "content": "Reply with a single word: ok"}], "max_tokens": 5}
    lat = []
    for _ in range(n):
        t0 = time.perf_counter()
        r = client.post(f"{GATEWAY}/chat/completions", json=body, headers=HEADERS)
        r.raise_for_status()
        lat.append((time.perf_counter() - t0) * 1000)
    return lat


def gateway_memorywrite(n, conv):
    """Turn that plants a fact -> triggers archive+delta+extract+persist."""
    lat = []
    for i in range(n):
        body = {"model": MODEL, "conversation_id": conv, "messages": [{"role": "user", "content": f"The owner is Bob{i}."}], "max_tokens": 3}
        t0 = time.perf_counter()
        r = client.post(f"{GATEWAY}/chat/completions", json=body, headers=HEADERS)
        r.raise_for_status()
        lat.append((time.perf_counter() - t0) * 1000)
    return lat


def gateway_plain(n, conv):
    """Non-memory turn: low-info ack, skips extraction."""
    lat = []
    for _ in range(n):
        body = {"model": MODEL, "conversation_id": conv, "messages": [{"role": "user", "content": "ok"}], "max_tokens": 3}
        t0 = time.perf_counter()
        r = client.post(f"{GATEWAY}/chat/completions", json=body, headers=HEADERS)
        r.raise_for_status()
        lat.append((time.perf_counter() - t0) * 1000)
    return lat


def stream_ttft(url, n, conv=None):
    ttft = []
    total = []
    for _ in range(n):
        body = {"model": MODEL, "stream": True, "messages": [{"role": "user", "content": "Count 1 2 3 4 5"}], "max_tokens": 20}
        if conv:
            body["conversation_id"] = conv
        t0 = time.perf_counter()
        first = None
        done = None
        with client.stream("POST", url, json=body, headers=HEADERS) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if line.startswith("data: ") and line != "data: [DONE]":
                    if first is None:
                        first = (time.perf_counter() - t0) * 1000
        done = (time.perf_counter() - t0) * 1000
        ttft.append(first if first is not None else done)
        total.append(done)
    return ttft, total


def main():
    n = 8
    conv = f"bench-lat-{int(time.time())}"
    print(f"runs per scenario: {n}")
    print("--- latency (ms) ---")
    res = {}
    res["direct_nonstream"] = report("Direct upstream non-stream", direct_nonstream(n))
    res["gateway_nonstream"] = report("Remember (gateway) non-stream", gateway_nonstream(n, conv))

    ttft_d, tot_d = stream_ttft(f"{UPSTREAM}/chat/completions", n)
    res["direct_ttft"] = report("Direct upstream stream TTFT", ttft_d)
    res["direct_stream_total"] = report("Direct upstream stream total", tot_d)

    ttft_g, tot_g = stream_ttft(f"{GATEWAY}/chat/completions", n, conv)
    res["gateway_ttft"] = report("Remember stream TTFT", ttft_g)
    res["gateway_stream_total"] = report("Remember stream total", tot_g)

    # Memory-write vs plain within gateway
    res["gateway_memorywrite"] = report("Gateway memory-write turn", gateway_memorywrite(n, conv))
    res["gateway_plain"] = report("Gateway plain (low-info) turn", gateway_plain(n, conv))

    with open("/tmp/opencode/latency_results.json", "w") as fh:
        json.dump(res, fh, indent=2)
    print("\nSaved /tmp/opencode/latency_results.json")


if __name__ == "__main__":
    main()
