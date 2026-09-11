"""OpenAI Compatibility Test using the official openai client.

Client requires NO Remember-specific API changes — only base_url + api_key.
"""
from __future__ import annotations

import json

from openai import OpenAI

client = OpenAI(
    api_key="test",
    base_url="http://localhost:8199/v1",
)

results = {}


def main():
    # 1. /v1/models
    try:
        models = client.models.list()
        results["models"] = {"ok": True, "count": len(models.data), "first": models.data[0].id}
        print("models:", results["models"]["count"], "models")
    except Exception as e:
        results["models"] = {"ok": False, "error": str(e)}
        print("models ERROR:", e)

    # 2. /v1/chat/completions (non-streaming)
    try:
        resp = client.chat.completions.create(
            model="deepseek-v4-flash-0731",
            messages=[{"role": "user", "content": "Reply with one word: ok"}],
            max_tokens=5,
        )
        results["chat_nonstream"] = {"ok": True, "content": resp.choices[0].message.content}
        print("chat_nonstream:", resp.choices[0].message.content)
    except Exception as e:
        results["chat_nonstream"] = {"ok": False, "error": str(e)}
        print("chat_nonstream ERROR:", e)

    # 3. /v1/chat/completions (streaming)
    try:
        stream = client.chat.completions.create(
            model="deepseek-v4-flash-0731",
            messages=[{"role": "user", "content": "Count 1 2 3"}],
            max_tokens=10,
            stream=True,
        )
        parts = []
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                parts.append(chunk.choices[0].delta.content)
        content = "".join(parts)
        results["chat_stream"] = {"ok": True, "content": content}
        print("chat_stream:", repr(content))
    except Exception as e:
        results["chat_stream"] = {"ok": False, "error": str(e)}
        print("chat_stream ERROR:", e)

    # 4. /v1/responses (if upstream supports; else report passthrough)
    try:
        resp = client.responses.create(
            model="deepseek-v4-flash-0731",
            input="Reply with one word: ok",
        )
        results["responses"] = {"ok": True}
        print("responses: ok")
    except Exception as e:
        results["responses"] = {"ok": False, "error": str(e)[:200]}
        print("responses ERROR:", str(e)[:200])

    with open("/tmp/opencode/openai_compat_results.json", "w") as fh:
        json.dump(results, fh, indent=2)
    print("\nSaved /tmp/opencode/openai_compat_results.json")


if __name__ == "__main__":
    main()
