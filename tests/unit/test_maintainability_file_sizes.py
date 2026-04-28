from __future__ import annotations

from pathlib import Path

MAX_PYTHON_FILE_LINES = 1000
MAX_SOURCE_FILE_LINES = 700


def _iter_python_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for source_root in (root / "src", root / "cli", root / "tools"):
        if not source_root.exists():
            continue
        for path in source_root.rglob("*.py"):
            if ".venv" in path.parts or "site-packages" in path.parts:
                continue
            files.append(path)
    return sorted(files)


def _count_lines(path: Path) -> int:
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for _ in handle)


def test_python_files_stay_under_hard_size_limit() -> None:
    root = Path(__file__).resolve().parents[2]
    offenders: list[tuple[Path, int]] = []
    for path in _iter_python_files(root):
        line_count = _count_lines(path)
        if line_count > MAX_PYTHON_FILE_LINES:
            offenders.append((path, line_count))

    assert not offenders, (
        "Large Python files exceed hard maintainability limit "
        f"({MAX_PYTHON_FILE_LINES} lines): "
        + ", ".join(f"{path.relative_to(root)} ({count})" for path, count in offenders)
    )


def test_svg2ooxml_source_files_stay_under_soft_size_limit() -> None:
    root = Path(__file__).resolve().parents[2]
    source_root = root / "src" / "svg2ooxml"
    offenders: list[tuple[Path, int]] = []
    for path in sorted(source_root.rglob("*.py")):
        line_count = _count_lines(path)
        if line_count > MAX_SOURCE_FILE_LINES:
            offenders.append((path, line_count))

    assert not offenders, (
        "svg2ooxml source files exceed soft maintainability limit "
        f"({MAX_SOURCE_FILE_LINES} lines): "
        + ", ".join(f"{path.relative_to(root)} ({count})" for path, count in offenders)
    )
