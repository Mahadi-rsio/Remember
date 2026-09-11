"""Context compression benchmark: Full vs Recent-N vs Remember.

For identical logical conversations of increasing length (10/30/50/100 turns),
measures prompt (input) tokens sent to the LLM under each configuration.

- Full Context: entire transcript sent directly to upstream
- Recent-N: only the latest N messages sent directly to upstream (N = last 10 turns)
- Remember: conversation built through the gateway; a short follow-up query is
  compiled by the gateway's memory engine, then sent upstream.

Token counts come from the upstream `usage.prompt_tokens` field (ground truth,
not the gateway's heuristic).
"""
from __future__ import annotations

import json
import time
import statistics

import httpx

GATEWAY = "http://127.0.0.1:8199/v1"
UPSTREAM = "https://api.progga.app/v1"
MODEL = "deepseek-v4-flash-0731"
KEY = "progga_goBPgKimwf8I9YiOCFpWJGyCnCBKwpWX55B1vvP0HdsA2GgP"
HEADERS = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

# A realistic conversation generator producing "turns" of user + assistant.
# Uses varied facts that the deterministic extractor recognizes so memory grows.


def make_fact(i: int) -> str:
    topics = [
        "name",
        "project",
        "ui_library",
        "language",
        "region",
        "channel",
        "stack",
        "budget",
        "deadline",
        "owner",
    ]
    t = topics[i % len(topics)]
    if t == "name":
        return f"My name is User{i}."
    if t == "project":
        return f"I am building Project{i}."
    if t == "ui_library":
        return f"I prefer MUI for project {i}."
    if t == "language":
        return f"I prefer TypeScript for project {i}."
    if t == "region":
        return f"The region is eu-west-{i % 3}."
    if t == "channel":
        return f"The alert channel is #team-{i}."
    if t == "stack":
        return f"The stack uses Postgres for project {i}."
    if t == "budget":
        return f"The budget is {i * 1000} dollars."
    if t == "deadline":
        return f"The deadline is Q{i % 4 + 1}."
    return f"The owner is Alice{i}."


def build_transcript(n_turns):
    """n_turns user turns + n_turns assistant ack turns (2x messages)."""
    transcript = []
    for i in range(n_turns):
        transcript.append({"role": "user", "content": make_fact(i)})
        transcript.append({"role": "assistant", "content": "ok"})
    return transcript


def post_json(url, payload, timeout=300, client=None):
    last = None
    for attempt in range(3):
        try:
            c = client or httpx
            r = c.post(url, json=payload, headers=HEADERS, timeout=timeout)
            r.raise_for_status()
            return r
        except Exception as e:
            last = e
            time.sleep(1.0 * (attempt + 1))
    raise last


def measure_prompt(messages, timeout=300, client=None):
    """Send messages directly to upstream, return prompt_tokens and latency."""
    body = {"model": MODEL, "messages": messages, "max_tokens": 5}
    t0 = time.perf_counter()
    r = post_json(f"{UPSTREAM}/chat/completions", body, timeout, client=client)
    t1 = time.perf_counter()
    usage = r.json()["usage"]
    return {
        "prompt_tokens": usage["prompt_tokens"],
        "completion_tokens": usage["completion_tokens"],
        "total_tokens": usage["total_tokens"],
        "latency_ms": (t1 - t0) * 1000,
    }


def plant_and_measure_remember(conv, n_turns, timeout=300, client=None):
    """Plant n_turns through gateway, then send short query; return compiled metrics."""
    # Plant each turn
    for i in range(n_turns):
        fact = make_fact(i)
        payload = {"model": MODEL, "conversation_id": conv, "messages": [{"role": "user", "content": fact}], "max_tokens": 3}
        post_json(f"{GATEWAY}/chat/completions", payload, timeout, client=client)
    # Short follow-up query to trigger compilation
    payload = {"model": MODEL, "conversation_id": conv, "messages": [{"role": "user", "content": "Reply: ok"}], "max_tokens": 5}
    t0 = time.perf_counter()
    r = post_json(f"{GATEWAY}/chat/completions", payload, timeout, client=client)
    t1 = time.perf_counter()
    usage = r.json()["usage"]
    return {
        "prompt_tokens": usage["prompt_tokens"],
        "completion_tokens": usage["completion_tokens"],
        "total_tokens": usage["total_tokens"],
        "latency_ms": (t1 - t0) * 1000,
    }


def main():
    sizes = [10, 30, 50, 100]
    recent_n = 10  # Recent-N baseline: last 10 messages
    results = {}

    with httpx.Client(timeout=300) as client:
        for size in sizes:
            print(f"=== size {size} turns ===")
            transcript = build_transcript(size)
            # Full context: entire transcript + short query
            full_msgs = transcript + [{"role": "user", "content": "Reply: ok"}]
            full = measure_prompt(full_msgs, client=client)
            # Recent-N: last recent_n messages + short query
            recent_msgs = transcript[-recent_n:] + [{"role": "user", "content": "Reply: ok"}]
            recent = measure_prompt(recent_msgs, client=client)
            # Remember: plant and measure compiled context
            conv = f"bench-compress-{size}-{int(time.time())}"
            rem = plant_and_measure_remember(conv, size, client=client)

            results[size] = {
                "full_prompt_tokens": full["prompt_tokens"],
                "recentN_prompt_tokens": recent["prompt_tokens"],
                "remember_prompt_tokens": rem["prompt_tokens"],
                "full_latency_ms": round(full["latency_ms"], 1),
                "recentN_latency_ms": round(recent["latency_ms"], 1),
                "remember_latency_ms": round(rem["latency_ms"], 1),
            }
            print(f"  full={full['prompt_tokens']}  recentN={recent['prompt_tokens']}  remember={rem['prompt_tokens']}")
            time.sleep(0.3)

    with open("/tmp/opencode/compression_results.json", "w") as fh:
        json.dump(results, fh, indent=2)
    print("\nSaved /tmp/opencode/compression_results.json")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
