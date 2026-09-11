"""Long-session scaling benchmark for the Memory Gateway.

Two parts:

Part A — realistic large memory (real extraction via turns):
  - Seeds N distinct facts in one conversation (real delta/archive/extract path).
  - Measures per-turn hot-path latency (p50 over M follow-up turns).
  - Checks compiled prompt_tokens stays <= CONTEXT_BUDGET.
  - Tests recall of an OLD (first) fact vs a RECENT fact via single-message turns.

Part B — isolated load/compile scaling (bulk-seeded memory, no network extraction):
  - Bulk-inserts synthetic memory_items (K items) for a conversation.
  - Measures hot-path latency for 100 / 1000 / 3000 items.
  - Confirms compiled context stays under budget and a high-importance fact is recalled.

Usage:
  python benchmarks/scale.py --gateway http://127.0.0.1:8000 \
      --model deepseek-v4-flash-0731 --seed 40 --followups 5

Requires the gateway to be running with .env configured. Costs a handful of
real upstream calls on a cheap model.
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sqlite3
import time
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
DB = HERE.parent / "data" / "memory.db"


def pct(vals: list[float], p: float) -> float:
    s = sorted(vals)
    return s[min(len(s) - 1, int(len(s) * p))]


async def chat(c: httpx.AsyncClient, url: str, body: dict, conv: str | None = None) -> tuple[dict, float]:
    headers = {"X-Conversation-Id": conv} if conv else None
    t0 = time.perf_counter()
    r = await c.post(url, json=body, headers=headers)
    dt = (time.perf_counter() - t0) * 1000
    r.raise_for_status()
    return r.json(), dt


async def part_a(args, c: httpx.AsyncClient, url: str) -> None:
    conv = f"scale-a-{int(time.time())}"
    print(f"\n=== Part A: realistic large memory (seed {args.seed} facts) ===")
    print(f"conversation: {conv}\n")

    body = {
        "model": args.model,
        "messages": [{"role": "user", "content": "placeholder"}],
        "max_tokens": 5,
    }
    seed_start = time.perf_counter()
    for i in range(1, args.seed + 1):
        body["messages"][0]["content"] = (
            f"Remember catalog entry {i}: feature grommet-{i} is assigned to "
            f"owner alice-{i % 7} with priority p{i % 5} and status active."
        )
        await chat(c, url, body, conv=conv)
    seed_s = time.perf_counter() - seed_start

    # hot-path latency over follow-up turns (single new message each)
    lats: list[float] = []
    for i in range(args.followups):
        body["messages"][0]["content"] = f"reply with the word ok (round {i})"
        _, dt = await chat(c, url, body, conv=conv)
        lats.append(dt)

    # recall: oldest fact (entry 1) and a recent fact (entry N) — no history sent
    old, _ = await chat(c, url, {
        **body, "messages": [{"role": "user", "content": "Which owner is assigned catalog entry 1? One word only."}],
        "max_tokens": 8,
    }, conv=conv)
    recent, _ = await chat(c, url, {
        **body, "messages": [{"role": "user", "content": f"Which owner is assigned catalog entry {args.seed}? One word only."}],
        "max_tokens": 8,
    }, conv=conv)

    print(f"  seed: {args.seed} facts in {seed_s:.1f}s ({seed_s/args.seed*1000:.0f} ms/turn seed)")
    print(f"  hot-path follow-up p50: {statistics.median(lats):.0f} ms | p95: {pct(lats, 0.95):.0f} ms")
    print(f"  compiled prompt_tokens (recall turns): old={old['usage']['prompt_tokens']}, recent={recent['usage']['prompt_tokens']} (budget 8000)")
    print(f"  recall old(entry1)  -> {old['choices'][0]['message']['content'].strip()!r}  (expected 'alice-1')")
    print(f"  recall recent(entry{args.seed}) -> {recent['choices'][0]['message']['content'].strip()!r}  (expected 'alice-{args.seed % 7}')")

    n = sqlite_count(f"SELECT COUNT(*) FROM memory_items WHERE conversation_id='{conv}'")
    print(f"  memory_items for conversation: {n}")
    return conv


def sqlite_count(q: str) -> int:
    con = sqlite3.connect(str(DB))
    try:
        return con.execute(q).fetchone()[0]
    finally:
        con.close()


def bulk_seed(conv: str, k: int) -> None:
    con = sqlite3.connect(str(DB))
    cur = con.cursor()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    for i in range(1, k + 1):
        cur.execute(
            "INSERT INTO memory_items (conversation_id, content, type, topic_key, confidence, "
            "importance, stability, freshness, information_gain, source_message_ids_json, "
            "status, version, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                conv, f"archive fact {i}: service node-{i} region us-east uses port {10000 + i}.",
                "fact", f"node-{i}", 0.8, 0.3, 0.5, 0.5, 0.2, "[]", "active", 1, now, now,
            ),
        )
    con.commit()
    con.close()


async def part_b(args, c: httpx.AsyncClient, url: str) -> None:
    print("\n=== Part B: isolated load/compile scaling (bulk-seeded, no extraction) ===")
    base = {
        "model": args.model,
        "messages": [{"role": "user", "content": "reply ok"}],
        "max_tokens": 5,
    }
    for k in (100, 1000, 3000):
        conv = f"scale-b-{k}-{int(time.time())}"
        bulk_seed(conv, k)
        # high-importance sentinel fact to test recall over noise
        con = sqlite3.connect(str(DB))
        con.execute(
            "UPDATE memory_items SET importance=1.0, content='SENTINEL: the master password is ORCHID-7.' "
            "WHERE conversation_id=? AND id=(SELECT MIN(id) FROM memory_items WHERE conversation_id=?)",
            (conv, conv),
        )
        con.commit(); con.close()

        lats = []
        for _ in range(4):
            _, dt = await chat(c, url, {**base}, conv=conv)
            lats.append(dt)
        sentinel, _ = await chat(c, url, {
            **base,
            "messages": [{"role": "user", "content": "What is the master password? One phrase."}],
            "max_tokens": 8,
        }, conv=conv)
        print(f"  {k:>5} items | hot-path p50 {statistics.median(lats):6.0f} ms | "
              f"compiled prompt_tokens {sentinel['usage']['prompt_tokens']:5d} | "
              f"recall: {sentinel['choices'][0]['message']['content'].strip()!r}")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--gateway", default="http://127.0.0.1:8000")
    ap.add_argument("--model", default="deepseek-v4-flash-0731")
    ap.add_argument("--seed", type=int, default=40)
    ap.add_argument("--followups", type=int, default=5)
    args = ap.parse_args()

    url = f"{args.gateway.rstrip('/')}/v1/chat/completions"
    async with httpx.AsyncClient(timeout=120.0) as c:
        await part_a(args, c, url)
        await part_b(args, c, url)


if __name__ == "__main__":
    asyncio.run(main())
