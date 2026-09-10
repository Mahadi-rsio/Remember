#!/usr/bin/env python3
"""Summarize checkbox progress in todo.md (and optional other docs)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]  # repo root from .cursor/skills/memory-gateway/scripts/
DEFAULT = ROOT / "todo.md"

PHASE_RE = re.compile(r"^## (.+)$")
CHECK_RE = re.compile(r"^- \[([ xX])\] (.+)$")


def summarize(path: Path) -> int:
    if not path.is_file():
        print(f"Not found: {path}", file=sys.stderr)
        return 1

    phase = "Preamble"
    stats: dict[str, list[tuple[bool, str]]] = {}

    for line in path.read_text(encoding="utf-8").splitlines():
        m = PHASE_RE.match(line)
        if m:
            phase = m.group(1).strip()
            stats.setdefault(phase, [])
            continue
        c = CHECK_RE.match(line)
        if c:
            done = c.group(1).lower() == "x"
            stats.setdefault(phase, []).append((done, c.group(2).strip()))

    total_done = total = 0
    current = None
    print(f"# Progress — {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}\n")

    skip_progress = ("non-goal", "do not")

    for name, items in stats.items():
        if not items:
            continue
        lower = name.lower()
        # Non-goals are reminders, not work to complete
        if any(s in lower for s in skip_progress):
            print(f"## {name}")
            print(f"(skipped — {len(items)} reminders, not counted)\n")
            continue
        done = sum(1 for d, _ in items if d)
        n = len(items)
        total_done += done
        total += n
        mark = "DONE" if done == n else "TODO"
        if done < n and current is None:
            current = name
            mark = "CURRENT"
        print(f"## {name}")
        print(f"{done}/{n} — {mark}")
        remaining = [t for d, t in items if not d]
        if remaining and name == current:
            print("Next:")
            for t in remaining[:5]:
                print(f"  - {t}")
            if len(remaining) > 5:
                print(f"  - … +{len(remaining) - 5} more")
        print()

    pct = (100 * total_done // total) if total else 0
    print(f"Overall: {total_done}/{total} ({pct}%)")
    if current:
        print(f"Recommended focus: {current}")
    return 0


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT
    if not path.is_absolute():
        path = ROOT / path
    return summarize(path)


if __name__ == "__main__":
    raise SystemExit(main())
