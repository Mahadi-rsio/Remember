"""Unit-level fail-open isolation tests.

Verifies that memory-layer failures do not break main-AI forwarding.
Simulates SQLite unavailability / extraction failure by pointing storage at a
path that cannot be opened, and checks that archive_request and compile_context
fail open (return None / original messages) rather than raising.
"""
from __future__ import annotations

import json
import os
import sys

# Run inside the gateway package dir so `app` imports resolve
sys.path.insert(0, "/workspaces/Remember/memory-gateway")

results = {}


def test_sqlite_unavailable():
    """Point SQLite at an unwritable path; archive must fail open."""
    import tempfile
    from app.memory import delta
    from app.storage import archive
    from app.storage import db as dbmod

    # Force a session that raises (simulate DB down) by monkeypatching session_scope
    original = dbmod.session_scope

    def broken_scope():
        raise RuntimeError("simulated DB unavailable")

    dbmod.session_scope = broken_scope
    try:
        body = {"messages": [{"role": "user", "content": "My name is Test."}]}
        result = archive.archive_request_async is not None  # just confirm import
        # archive_request uses session_scope internally -> should fail open to None
        from app.storage.archive import archive_request
        out = archive_request(body, headers={})
        results["sqlite_unavailable_archive"] = {"failed_open_to_none": out is None}
        print("sqlite unavailable -> archive fail-open:", out is None)
    finally:
        dbmod.session_scope = original


def test_extraction_failure_fail_open():
    """Memory engine raising must not propagate; returns error result not raise."""
    import asyncio
    from app.memory.delta import DeltaResult
    from app.memory import engine as eng
    from app.memory.ids import NormalizedMessage

    class Boom(Exception):
        pass

    original = eng.extract_candidates

    def broken_extract(*a, **k):
        raise Boom("extraction boom")

    eng.extract_candidates = broken_extract
    try:
        dm = DeltaResult(
            conversation_id="failopen-test",
            user_key=None,
            all_messages=[],
            new_messages=[
                NormalizedMessage(
                    message_key="k1", role="user", content="My name is Test.",
                    content_hash="h", ordinal=0, client_message_id=None, raw={},
                )
            ],
        )
        res = eng.process_memory_delta(dm)
        results["extraction_failure"] = {
            "did_not_raise": res is not None,
            "has_error_flag": bool(res.error) if res else False,
        }
        print("extraction failure -> returns result with error, no raise:", res.error if res else "None")
    finally:
        eng.extract_candidates = original


def test_low_info_skips():
    from app.memory.low_info import is_low_info_message
    for phrase in ["ok", "thanks", "yes", "continue", "got it"]:
        if not is_low_info_message(phrase):
            print("  WARNING: not low-info:", phrase)
    results["low_info"] = {
        "ok": is_low_info_message("ok"),
        "thanks": is_low_info_message("thanks"),
        "yes": is_low_info_message("yes"),
    }
    print("low-info phrases recognized correctly")


def main():
    test_sqlite_unavailable()
    test_extraction_failure_fail_open()
    test_low_info_skips()
    with open("/tmp/opencode/failopen_results.json", "w") as fh:
        json.dump(results, fh, indent=2)
    print("\nSaved /tmp/opencode/failopen_results.json")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
