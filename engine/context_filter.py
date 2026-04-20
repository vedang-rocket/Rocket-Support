"""
context_filter.py — Suppress false-positive findings before scoring.

For each finding, reads ±15 lines around the violation and checks for:
  - // @rkt-ignore on or above the violation line
  - // intentional / // expected / // override in the same block
  - process.env.NODE_ENV test guard wrapping the violation
  - Test file path (/__tests__/, /test/, .test.ts, .spec.ts, etc.)

Input findings shape: [{"source": str, "finding": dict, "fix_mode": str, "confidence": float}]
Output: {"active": [...], "suppressed": [...]}
Each suppressed entry gains a "suppression_reason" key.
"""

import os
import re
from typing import Any, Dict, List, Tuple

_SUPPRESS_COMMENT_RE = re.compile(
    r"//\s*(@rkt-ignore|intentional|expected|override)\b", re.IGNORECASE
)
_TEST_ENV_RE = re.compile(
    r"""process\.env\.NODE_ENV\s*[!=]==?\s*['"]test['"]""", re.IGNORECASE
)
_TEST_PATH_PATTERNS = (
    "/__tests__/", "/test/", ".test.ts", ".spec.ts",
    ".test.tsx", ".spec.tsx", ".test.js", ".spec.js",
)

CONTEXT_WINDOW = 15


def _read_lines(path: str) -> List[str]:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.readlines()
    except OSError:
        return []


def _is_test_file(file_path: str) -> Tuple[bool, str]:
    for pattern in _TEST_PATH_PATTERNS:
        if pattern in file_path:
            return True, f"test file ({pattern})"
    return False, ""


def _get_context(lines: List[str], line_number: int) -> List[str]:
    idx = max(0, line_number - 1)
    start = max(0, idx - CONTEXT_WINDOW)
    end = min(len(lines), idx + CONTEXT_WINDOW + 1)
    return [l.rstrip("\n") for l in lines[start:end]]


def _check_suppression(context: List[str]) -> Tuple[bool, str]:
    for line in context:
        m = _SUPPRESS_COMMENT_RE.search(line)
        if m:
            return True, m.group(0).strip()
        if _TEST_ENV_RE.search(line):
            return True, "NODE_ENV test guard"
    return False, ""


def _get_file_and_line(finding: Dict[str, Any], source: str) -> Tuple[str, int]:
    if source == "semgrep":
        return finding.get("path", ""), finding.get("start", {}).get("line", 0)
    if source == "chain_walker":
        return finding.get("broken_at", ""), 0
    return finding.get("file", ""), finding.get("line", 0)


_CATEGORY_FILE_HINTS: Dict[str, List[str]] = {
    "AUTH":     ["middleware.ts", "lib/supabase/server.ts", "lib/supabase/middleware.ts"],
    "STRIPE":   ["app/api/webhooks/stripe/route.ts", "lib/stripe.ts"],
    "SUPABASE": ["lib/supabase/server.ts", "lib/supabase/client.ts"],
    "ENV":      [".env.local", ".env"],
    "BUILD":    ["next.config.ts", "next.config.js", "tsconfig.json"],
}


def top_suspicious_files(
    repo_path: str,
    chain_findings: List[Dict[str, Any]],
    fp_result: Dict[str, Any],
    max_files: int = 5,
) -> List[str]:
    """
    Return the N absolute file paths most likely to contain violations,
    based on chain_walker results and fingerprint category. Used as a
    pre-filter in --quick mode to avoid reading irrelevant files.
    """
    seen: "dict[str, int]" = {}

    # Highest priority: files chain_walker flagged
    for f in chain_findings:
        fp = f.get("file_path", "")
        if fp and os.path.isfile(fp):
            seen[fp] = seen.get(fp, 0) + 10

    # Secondary: known files for the detected category
    category = (fp_result or {}).get("category", "AUTH")
    for rel in _CATEGORY_FILE_HINTS.get(category, []):
        abs_p = os.path.join(repo_path, rel)
        if os.path.isfile(abs_p) and abs_p not in seen:
            seen[abs_p] = 1

    ranked = sorted(seen, key=lambda k: seen[k], reverse=True)
    return ranked[:max_files]


def filter_findings(
    findings: List[Dict[str, Any]],
    workspace_path: str,
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Split findings into active and suppressed.

    Returns {"active": [...], "suppressed": [...]}
    """
    active = []
    suppressed = []

    for entry in findings:
        source = entry.get("source", "")
        f = entry.get("finding", {})
        file_path, line_number = _get_file_and_line(f, source)

        # Test file path check (no disk read needed)
        is_test, reason = _is_test_file(file_path)
        if is_test:
            suppressed.append({**entry, "suppression_reason": reason})
            continue

        # Context check requires file content + a known line number
        if file_path and line_number > 0:
            abs_path = (
                os.path.join(workspace_path, file_path)
                if not os.path.isabs(file_path)
                else file_path
            )
            lines = _read_lines(abs_path)
            if lines:
                context = _get_context(lines, line_number)
                suppressed_flag, reason = _check_suppression(context)
                if suppressed_flag:
                    suppressed.append({**entry, "suppression_reason": reason})
                    continue

        active.append(entry)

    return {"active": active, "suppressed": suppressed}
