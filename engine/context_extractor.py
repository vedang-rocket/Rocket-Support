"""
context_extractor.py — Extract a line-window from a source file.

Used by rkt_engine to show code context around detected issues
instead of sending full files to Claude (60-70% token reduction).
"""
import os
from typing import Dict, Optional


def extract_context(file_path: str, line_number: int, window: int = 15) -> Dict:
    """Return a window*2 line window centred on line_number.

    Args:
        file_path:   Absolute (or expandable) path to the file.
        line_number: 1-indexed target line.
        window:      Lines before AND after (default 15 → 30-line window).

    Returns:
        {file, full_path, start_line, end_line, content}
        or {} on any error (missing file, binary, empty, etc.)
    """
    file_path = os.path.expanduser(file_path)
    if not file_path or not os.path.isfile(file_path):
        return {}

    try:
        with open(file_path, "r", errors="replace") as fh:
            lines = fh.readlines()
    except (IOError, OSError):
        return {}

    total = len(lines)
    if total == 0:
        return {}

    # Clamp to valid range
    line_number = max(1, min(line_number, total))
    start = max(0, line_number - 1 - window)
    end   = min(total, line_number + window)

    return {
        "file":       os.path.basename(file_path),
        "full_path":  file_path,
        "start_line": start + 1,
        "end_line":   end,
        "content":    "".join(lines[start:end]),
    }


def find_anchor_line(file_path: str, search_str: str) -> int:
    """Find the first line in file_path containing search_str.

    Returns the 1-indexed line number, or 1 if not found / file unreadable.
    Used to anchor a chain_walker context window when no explicit line is given.
    """
    file_path = os.path.expanduser(file_path)
    if not os.path.isfile(file_path):
        return 1
    try:
        with open(file_path, "r", errors="replace") as fh:
            for i, line in enumerate(fh, start=1):
                if search_str in line:
                    return i
    except (IOError, OSError):
        pass
    return 1


def format_context_block(ctx: Dict, label: str = "") -> str:
    """Format a context dict as a readable indented block for terminal output.

    Returns empty string if ctx is empty.
    """
    if not ctx:
        return ""
    header = f"  ┌─ {ctx['file']} (lines {ctx['start_line']}–{ctx['end_line']})"
    if label:
        header += f"  [{label}]"
    numbered_lines = []
    for i, line in enumerate(ctx["content"].splitlines(), start=ctx["start_line"]):
        numbered_lines.append(f"  │ {i:4d}  {line}")
    return "\n".join([header] + numbered_lines + ["  └─"])
