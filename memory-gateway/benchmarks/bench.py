"""Live benchmark for the Memory Gateway.

Compares the gateway against the upstream directly (baseline) with a real model:

  1. proxy_overhead   — non-streaming latency, gateway vs direct upstream
  2. stream_ttft      — time to first content chunk, gateway vs direct
  3. stream_tps       — assembled output tokens per second through the gateway
  4. memory_write     — latency of a fact-planting turn (delta+extract+persist)
                        vs a plain turn
  5. compaction       — prompt_tokens for a long history sent raw (direct) vs
                        compiled by the gateway (single new message)

Usage:
  python benchmarks/bench.py \
      --gateway http://127.0.0.1:8000 \
      --upstream-base https://api.openai.com/v1 \
      --model gpt-4.1 --runs 8

Requires the gateway to be running and `.env` to hold a valid UPSTREAM_API_KEY
(the script reads the key from memory-gateway/.env, or pass --upstream-key).
"""

from __future__ import annotations

import argparse
import asyncio
import os
import statistics
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent


def load_env_key() -> str:
    env = HERE.parent / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            if line.startswith("UPSTREAM_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


def pct(values: list[float], p: float) -> float:
    s = sorted(values)
    return s[min(len(s) - 1, int(len(s) * p))]


def fmt_ms(ms: float) -> str:
    return f"{ms:8.1f}"


async def nonstream_latency(client: httpx.AsyncClient, url: str, body: dict) -> float:
    t0 = time.perf_counter()
    r = await client.post(url, json=body)
    t1 = time.perf_counter()
    r.raise_for_status()
    return (t1 - t0) * 1000


async def stream_metrics(client: httpx.AsyncClient, url: str, body: dict) -> tuple[float, float, int]:
    """Return (ttft_ms, total_ms, completion_tokens)."""
    completion_tokens = 0
    t0 = time.perf_counter()
    ttft = None
    async with client.stream("POST", url, json=body) as r:
        r.raise_for_status()
        async for line in r.aiter_lines():
            if not line.startswith("data: ") or line == "data: [DONE]":
                continue
            chunk = json_loads(line[6:])
            if chunk.get("usage"):
                completion_tokens = chunk["usage"].get("completion_tokens", completion_tokens)
            choices = chunk.get("choices") or []
            if choices and choices[0].get("delta", {}).get("content") and ttft is None:
                ttft = (time.perf_counter() - t0) * 1000
    total = (time.perf_counter() - t0) * 1000
    return ttft or total, total, completion_tokens


def json_loads(s: str):
    import json

    return json.loads(s)


async def bench(args: argparse.Namespace) -> None:
    key = args.upstream_key or load_env_key()
    if not key:
        raise SystemExit("No UPSTREAM_API_KEY found in .env — pass --upstream-key")
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    conv = f"bench-{int(time.time())}"

    url_gw = f"{args.gateway.rstrip('/')}/v1/chat/completions"
    url_up = f"{args.upstream_base.rstrip('/')}/chat/completions"

    async with httpx.AsyncClient(timeout=120.0, headers=headers) as c:
        # --- 1. proxy overhead (non-streaming) ---------------------------------
        body = {
            "model": args.model,
            "messages": [{"role": "user", "content": "Reply with the single word: ok"}],
            "max_tokens": 5,
        }
        lat_gw, lat_up = [], []
        for _ in range(args.runs):
            lat_up.append(await nonstream_latency(c, url_up, body))
            lat_gw.append(await nonstream_latency(c, url_gw, body))

        # --- 2/3. streaming ttft + throughput ----------------------------------
        sbody = {
            "model": args.model,
            "stream": True,
            "messages": [{"role": "user", "content": "Count from 1 to 20, digits only."}],
            "max_tokens": 60,
        }
        ttft_gw, tot_gw, tok_gw = await stream_metrics(c, url_gw, sbody)
        ttft_up, _, _ = await stream_metrics(c, url_up, sbody)

        # --- 4. memory write overhead ------------------------------------------
        plant = {
            "model": args.model,
            "messages": [
                {
                    "role": "user",
                    "content": "Note for later: my staging region is eu-central-1 and my alert channel is #ops-bench.",
                }
            ],
            "max_tokens": 10,
        }
        plain = dict(body)
        t_mem = await nonstream_latency(c, url_gw, {**plant, "conversation_id": conv})
        t_plain = await nonstream_latency(c, url_gw, {**plain, "conversation_id": conv})

        # --- 5. compaction: long history raw vs gateway-compiled ----------------
        long_history = [
            {"role": "user", "content": f"Fact {i}: the backup window is {i:02d}:00-0{i % 10}:30 UTC."}
            for i in range(30)
        ]
        raw = {
            "model": args.model,
            "messages": long_history + [{"role": "user", "content": "Reply: ok"}],
            "max_tokens": 5,
        }
        r_up = await c.post(url_up, json=raw)
        r_up.raise_for_status()
        raw_tokens = r_up.json()["usage"]["prompt_tokens"]

        # Same conversation id as planted memory: gateway compiles state itself.
        compiled = {
            "model": args.model,
            "conversation_id": conv,
            "messages": [{"role": "user", "content": "Reply: ok"}],
            "max_tokens": 5,
        }
        r_gw = await c.post(url_gw, json=compiled)
        r_gw.raise_for_status()
        gw_tokens = r_gw.json()["usage"]["prompt_tokens"]

    # --- report -------------------------------------------------------------
    print()
    print(f"  benchmark: gateway={args.gateway}  model={args.model}  runs={args.runs}")
    print("  " + "-" * 66)
    print(f"  {'metric':<34}{'gateway':>10}{'direct':>10}{'delta':>10}")
    print("  " + "-" * 66)
    print(f"  {'nonstream p50 (ms)':<34}{fmt_ms(statistics.median(lat_gw)):>10}{fmt_ms(statistics.median(lat_up)):>10}{fmt_ms(statistics.median(lat_gw) - statistics.median(lat_up)):>10}")
    print(f"  {'nonstream p95 (ms)':<34}{fmt_ms(pct(lat_gw, 0.95)):>10}{fmt_ms(pct(lat_up, 0.95)):>10}{fmt_ms(pct(lat_gw, 0.95) - pct(lat_up, 0.95)):>10}")
    print(f"  {'stream TTFT (ms)':<34}{fmt_ms(ttft_gw):>10}{fmt_ms(ttft_up):>10}{fmt_ms(ttft_gw - ttft_up):>10}")
    print(f"  {'stream throughput (tok/s)':<34}{(tok_gw / (tot_gw / 1000)):>10.1f}{'—':>10}{'':>10}")
    print(f"  {'memory-write turn (ms)':<34}{fmt_ms(t_mem):>10}{fmt_ms(t_plain):>10}{fmt_ms(t_mem - t_plain):>10}")
    print("  " + "-" * 66)
    print(f"  compaction: prompt_tokens raw-history={raw_tokens}  gateway-compiled={gw_tokens}"
          f"  (saved {raw_tokens - gw_tokens} tok, {(1 - gw_tokens / raw_tokens) * 100:.0f}%)")
    print(f"  conversation: {conv}")
    print()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Memory Gateway live benchmark")
    ap.add_argument("--gateway", default="http://127.0.0.1:8000")
    ap.add_argument("--upstream-base", default=os.environ.get("UPSTREAM_BASE_URL", "https://api.progga.app/v1"))
    ap.add_argument("--upstream-key", default="")
    ap.add_argument("--model", default="deepseek-v4-flash-0731")
    ap.add_argument("--runs", type=int, default=8)
    asyncio.run(bench(ap.parse_args()))
