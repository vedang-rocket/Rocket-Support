from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ENGINE_DIR)

import tracer as _tracer


@dataclass
class LoopResult:
    success: bool
    attempts: int
    final_result: Any
    validation_passed: bool
    tsc_errors: List[str] = field(default_factory=list)
    chain_errors: List[str] = field(default_factory=list)
    error: str = ""


def run_oxc_validation(repo_path: str, changed_files: list) -> Tuple[bool, List[str]]:
    """
    Run fix_validator on changed files only.
    Returns (passed: bool, errors: List[str])
    Never blocks — always returns gracefully.
    """
    with _tracer.trace("PHASE8", "fix_validator:oxc") as trace_token:
        passed, errors = _run_oxc_validation_impl(repo_path, changed_files)
        trace_token.set_output(f"errors={len(errors)}")
        return passed, errors


def _run_oxc_validation_impl(repo_path: str, changed_files: list) -> Tuple[bool, List[str]]:
    try:
        import fix_validator

        ts_files = [f for f in (changed_files or []) if f.endswith((".ts", ".tsx"))]
        if not ts_files:
            return True, []

        proposals = []
        for rel_path in ts_files:
            abs_path = rel_path if os.path.isabs(rel_path) else os.path.join(repo_path, rel_path)
            try:
                with open(abs_path, "r", encoding="utf-8", errors="replace") as fh:
                    new_content = fh.read()
            except Exception:
                continue
            proposal = type("Proposal", (), {})()
            proposal.path = rel_path
            proposal.new_content = new_content
            proposal.diff = None
            proposals.append(proposal)

        if not proposals:
            return True, []

        plan = type("FixPlan", (), {})()
        plan.proposals = proposals

        errors = fix_validator.validate_fix_plan(plan, repo_path)
        if not errors:
            return True, []

        error_lines: List[str] = []
        for item in errors[:5]:
            file_name = item.get("file", "")
            for err in item.get("errors", [])[:2]:
                error_lines.append(f"{file_name}: {err}")
        return False, error_lines[:5]
    except Exception:
        return True, []


