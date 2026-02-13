#!/usr/bin/env python3
"""Report large Python files and enforce hard size limits."""

from __future__ import annotations

import argparse
from pathlib import Path


def iter_python_files(root: Path) -> list[Path]:
    """Return tracked Python files under source roots."""

    roots = [root / "src", root / "cli", root / "tests", root / "tools"]
    files: list[Path] = []
    for source_root in roots:
        if not source_root.exists():
            continue
        for path in source_root.rglob("*.py"):
            if ".venv" in path.parts or "site-packages" in path.parts:
                continue
            files.append(path)
    return sorted(files)


def count_lines(path: Path) -> int:
    """Return number of lines in a UTF-8 text file."""

    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for _ in handle)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--soft-limit", type=int, default=800, help="warn when a file exceeds this many lines")
    parser.add_argument("--hard-limit", type=int, default=1500, help="fail when a file exceeds this many lines")
    parser.add_argument("--top", type=int, default=20, help="number of largest files to print")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    files = iter_python_files(root)
    rows = [(count_lines(path), path) for path in files]
    rows.sort(reverse=True, key=lambda item: item[0])

    print(f"Scanned {len(rows)} Python files")
    print(f"Soft limit: {args.soft_limit} lines, hard limit: {args.hard_limit} lines")
    print()
    print("Largest files:")
    for line_count, path in rows[: args.top]:
        marker = "!"
        if line_count <= args.soft_limit:
            marker = " "
        if line_count > args.hard_limit:
            marker = "X"
        rel = path.relative_to(root)
        print(f"{marker} {line_count:4d}  {rel}")

    hard_violations = [(line_count, path) for line_count, path in rows if line_count > args.hard_limit]
    if hard_violations:
        print("\nHard-limit violations:")
        for line_count, path in hard_violations:
            print(f"- {path.relative_to(root)} ({line_count} lines)")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
