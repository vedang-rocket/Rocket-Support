"""
claude_code_agent.py — Replace raw Claude API with Claude Code CLI.

Claude Code CLI runs with:
- Full cursor rules from cursor-rules-v34/ (AGENTS.md, contexts, docs)
- Real file system access to repo_path
- Can read complete files not just 7 lines
- Runs tsc --noEmit itself for validation
- Has all Rocket.new conventions built in

Usage: called from claude_agent.py instead of _claude_api_fix()
"""
import json
import os
import subprocess
import time
from typing import Any, Dict, List, Optional

CLAUDE_CLI = os.path.expanduser("~/.local/bin/claude")
RULES_DIR = os.path.expanduser("~/rocket-support/cursor-rules-v34")


def _build_fix_prompt(
    findings: list,
    repo_path: str,
    db_match: Optional[dict],
    hint: str,
) -> str:
    primary = findings[0] if findings else {}

    broken_file = (
        primary.get("broken_at")
        or primary.get("file_path", "")
        or ""
    )
    if broken_file and not os.path.isabs(broken_file):
        broken_file = os.path.join(repo_path, broken_file)

    rel_file = os.path.relpath(broken_file, repo_path) if broken_file else "unknown"
    issue = primary.get("issue") or primary.get("message") or "unknown issue"
    line = primary.get("line_number") or 1

    db_context = ""
    if db_match and db_match.get("pattern"):
        db_context = f"\nKnown pattern: {db_match['pattern']}"
        if db_match.get("fix_diff"):
            db_context += f"\nSimilar fix applied before:\n{db_match['fix_diff'][:200]}"

    return f"""Fix this bug in {rel_file}.

TICKET: {hint or "(no hint)"}
ISSUE: {issue}
FILE: {rel_file}
LINE: {line}{db_context}

INSTRUCTIONS:
1. Read {rel_file} fully before making any change
2. Make the minimum change needed — do not refactor
3. Do not change any other files unless strictly required
4. After fixing, run: npx tsc --noEmit
5. If tsc fails, fix the TypeScript errors

Read AGENTS.md in the project root for all hard rules. This is a Rocket.new project."""


def run_claude_code_fix(
    findings: list,
    repo_path: str,
    db_match: Optional[dict],
    hint: str,
    shadow: bool = False,
    timeout: int = 120,
) -> Dict[str, Any]:
    """
    Run Claude Code CLI to fix a bug.

    Returns dict with:
      success: bool
      changes_applied: list of {file, description}
      tokens_used: int
      cost_usd: float
      error: str
      raw_output: str
    """
    if not os.path.isfile(CLAUDE_CLI):
        return {
            "success": False,
            "error": f"Claude Code CLI not found at {CLAUDE_CLI}",
            "changes_applied": [],
            "tokens_used": 0,
            "cost_usd": 0.0,
        }

    prompt = _build_fix_prompt(findings, repo_path, db_match, hint)

    if shadow:
        prompt += "\n\nSHADOW MODE: Describe what you WOULD change but do NOT edit any files."

    cmd = [
        CLAUDE_CLI,
        "--print",
        "--output-format", "json",
        "--dangerously-skip-permissions",
        "--model", "claude-sonnet-4-6",
        "--max-budget-usd", "0.05",
        "--add-dir", RULES_DIR,
        "--add-dir", repo_path,
        "--allowedTools", "Edit,Write,Read,Bash(npx tsc --noEmit),Bash(cat *),Bash(ls *)",
        "--system-prompt", (
            "You are fixing a Rocket.new support ticket. "
            "Read AGENTS.md in the added directory for all hard rules. "
            "Make surgical fixes only. "
            "Never rewrite entire files unless strictly necessary."
        ),
        prompt,
    ]

    start = time.perf_counter()

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=repo_path,
        )
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        raw = result.stdout.strip()

        if result.returncode != 0:
            return {
                "success": False,
                "error": f"Claude Code exited {result.returncode}: {result.stderr[:200]}",
                "changes_applied": [],
                "tokens_used": 0,
                "cost_usd": 0.0,
                "elapsed_ms": elapsed_ms,
            }

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {"result": raw, "type": "text"}

        tokens_input = 0
        tokens_output = 0
        cost_usd = 0.0

        if isinstance(data, dict):
            usage = data.get("usage", {})
            tokens_input = usage.get("input_tokens", 0)
            tokens_output = usage.get("output_tokens", 0)
            cost_usd = data.get("cost_usd", 0.0)

        tokens_total = tokens_input + tokens_output

        # Detect files mentioned in the result text
        changes: List[Dict[str, Any]] = []
        if isinstance(data, dict):
            result_text = data.get("result", "") or str(data)
            for finding in findings[:3]:
                broken = finding.get("broken_at") or finding.get("file_path", "")
                if broken and broken in result_text:
                    changes.append({
                        "file": broken,
                        "description": (finding.get("issue") or finding.get("message", "fix applied"))[:60],
                    })

        if not changes and isinstance(data, dict):
            result_text = data.get("result", "")
            if result_text and (
                "edited" in result_text.lower()
                or "updated" in result_text.lower()
                or "changed" in result_text.lower()
            ):
                changes.append({
                    "file": "see output",
                    "description": "Claude Code applied changes",
                })

        success = (
            result.returncode == 0
            and not (isinstance(data, dict) and data.get("is_error", False))
        )

        return {
            "success": success,
            "changes_applied": changes,
            "tokens_used": tokens_total,
            "tokens_input": tokens_input,
            "tokens_output": tokens_output,
            "cost_usd": cost_usd,
            "elapsed_ms": elapsed_ms,
            "raw_output": raw[:500],
            "result_text": (data.get("result", "")[:300] if isinstance(data, dict) else raw[:300]),
            "error": (data.get("error", "") if isinstance(data, dict) else ""),
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": f"Claude Code timed out after {timeout}s",
            "changes_applied": [],
            "tokens_used": 0,
            "cost_usd": 0.0,
        }
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc)[:200],
            "changes_applied": [],
            "tokens_used": 0,
            "cost_usd": 0.0,
        }