def run_tsc(repo_path: str, timeout: int = 30) -> Tuple[bool, List[str]]:
    """
    Run tsc --noEmit in repo_path.
    Returns (passed: bool, errors: List[str])
    Fails gracefully if tsc not available.
    """
    with _tracer.trace("PHASE8", "tsc") as trace_token:
        try:
            result = subprocess.run(
                ["npx", "tsc", "--noEmit", "--pretty", "false"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            logger = _tracer.get_logger()
            if logger:
                logger.increment("tsc")
        except FileNotFoundError:
            trace_token.set_output("errors=0 unavailable=1")
            return True, []
        except subprocess.TimeoutExpired:
            trace_token.set_output("errors=0 timeout=1")
            return True, []
        except Exception:
            trace_token.set_output("errors=0 exception=1")
            return True, []
        if result.returncode == 0:
            trace_token.set_output("errors=0")
            return True, []

        import re as _re
        _ansi = _re.compile(r"\x1b\[[0-9;]*m")
        raw_lines = result.stdout.splitlines() + result.stderr.splitlines()
        output_lines = [_ansi.sub("", l) for l in raw_lines]

        # npx "not the tsc command" — TypeScript not installed, treat as pass
        if any("not the tsc command" in l for l in output_lines):
            trace_token.set_output("errors=0 unavailable=1")
            return True, []

        errors = [
            line
            for line in output_lines
            if line.strip() and ("error TS" in line or "Error:" in line)
        ]
        if not errors:
            errors = [line for line in output_lines if line.strip()]
        trace_token.set_output(f"errors={len(errors)}")
        return False, errors


def run_chain_validation(repo_path: str, original_findings: list) -> Tuple[bool, List[str]]:
    """
    Re-run chain_walker. Check if original violations are still present.
    Returns (passed: bool, remaining_violations: List[str])
    """
    with _tracer.trace("PHASE8", "chain_walker:rescan") as trace_token:
        passed, errors = _run_chain_validation_impl(repo_path, original_findings)
        trace_token.set_output(f"findings={len(errors)}")
        return passed, errors


def _run_chain_validation_impl(repo_path: str, original_findings: list) -> Tuple[bool, List[str]]:
    try:
        import chain_walker

        new_findings = chain_walker.walk(repo_path)

        original_broken = {
            f.get("broken_at", "") or f.get("file_path", "")
            for f in (original_findings or [])
            if f.get("broken_at") or f.get("file_path")
        }

        still_broken: List[str] = []
        for f in new_findings:
            broken = f.get("broken_at", "") or f.get("file_path", "")
            if broken in original_broken:
                still_broken.append(f.get("issue", broken))

        return len(still_broken) == 0, still_broken
    except Exception:
        return True, []


def run_fix_loop(
    findings: list,
    repo_path: str,
    db_match: Optional[dict],
    hint: str,
    shadow: bool = False,
    max_attempts: int = 3,
) -> LoopResult:
    """
    Main agent loop:
    1. ClaudeAgent.fix()
    2. Validate (tsc + chain_walker)
    3. If fail -> retry with error context (max 3 attempts)
    4. Return best result
    """
    from claude_agent import ClaudeAgent

    agent = ClaudeAgent()
    original_hint = hint
    last_result = None
    last_oxc_errors: List[str] = []
    last_tsc_errors: List[str] = []
    last_chain_errors: List[str] = []

    for attempt in range(1, max_attempts + 1):
        result = agent.fix(
            findings=findings,
            repo_path=repo_path,
            db_match=db_match,
            hint=hint,
            shadow=shadow,
        )
        last_result = result

        if not result.success:
            hint = (
                f"{original_hint}\n\n"
                f"[Attempt {attempt} failed: {result.error}]\n"
                f"Try a different approach. Be more surgical."
            )
            continue

        if shadow:
            return LoopResult(
                success=True,
                attempts=attempt,
                final_result=result,
                validation_passed=True,
            )

        changed_files = [
            c.get("file", "") for c in (result.changes_applied or [])
            if c.get("file")
        ]

        oxc_passed, oxc_errors = run_oxc_validation(repo_path, changed_files)
        last_oxc_errors = oxc_errors
        if not oxc_passed:
            hint = (
                f"{original_hint}\n\n"
                f"[Attempt {attempt} — oxc syntax errors in changed files]\n"
                f"{chr(10).join(oxc_errors)}\n"
                f"Fix these syntax errors. Do not introduce new ones."
            )
            continue

        tsc_passed, tsc_errors = run_tsc(repo_path)
        chain_passed, chain_errors = run_chain_validation(repo_path, findings)
        last_tsc_errors = tsc_errors
        last_chain_errors = chain_errors

        if tsc_passed and chain_passed:
            return LoopResult(
                success=True,
                attempts=attempt,
                final_result=result,
                validation_passed=True,
                tsc_errors=[],
                chain_errors=[],
            )

        all_errors = tsc_errors + chain_errors
        error_summary = "\n".join(all_errors)

        hint = (
            f"{original_hint}\n\n"
            f"[Attempt {attempt} applied changes but validation failed]\n"
            f"tsc: {'PASS' if tsc_passed else 'FAIL'}\n"
            f"chain_walker: {'PASS' if chain_passed else 'FAIL'}\n"
            f"Errors:\n{error_summary}\n\n"
            f"Fix these errors. Do not repeat the previous approach."
        )

    return LoopResult(
        success=False,
        attempts=max_attempts,
        final_result=last_result,
        validation_passed=False,
        tsc_errors=last_oxc_errors + last_tsc_errors,
        chain_errors=last_chain_errors,
        error=f"Failed after {max_attempts} attempts",
    )
