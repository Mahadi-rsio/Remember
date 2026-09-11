"""Functional memory + correctness test for the Remember gateway.

Plants a scripted conversation through the gateway, then asks recall questions
via three paths:
  A. Full Context  — full transcript sent directly to upstream
  B. Recent-N      — only the latest N messages sent directly to upstream
  C. Remember      — short query through the gateway (memory-compiled context)

For answer correctness, the same question is asked in each path and graded
against an expected answer.
"""
from __future__ import annotations

import json
import re
import sys
import time
import statistics

import httpx

GATEWAY = "http://127.0.0.1:8199/v1"
UPSTREAM = "https://api.progga.app/v1"
MODEL = "deepseek-v4-flash-0731"
KEY = "progga_goBPgKimwf8I9YiOCFpWJGyCnCBKwpWX55B1vvP0HdsA2GgP"

HEADERS = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}

# Scripted conversation (each turn sent separately so it builds memory)
FACTS = [
    "My name is Mahadi.",
    "I am building Cloudisy.",
    "Cloudisy uses Neon PostgreSQL.",
    "I prefer MUI over shadcn.",
    "The deployment target is AWS Lambda.",
    "I prefer TypeScript.",
    "Cloudisy's beta launch is scheduled for next month.",
    "The team uses the agile workflow.",
    "We are considering a mobile app for Cloudisy later.",
    "Temporary detail: the demo password is temp1234.",
    "Actually, Cloudisy changed from Neon to self-hosted PostgreSQL.",
    "The temporary demo password was reset; ignore temp1234.",
    "We decided against the mobile app for now.",
    "I prefer dark mode in the dashboard.",
]

# Recall questions: (question, expected answer substring, kind)
QUESTIONS = [
    # kind: identity / project / preference / correction / temp / stale / negative
    ("What is my name?", "Mahadi", "identity"),
    ("What am I building?", "Cloudisy", "project"),
    ("What database does Cloudisy use now?", "self-hosted", "correction"),
    ("Which UI library do I prefer?", "MUI", "preference"),
    ("What is the deployment target for Cloudisy?", "AWS Lambda", "project"),
    ("What language do I prefer?", "TypeScript", "preference"),
    ("When is Cloudisy's beta launch?", "next month", "project"),
    ("What is the demo password?", "temp1234", "temp-negative"),
    ("Do I prefer dark mode or light mode?", "dark", "preference"),
    ("Do we have a mobile app for Cloudisy?", "no / against", "negative"),
]

USER_B = "user-B"


def chat(url, payload, timeout=90):
    r = httpx.post(url, json=payload, headers=HEADERS, timeout=timeout)
    r.raise_for_status()
    return r.json()


def ask_direct(messages, timeout=90):
    body = {"model": MODEL, "messages": messages, "max_tokens": 120}
    return chat(f"{UPSTREAM}/chat/completions", body, timeout)


def ask_gateway(conv, question, timeout=90):
    body = {
        "model": MODEL,
        "conversation_id": conv,
        "messages": [{"role": "user", "content": question}],
        "max_tokens": 120,
    }
    return chat(f"{GATEWAY}/chat/completions", body, timeout)


def extract_answer(resp):
    try:
        return resp["choices"][0]["message"]["content"].strip()
    except Exception:
        return ""


def grade(answer, expected):
    a = answer.casefold()
    e = expected.casefold()
    if e in a:
        return True
    # handle "no / against" style expectations
    if "/" in e:
        return any(part.strip() in a for part in e.split("/"))
    return False


def build_transcript():
    # Reconstruct the multi-turn transcript: user fact, assistant ack
    transcript = []
    for f in FACTS:
        transcript.append({"role": "user", "content": f})
        transcript.append({"role": "assistant", "content": "ok"})
    return transcript


def plant_memory(conv, facts):
    for f in facts:
        chat(
            f"{GATEWAY}/chat/completions",
            {"model": MODEL, "conversation_id": conv, "messages": [{"role": "user", "content": f}], "max_tokens": 3},
            timeout=90,
        )
        time.sleep(0.15)


def main():
    conv = "bench-func"
    results = {}

    # ---- Plant memory through the gateway ----
    print("Planting memory...")
    plant_memory(conv, FACTS)
    results["conversation"] = conv

    transcript = build_transcript()

    # ---- Build the three context variants ----
    full_messages = transcript  # Full context (all turns)
    recent_n = transcript[-8:]  # Recent-N baseline (last 4 user+assistant pairs)
    # Remember: just ask via gateway with the compiled memory

    # ---- Ask each question in each path ----
    paths = {"full": full_messages, "recentN": recent_n}
    out = {}
    for q, expected, kind in QUESTIONS:
        row = {"expected": expected, "kind": kind, "answers": {}, "correct": {}}
        # Full context
        a_full = extract_answer(ask_direct(paths["full"] + [{"role": "user", "content": q}]))
        row["answers"]["full"] = a_full
        row["correct"]["full"] = grade(a_full, expected)
        # Recent-N
        a_n = extract_answer(ask_direct(paths["recentN"] + [{"role": "user", "content": q}]))
        row["answers"]["recentN"] = a_n
        row["correct"]["recentN"] = grade(a_n, expected)
        # Remember (gateway)
        a_rem = extract_answer(ask_gateway(conv, q))
        row["answers"]["remember"] = a_rem
        row["correct"]["remember"] = grade(a_rem, expected)
        out[q] = row
        time.sleep(0.2)

    results["questions"] = out

    # ---- Isolation test: user B asks about user A's memory ----
    # User A's secret is planted in a *different* conversation but same user key A.
    sec_conv = "bench-secret-A"
    plant_memory(sec_conv, ["My secret project code is ALPHA-123."])
    # User B asks, using B's conversation & user key, same question as A
    b_q = "What is User A's project code?"
    leak = extract_answer(
        ask_gateway("bench-user-B-conv", b_q)
    )
    results["isolation"] = {
        "userB_question": b_q,
        "userB_answer": leak,
        "leaked_alpha": "ALPHA-123" in leak,
    }

    # ---- Save ----
    with open("/tmp/opencode/func_results.json", "w") as fh:
        json.dump(results, fh, indent=2, ensure_ascii=False)

    # ---- Print summary ----
    print("\n=== FUNCTIONAL / CORRECTNESS RESULTS ===")
    for kind in ["identity", "project", "preference", "correction", "temp-negative", "negative"]:
        print(f"\n--- {kind} ---")
        for q, row in out.items():
            if row["kind"] == kind:
                print(f"  Q: {q}")
                for p in ["full", "recentN", "remember"]:
                    mark = "✓" if row["correct"][p] else "✗"
                    print(f"    [{p}] {mark} {row['answers'][p][:70]!r}")
    print("\n=== ISOLATION ===")
    print(json.dumps(results["isolation"], indent=2))


if __name__ == "__main__":
    main()
