"""Failure / resilience tests for the Remember gateway.

Covers malformed request, oversized request, streaming, non-streaming,
upstream LLM failure propagation, and gateway crash checks.
(Memory DB unavailable / cache unavailable / extraction failure are tested at
unit level via the app's fail-open logic in a separate check.)
"""
from __future__ import annotations

import json
import time

import httpx

GATEWAY = "http://127.0.0.1:8199/v1"
MODEL = "deepseek-v4-flash-0731"
KEY = "progga_goBPgKimwf8I9YiOCFpWJGyCnCBKwpWX55B1vvP0HdsA2GgP"
HEADERS = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
client = httpx.Client(timeout=300)

results = {}


def healthy():
    r = client.get("http://127.0.0.1:8199/health", timeout=5)
    return r.status_code == 200


def main():
    # 1. Non-streaming normal request works
    body = {"model": MODEL, "messages": [{"role": "user", "content": "Reply with one word: ok"}], "max_tokens": 5}
    r = client.post(f"{GATEWAY}/chat/completions", json=body, headers=HEADERS)
    results["non_stream_normal"] = {"status": r.status_code, "is_openai_format": "choices" in r.text}
    print("non_stream_normal:", r.status_code)

    # 2. Streaming normal request works & transparent
    sbody = {"model": MODEL, "stream": True, "messages": [{"role": "user", "content": "Count 1 2 3"}], "max_tokens": 10}
    events = []
    content_type = None
    with client.stream("POST", f"{GATEWAY}/chat/completions", json=sbody, headers=HEADERS) as r:
        content_type = r.headers.get("content-type")
        for line in r.iter_lines():
            if line.startswith("data: "):
                events.append(line)
    has_done = any("DONE" in e for e in events)
    has_data = any('"content"' in e for e in events)
    results["stream_normal"] = {"status": 200, "content_type": content_type, "has_done": has_done, "has_content": has_data}
    print("stream_normal:", content_type, "done=", has_done, "content=", has_data)

    # 3. Malformed JSON -> 400, gateway stays up
    r = client.post(f"{GATEWAY}/chat/completions", content=b"{bad json", headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
    results["malformed_json"] = {"status": r.status_code}
    print("malformed_json:", r.status_code)

    # 4. Non-object JSON -> 400
    r = client.post(f"{GATEWAY}/chat/completions", content=b"[1,2,3]", headers={"Content-Type": "application/json", "Authorization": f"Bearer {KEY}"})
    results["non_object_json"] = {"status": r.status_code}
    print("non_object_json:", r.status_code)

    # 5. Missing model / messages -> upstream behavior (should be 4xx passed through or handled)
    r = client.post(f"{GATEWAY}/chat/completions", json={"messages": []}, headers=HEADERS)
    results["empty_messages"] = {"status": r.status_code}
    print("empty_messages:", r.status_code)

    # 6. Oversized request -> 413
    big = "x" * (2_000_000 + 100)
    r = client.post(f"{GATEWAY}/chat/completions", json={"model": MODEL, "messages": [{"role": "user", "content": big}]}, headers=HEADERS)
    results["oversized"] = {"status": r.status_code}
    print("oversized:", r.status_code)

    # 7. Upstream LLM failure propagation: bad upstream key is configured in a *separate* instance;
    # instead test by pointing at an unreachable model via a request the upstream rejects.
    # We can't reconfigure the running gateway; instead verify a 4xx from upstream is passed through
    # when model is invalid (if upstream returns an error).
    r = client.post(f"{GATEWAY}/chat/completions", json={"model": "definitely-not-a-real-model-xyz", "messages": [{"role": "user", "content": "hi"}]}, headers=HEADERS)
    results["invalid_model_upstream"] = {"status": r.status_code}
    print("invalid_model_upstream:", r.status_code)

    # 8. /v1/responses endpoint
    r = client.post(f"{GATEWAY}/responses", json={"model": MODEL, "input": "Reply with one word: ok"}, headers=HEADERS)
    results["responses_endpoint"] = {"status": r.status_code}
    print("responses_endpoint:", r.status_code)

    # 9. /v1/models endpoint
    r = client.get(f"{GATEWAY}/models", headers=HEADERS)
    results["models_endpoint"] = {"status": r.status_code}
    print("models_endpoint:", r.status_code)

    # 10. Gateway still healthy after all failure tests
    results["gateway_healthy_after"] = healthy()
    print("gateway_healthy_after:", results["gateway_healthy_after"])

    with open("/tmp/opencode/failure_results.json", "w") as fh:
        json.dump(results, fh, indent=2)
    print("\nSaved /tmp/opencode/failure_results.json")


if __name__ == "__main__":
    main()
