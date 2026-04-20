"""
retriage.py — Incremental re-triage after AUTO fix.

After AUTO mode writes fixes, re-scan only the changed files using
chain_walker and semgrep. Returns delta findings not present in the original report.

CLI usage:
    python3 retriage.py <workspace_path> <fixed_files_json> <issue_description>

    fixed_files_json: JSON array of absolute or relative paths written by the fix run.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Dict, List, Optional, Set

ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ENGINE_DIR)

import chain_walker as cw
import rkt_engine
from context_filter import filter_findings
from dedup import deduplicate

GREEN = "\033[0;32m"
YELLOW = "\033[0;33m"
BOLD = "\033[1m"
CYAN = "\033[0;36m"
NC = "\033[0m"


def _fingerprint_set(findings: List[Dict[str, Any]]) -> Set[str]:
    """Build a set of (source:path:rule_tail) keys for dedup against original report."""
    result = set()
    for entry in findings:
        src = entry.get("source", "")
        f = entry.get("finding", {})
        path = f.get("path") or f.get("broken_at") or f.get("file") or ""
        rule_tail = (f.get("chain") or f.get("check_id") or "").split(".")[-1].lower()
        result.add(f"{src}:{path}:{rule_tail}")
    return result


def run(
    workspace_path: str,
    fixed_files: List[str],
    issue_description: str,
    original_findings: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Re-scan only the changed files and return delta findings.

    Returns:
        {
            "delta_findings": list,
            "files_scanned": int,
            "scan_time_ms": float,
        }
    """
    t0 = time.perf_counter()
    workspace_path = os.path.abspath(os.path.expanduser(workspace_path))

    # Normalise to relative paths for comparison against finding paths
    rel_files: List[str] = []
    for p in fixed_files:
        try:
            rel = os.path.relpath(p, workspace_path)
        except ValueError:
            rel = p
        rel_files.append(rel)

    changed_set = set(rel_files)

    # Re-run chain_walker, filter to changed files only
    cw_entries: List[Dict[str, Any]] = []
    for f in cw.walk(workspace_path):
        if f.get("broken_at") in changed_set:
            cw_entries.append({
                "source": "chain_walker",
                "finding": f,
                "fix_mode": "GUIDED",
                "confidence": 0.75,
            })

    # Re-run semgrep scoped to changed files
    semgrep_entries: List[Dict[str, Any]] = []
    if rel_files:
        sg = rkt_engine.run_semgrep(workspace_path, autofix=False)
        for f in sg.get("findings", []):
            if f.get("path") in changed_set:
                semgrep_entries.append({
                    "source": "semgrep",
                    "finding": f,
                    "fix_mode": "GUIDED",
                    "confidence": 0.75,
                })

    all_new = cw_entries + semgrep_entries

    # Filter suppressed findings, then dedup cross-layer
    filtered = filter_findings(all_new, workspace_path)
    deduped = deduplicate(filtered["active"])

    # Remove findings that were already in the original report
    original_fp = _fingerprint_set(original_findings or [])
    if original_fp:
        delta = [e for e in deduped if not (_fingerprint_set([e]) & original_fp)]
    else:
        delta = deduped

    elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
    return {
        "delta_findings": delta,
        "files_scanned": len(rel_files),
        "scan_time_ms": elapsed_ms,
    }


def format_delta(result: Dict[str, Any]) -> str:
    delta = result["delta_findings"]
    files = result["files_scanned"]
    ms = result["scan_time_ms"]

    lines = [f"\n{BOLD}{CYAN}── RE-TRIAGE (changed files only) ──{NC}"]
    lines.append(f"  {GREEN}✓{NC}  {files} file(s) re-scanned in {ms:.0f}ms")

    if not delta:
        lines.append(f"  {GREEN}✓{NC}  Re-triage clean — no secondary issues found")
    else:
        lines.append(f"  {YELLOW}!{NC}  {len(delta)} secondary issue(s) found:")
        for entry in delta:
            src = entry.get("source", "")
            f = entry.get("finding", {})
            mode = entry.get("fix_mode", "?")
            conf = entry.get("confidence", 0.0)
            evidence = entry.get("evidence", [src])
            ev_str = "+".join(evidence)

            if src == "chain_walker":
                msg = f.get("issue", "")
                path = f.get("broken_at", "")
                lines.append(f"     [{ev_str}] [{mode}:{conf:.0%}] {path} — {msg}")
            else:
                rule = (f.get("check_id") or "").split(".")[-1]
                path = f.get("path", "")
                line = f.get("start", {}).get("line", "?")
                lines.append(f"     [{ev_str}] [{mode}:{conf:.0%}] {rule} @ {path}:{line}")

        lines.append(f"     → Run {CYAN}rkt-triage{NC} again to fix remaining issues")

    return "\n".join(lines)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: retriage.py <workspace> <fixed_files_json> <issue_description>")
        sys.exit(1)
    ws = sys.argv[1]
    files = json.loads(sys.argv[2])
    issue = sys.argv[3]
    result = run(ws, files, issue)
    print(format_delta(result))
