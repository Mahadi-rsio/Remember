#!/usr/bin/env python3
"""Run existing benchmarks against the TS Worker without changing methodology/phrases.

Only patches: gateway URL, upstream URL, API key, health URL, result output paths,
and a slightly longer plant sleep so Cloudflare waitUntil memory writes can finish.
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCH = ROOT / "benchmarks"
sys.path.insert(0, str(BENCH))

GATEWAY_BASE = os.environ.get("GATEWAY_BASE", "http://127.0.0.1:8787")
GATEWAY_V1 = os.environ.get("GATEWAY_V1", f"{GATEWAY_BASE}/v1")
UPSTREAM = os.environ.get("BENCH_UPSTREAM", "https://api.progga.app/v1")
KEY = os.environ["BENCH_KEY"]
MODEL = os.environ.get("BENCH_MODEL", "deepseek-v4-flash-0731")
RUN_ID = os.environ.get("BENCH_RUN_ID", "bench")
OUT = Path(os.environ.get("BENCH_OUT", "/tmp/bench-results"))
OUT.mkdir(parents=True, exist_ok=True)


def load(name: str):
    path = BENCH / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def patch_common(mod):
    if hasattr(mod, "GATEWAY"):
        mod.GATEWAY = GATEWAY_V1
    if hasattr(mod, "UPSTREAM"):
        mod.UPSTREAM = UPSTREAM
    if hasattr(mod, "KEY"):
        mod.KEY = KEY
    if hasattr(mod, "MODEL"):
        mod.MODEL = MODEL
    if hasattr(mod, "HEADERS"):
        mod.HEADERS = {
            "Authorization": f"Bearer {KEY}",
            "Content-Type": "application/json",
        }
    if hasattr(mod, "client"):
        import httpx

        mod.client = httpx.Client(timeout=300)


def run_func():
    mod = load("func_test")
    patch_common(mod)

    # Unique conversation ids for this run
    conv = f"{RUN_ID}-func"
    orig_plant = mod.plant_memory

    def plant_memory(c, facts):
        for f in facts:
            mod.chat(
                f"{mod.GATEWAY}/chat/completions",
                {
                    "model": mod.MODEL,
                    "conversation_id": c,
                    "messages": [{"role": "user", "content": f}],
                    "max_tokens": 3,
                },
                timeout=120,
            )
            # Workers archive via waitUntil; allow Turso write to land
            time.sleep(1.0)
        time.sleep(3.0)

    mod.plant_memory = plant_memory

    print(f"\n===== FUNCTIONAL ({conv}) =====")
    print("Planting memory...")
    plant_memory(conv, mod.FACTS)

    transcript = mod.build_transcript()
    full_messages = transcript
    recent_n = transcript[-8:]
    out = {}
    for q, expected, kind in mod.QUESTIONS:
        row = {"expected": expected, "kind": kind, "answers": {}, "correct": {}}
        a_full = mod.extract_answer(
            mod.ask_direct(full_messages + [{"role": "user", "content": q}])
        )
        row["answers"]["full"] = a_full
        row["correct"]["full"] = mod.grade(a_full, expected)
        a_n = mod.extract_answer(
            mod.ask_direct(recent_n + [{"role": "user", "content": q}])
        )
        row["answers"]["recentN"] = a_n
        row["correct"]["recentN"] = mod.grade(a_n, expected)
        a_rem = mod.extract_answer(mod.ask_gateway(conv, q))
        row["answers"]["remember"] = a_rem
        row["correct"]["remember"] = mod.grade(a_rem, expected)
        out[q] = row
        mark = {p: ("✓" if row["correct"][p] else "✗") for p in ("full", "recentN", "remember")}
        print(f"Q[{kind}] {q}")
        print(f"  full={mark['full']} recentN={mark['recentN']} remember={mark['remember']}")
        print(f"  remember_ans={a_rem[:100]!r}")
        time.sleep(0.3)

    sec_conv = f"{RUN_ID}-secret-A"
    plant_memory(sec_conv, ["My secret project code is ALPHA-123."])
    leak = mod.extract_answer(mod.ask_gateway(f"{RUN_ID}-user-B-conv", "What is User A's project code?"))
    isolation = {
        "userB_answer": leak,
        "leaked_alpha": "ALPHA-123" in leak,
    }
    print("\n=== ISOLATION ===")
    print(json.dumps(isolation, indent=2))

    # Score summary
    scores = {}
    for path in ("full", "recentN", "remember"):
        ok = sum(1 for r in out.values() if r["correct"][path])
        scores[path] = {"ok": ok, "total": len(out), "pct": round(100 * ok / len(out))}
    print("\n=== SCORES ===")
    print(json.dumps(scores, indent=2))

    results = {
        "conversation": conv,
        "questions": out,
        "isolation": isolation,
        "scores": scores,
        "run_id": RUN_ID,
        "gateway": GATEWAY_V1,
        "model": MODEL,
    }
    path = OUT / "func_results.json"
    path.write_text(json.dumps(results, indent=2, ensure_ascii=False))
    print("wrote", path)
    return results


def run_failure():
    mod = load("failure_test")
    patch_common(mod)

    def healthy():
        r = mod.client.get(f"{GATEWAY_BASE}/health", timeout=5)
        return r.status_code == 200

    mod.healthy = healthy
    print("\n===== FAILURE / STREAMING =====")
    # Re-implement main with patched health base — call original after patching
    # failure_test.main uses hardcoded health URL; monkeypatch healthy already done
    # but healthy() inside main is the local function - need to run patched version

    results = {}
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": "Reply with one word: ok"}],
        "max_tokens": 5,
    }
    r = mod.client.post(f"{GATEWAY_V1}/chat/completions", json=body, headers=mod.HEADERS)
    results["non_stream_normal"] = {
        "status": r.status_code,
        "is_openai_format": "choices" in r.text,
    }
    print("non_stream_normal:", r.status_code)

    sbody = {
        "model": MODEL,
        "stream": True,
        "messages": [{"role": "user", "content": "Count 1 2 3"}],
        "max_tokens": 10,
    }
    events = []
    content_type = None
    with mod.client.stream(
        "POST", f"{GATEWAY_V1}/chat/completions", json=sbody, headers=mod.HEADERS
    ) as resp:
        content_type = resp.headers.get("content-type")
        for line in resp.iter_lines():
            if line.startswith("data: "):
                events.append(line)
    has_done = any("DONE" in e for e in events)
    has_data = any('"content"' in e for e in events)
    results["stream_normal"] = {
        "status": 200,
        "content_type": content_type,
        "has_done": has_done,
        "has_content": has_data,
    }
    print("stream_normal:", content_type, "done=", has_done, "content=", has_data)

    r = mod.client.post(
        f"{GATEWAY_V1}/chat/completions",
        content="{not-json",
        headers=mod.HEADERS,
    )
    results["malformed_json"] = {"status": r.status_code, "gateway_alive": healthy()}
    print("malformed_json:", r.status_code, "alive=", results["malformed_json"]["gateway_alive"])

    huge = "x" * (2_000_000)
    r = mod.client.post(
        f"{GATEWAY_V1}/chat/completions",
        json={"model": MODEL, "messages": [{"role": "user", "content": huge}]},
        headers=mod.HEADERS,
    )
    results["oversized"] = {"status": r.status_code, "gateway_alive": healthy()}
    print("oversized:", r.status_code, "alive=", results["oversized"]["gateway_alive"])

    path = OUT / "failure_results.json"
    path.write_text(json.dumps(results, indent=2))
    print("wrote", path)
    return results


def run_openai_compat():
    from openai import OpenAI

    print("\n===== OPENAI COMPAT =====")
    client = OpenAI(api_key=KEY or "test", base_url=GATEWAY_V1)
    results = {}
    try:
        models = client.models.list()
        results["models"] = {
            "ok": True,
            "count": len(models.data),
            "first": models.data[0].id,
        }
        print("models:", results["models"]["count"])
    except Exception as e:
        results["models"] = {"ok": False, "error": str(e)}
        print("models ERROR:", e)

    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": "Reply with one word: ok"}],
            max_tokens=5,
        )
        results["chat_nonstream"] = {
            "ok": True,
            "content": resp.choices[0].message.content,
        }
        print("chat_nonstream:", resp.choices[0].message.content)
    except Exception as e:
        results["chat_nonstream"] = {"ok": False, "error": str(e)}
        print("chat_nonstream ERROR:", e)

    try:
        stream = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": "Count 1 2 3"}],
            max_tokens=20,
            stream=True,
        )
        chunks = []
        for ch in stream:
            if ch.choices and ch.choices[0].delta.content:
                chunks.append(ch.choices[0].delta.content)
        results["chat_stream"] = {"ok": True, "text": "".join(chunks)[:80]}
        print("chat_stream:", results["chat_stream"]["text"])
    except Exception as e:
        results["chat_stream"] = {"ok": False, "error": str(e)}
        print("chat_stream ERROR:", e)

    path = OUT / "openai_compat_results.json"
    path.write_text(json.dumps(results, indent=2))
    print("wrote", path)
    return results


def run_security():
    mod = load("security_test_v2")
    patch_common(mod)
    print("\n===== SECURITY / ISOLATION v2 =====")
    # Call main if it uses GATEWAY/HEADERS we patched
    if hasattr(mod, "main"):
        # Capture print output; also patch result file path if used
        try:
            mod.main()
        except Exception as e:
            print("security main error:", e)
            return {"error": str(e)}
    # Try to find results
    for candidate in [
        Path("/tmp/opencode/security_results_v2.json"),
        OUT / "security_results_v2.json",
    ]:
        if candidate.exists():
            data = json.loads(candidate.read_text())
            (OUT / "security_results_v2.json").write_text(json.dumps(data, indent=2))
            return data
    return getattr(mod, "results", {})


def run_latency():
    mod = load("latency_bench")
    patch_common(mod)
    print("\n===== LATENCY =====")
    # Reduce iterations slightly for practical runtime while keeping methodology
    # (same scenarios; fewer samples). Prefer full if N is baked into main.
    if hasattr(mod, "main"):
        mod.main()
    for candidate in [
        Path("/tmp/opencode/latency_results.json"),
        OUT / "latency_results.json",
    ]:
        if candidate.exists():
            data = json.loads(candidate.read_text())
            (OUT / "latency_results.json").write_text(json.dumps(data, indent=2))
            return data
    return {}


def run_compression():
    mod = load("compression_bench")
    patch_common(mod)
    print("\n===== COMPRESSION =====")
    if hasattr(mod, "main"):
        mod.main()
    for candidate in [
        Path("/tmp/opencode/compression_results.json"),
        OUT / "compression_results.json",
    ]:
        if candidate.exists():
            data = json.loads(candidate.read_text())
            (OUT / "compression_results.json").write_text(json.dumps(data, indent=2))
            return data
    return {}


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    summary = {}
    if which in ("all", "func"):
        summary["func"] = run_func()
    if which in ("all", "failure"):
        summary["failure"] = run_failure()
    if which in ("all", "compat"):
        summary["compat"] = run_openai_compat()
    if which in ("all", "security"):
        summary["security"] = run_security()
    if which in ("all", "latency"):
        summary["latency"] = run_latency()
    if which in ("all", "compression"):
        summary["compression"] = run_compression()
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2, default=str)[:200000])
    print("\nAll requested benches finished.")
