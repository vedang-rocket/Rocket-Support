"""
claude_agent.py — Three-path fix agent for rkt-diagnose.

PATH A — brain.db has a verified unified diff for this pattern:
    Apply it directly with string matching. Zero tokens, <1ms.

PATH B — Claude Code CLI (primary AI path):
    Full cursor rules, real file access, runs tsc --noEmit itself.
    Capped at $0.05/ticket. Falls through on failure.

PATH C — Raw Claude API (fallback):
    7-line slicer context, returns JSON changes applied by engine.

All paths write atomically and fall through gracefully on failure.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ENGINE_DIR)

import tracer as _tracer
from finding_resolver import resolve

_CLAUDE_MODEL = "claude-sonnet-4-6"


def _load_dotenv(env_path: str = os.path.join(ENGINE_DIR, ".env")) -> None:
    """
    Load KEY=VALUE lines from engine/.env into os.environ.
    Does not override existing env vars. Silent on missing/malformed file.
    Supports `#` comments and optional surrounding quotes on values.
    """
    if not os.path.isfile(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key   = key.strip()
                value = value.strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                    value = value[1:-1]
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        pass


_load_dotenv()


@dataclass
class AgentResult:
    success: bool
    changes_applied: List[Dict[str, Any]] = field(default_factory=list)
    root_cause: str = ""
    confidence: str = "LOW"
    tokens_used: int = 0
    error: str = ""
    path_used: str = ""   # "brain_db_diff" | "claude_api" | "none"


class ClaudeAgent:

    # ── Public entry point ────────────────────────────────────────────────────

    def fix(
        self,
        findings: list,
        repo_path: str,
        db_match: Optional[dict],
        hint: str = "",
        shadow: bool = False,
    ) -> AgentResult:
        """
        findings: normalized list — shape {rule_id, file_path, line_number, message}
                  OR raw chain_walker shape {chain, broken_at, missing, issue}
        """
        if not findings and not db_match:
            return AgentResult(success=False, error="no findings", path_used="none")
        if not findings and db_match:
            findings = [{
                "rule_id": f"db-{str(db_match.get('category', 'other')).lower()}",
                "file_path": os.path.join(repo_path, "package.json"),
                "line_number": 1,
                "message": db_match.get("pattern", "detected via brain.db pattern match"),
            }]

        # PATH A — verified diff in brain.db
        if db_match and db_match.get("fix_diff") and self._is_real_diff(db_match["fix_diff"]):
            if self._diff_is_applicable(db_match["fix_diff"], repo_path):
                result = self._apply_known_diff(db_match, repo_path, shadow=shadow)
                if result.success or shadow:
                    return result
                # fall through to PATH B

        # PATH B — Claude Code CLI (full cursor rules, real file access, runs tsc itself)
        _cc_error = ""
        try:
            from claude_code_agent import run_claude_code_fix
            cc = run_claude_code_fix(
                findings=findings,
                repo_path=repo_path,
                db_match=db_match,
                hint=hint,
                shadow=shadow,
                timeout=120,
            )
            if cc["success"]:
                return AgentResult(
                    success=True,
                    changes_applied=cc["changes_applied"],
                    root_cause=findings[0].get("issue") or findings[0].get("message", "") if findings else "",
                    confidence="HIGH",
                    tokens_used=cc["tokens_used"],
                    error="",
                    path_used="claude_code_cli",
                )
            _cc_error = cc.get("error", "") or "success=False"
        except Exception as _e:
            _cc_error = f"exception: {str(_e)[:80]}"

        # Log PATH B failure to trace log so it appears in rkt-trace / rkt-replay output
        _trace_log = os.environ.get("RKT_TRACE_LOG", "")
        if _trace_log and _cc_error:
            try:
                with open(_trace_log, "a") as _f:
                    _f.write(f"PATH_B claude_code_cli failed: {_cc_error}\n")
            except Exception:
                pass

        # PATH C — Raw Claude API (fallback)
        return self._claude_api_fix(findings, repo_path, db_match, hint, shadow=shadow)

    # ── PATH A helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _is_real_diff(fix_diff: str) -> bool:
        return fix_diff.strip().startswith("---")

    def _parse_diff(self, fix_diff: str):
        """
        Parse simplified unified diff (no @@ markers required).
        Returns (rel_file, old_block, new_block) as stripped strings.
        """
        rel_file = ""
        old_lines: List[str] = []
        new_lines: List[str] = []

        for line in fix_diff.splitlines():
            if line.startswith("--- a/"):
                rel_file = line[6:].strip()
            elif line.startswith("+++ b/") and not rel_file:
                rel_file = line[6:].strip()
            elif line.startswith("-") and not line.startswith("---"):
                old_lines.append(line[1:])
            elif line.startswith("+") and not line.startswith("+++"):
                new_lines.append(line[1:])

        return rel_file, "\n".join(old_lines), "\n".join(new_lines)

    def _resolve_file(self, rel_file: str, repo_path: str) -> Optional[str]:
        """Try root layout then src/ layout."""
        for candidate in (
            os.path.join(repo_path, rel_file),
            os.path.join(repo_path, "src", rel_file),
        ):
            if os.path.isfile(candidate):
                return candidate
        return None

    def _diff_is_applicable(self, fix_diff: str, repo_path: str) -> bool:
        rel_file, old_block, _ = self._parse_diff(fix_diff)
        if not rel_file or not old_block.strip():
            return False
        abs_path = self._resolve_file(rel_file, repo_path)
        if not abs_path:
            return False
        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read()
            return old_block.strip() in content
        except Exception:
            return False

    def _apply_known_diff(
        self,
        db_match: dict,
        repo_path: str,
        shadow: bool = False,
    ) -> AgentResult:
        fix_diff = db_match["fix_diff"]
        rel_file, old_block, new_block = self._parse_diff(fix_diff)

        if not rel_file:
            return AgentResult(success=False, error="no file in diff", path_used="brain_db_diff")

        abs_path = self._resolve_file(rel_file, repo_path)
        if not abs_path:
            return AgentResult(success=False, error=f"file not found: {rel_file}", path_used="brain_db_diff")

        try:
            with open(abs_path, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except Exception as exc:
            return AgentResult(success=False, error=str(exc), path_used="brain_db_diff")

        old_stripped = old_block.strip()
        new_stripped = new_block.strip()

        if not old_stripped or old_stripped not in content:
            return AgentResult(success=False, error="old content not found", path_used="brain_db_diff")

        line_num = content[:content.find(old_stripped)].count("\n") + 1
        rel_display = os.path.relpath(abs_path, repo_path)
        change = {
            "file": rel_display,
            "line": line_num,
            "old": old_stripped[:80],
            "new": new_stripped[:80],
        }

        if shadow:
            return AgentResult(
                success=True,
                changes_applied=[change],
                root_cause=db_match.get("pattern", ""),
                confidence="HIGH",
                tokens_used=0,
                path_used="brain_db_diff",
            )

        new_content = content.replace(old_stripped, new_stripped, 1)
        if new_content == content:
            new_content = self._line_replace(content, old_block, new_block)
        if new_content == content:
            return AgentResult(success=False, error="replace produced no change", path_used="brain_db_diff")

        self._write_atomic(abs_path, new_content)
        return AgentResult(
            success=True,
            changes_applied=[change],
            root_cause=db_match.get("pattern", ""),
            confidence="HIGH",
            tokens_used=0,
            path_used="brain_db_diff",
        )

    @staticmethod
    def _line_replace(content: str, old_block: str, new_block: str) -> str:
        """
        Fallback: match stripped lines, preserve original indentation.
        """
        old_stripped_lines = [l.strip() for l in old_block.splitlines() if l.strip()]
        new_block_lines = new_block.splitlines()
        content_lines = content.splitlines(keepends=True)

        for i in range(len(content_lines)):
            if not old_stripped_lines or content_lines[i].strip() != old_stripped_lines[0]:
                continue
            match = True
            j = i
            for ol in old_stripped_lines:
                if j >= len(content_lines) or content_lines[j].strip() != ol:
                    match = False
                    break
                j += 1
            if not match:
                continue
            indent = len(content_lines[i]) - len(content_lines[i].lstrip())
            prefix = " " * indent
            replacement = [prefix + nl.lstrip() + "\n" for nl in new_block_lines]
            content_lines[i:j] = replacement
            return "".join(content_lines)

        return content

    @staticmethod
    def _extract_minimal_context(file_path: str, line_num: int) -> str:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()
            start = max(0, line_num - 4)  # 3 before
            end = min(len(lines), line_num + 3)  # 3 after
            numbered: List[str] = []
            for i, line in enumerate(lines[start:end], start=start + 1):
                marker = ">>>" if i == line_num else "   "
                numbered.append(f"{marker} {i:4d}: {line.rstrip()}")
            return "\n".join(numbered)
        except Exception:
            return ""

    def _get_surgical_context(
        self,
        file_path: str,
        line_num: int,
        repo_path: str,
    ) -> str:
        """
        Try slicer first (tree-sitter function extraction).
        Fall back to 7-line window if slicer fails or finds nothing.
        Never raises — always returns a string.
        """
        try:
            import slicer as _slicer
            import os

            rel_path = os.path.relpath(file_path, repo_path)

            slices = _slicer.slice_file(file_path)

            if slices:
                best = None
                for s in slices:
                    start = s.get("start_line", 0)
                    end = s.get("end_line", 0)
                    if start <= line_num <= end:
                        best = s
                        break

                if best is None and slices:
                    best = min(
                        slices,
                        key=lambda s: abs(s.get("start_line", 0) - line_num)
                    )

                if best:
                    source = best.get("source", "")
                    func_name = best.get("function_name", "")
                    start_line = best.get("start_line", line_num)

                    numbered = []
                    for i, line in enumerate(source.splitlines(), start=start_line):
                        marker = ">>>" if i == line_num else "   "
                        numbered.append(f"{marker} {i:4d}: {line}")

                    header = f"# Function: {func_name} ({rel_path})"
                    return header + "\n" + "\n".join(numbered)
        except Exception:
            pass

        return self._extract_minimal_context(file_path, line_num)

    @staticmethod
    def _verify_change_safe(file_path: str, change: dict) -> bool:
        """Return True only if old content exists exactly as specified."""
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()
            line_idx = (change.get("line") or 1) - 1
            old_stripped = (change.get("old") or "").strip()

            if not old_stripped:
                return False

            # Check exact line first
            if 0 <= line_idx < len(lines):
                if old_stripped in lines[line_idx].strip():
                    return True

            # Check +/-2 lines
            for offset in (-2, -1, 1, 2):
                idx = line_idx + offset
                if 0 <= idx < len(lines):
                    if old_stripped in lines[idx].strip():
                        change["line"] = idx + 1  # update to actual line
                        return True

            return False
        except Exception:
            return False

    # ── PATH B helpers ────────────────────────────────────────────────────────

    def _claude_api_fix(
        self,
        findings: list,
        repo_path: str,
        db_match: Optional[dict],
        hint: str,
        shadow: bool = False,
    ) -> AgentResult:
        # Normalize findings to a common shape
        norm = [self._norm_finding(f, repo_path) for f in findings[:1]]
        norm = [f for f in norm if f["file_path"]]

        if not norm:
            return AgentResult(success=False, error="no resolvable file paths", path_used="claude_api")

        primary = norm[0]

        primary_file_relative = os.path.relpath(primary["file_path"], repo_path)
        primary_line_number = primary["line_number"] or 1
        primary_finding_message = primary["message"] or primary["rule_id"] or "unspecified issue"
        minimal_context = self._get_surgical_context(
            primary["file_path"],
            primary_line_number,
            repo_path,
        )

        db_section = ""
        if db_match:
            db_section = (
                f"VERIFIED FIX FROM DATABASE:\n"
                f"Category: {db_match.get('category', 'UNKNOWN')}\n"
                f"Pattern: {db_match.get('pattern', '')}\n"
            )
            if db_match.get("fix_diff"):
                db_section += f"Similar fix applied before:\n{db_match['fix_diff'][:300]}\n"

        prompt = f"""You are a surgical code patcher. Make the minimum possible change.

TICKET: {hint or "(no hint)"}

ISSUE: {primary_finding_message}
FILE: {primary_file_relative}
LINE: {primary_line_number}

CONTEXT (function containing the broken line, >>> marks the problem):
{minimal_context}

KNOWN PATTERN FROM DATABASE:
{db_section or "No exact match — use the issue description to determine fix."}

RULES — READ CAREFULLY:
1. Return ONLY valid JSON. No markdown. No backticks. No explanation.
2. The "old" field must be the EXACT content of the broken line (copy it exactly from context above).
3. The "new" field must be the replacement for that ONE line only.
4. If fix requires adding an import: add it as a SEPARATE change with the import line.
5. Maximum 3 changes total. If you need more than 3 changes → return empty changes array.
6. Do NOT reformat, rename, or restructure anything.
7. Do NOT add comments.
8. Do NOT change indentation of surrounding lines.
9. The >>> prefix in the context above is a visual marker only. Do NOT include >>> in the "old" field. Copy the exact line content without any prefix.
10. For a missing on_auth_user_created trigger: create a NEW file supabase/migrations/<YYYYMMDDHHMMSS>_add_user_trigger.sql — never modify existing migration files. Set "old" to "" (empty string) and "new" to the full file content. Use EXECUTE FUNCTION not EXECUTE PROCEDURE.

JSON FORMAT:
{{
  "root_cause": "one sentence — what is wrong",
  "changes": [
    {{
      "file": "{primary_file_relative}",
      "line": {primary_line_number},
      "old": "exact content of the broken line",
      "new": "replacement content"
    }}
  ],
  "confidence": "HIGH|MED|LOW"
}}

If you are not certain of the exact fix → return:
{{"changes": [], "root_cause": "uncertain", "confidence": "LOW"}}"""

        try:
            import anthropic
            client = anthropic.Anthropic()
            response = _tracer.trace_claude(
                client,
                model=_CLAUDE_MODEL,
                max_tokens=1000,
                system="You are a surgical code fixer. Return only valid JSON. Never explain. Never use markdown.",
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()
            tokens_used = response.usage.input_tokens + response.usage.output_tokens
        except ImportError:
            return AgentResult(success=False, error="anthropic SDK not installed", path_used="claude_api")
        except Exception as exc:
            err = str(exc)
            if "api_key" in err.lower() or "authentication" in err.lower() or "ANTHROPIC_API_KEY" in err:
                return AgentResult(success=False, error="ANTHROPIC_API_KEY not set", path_used="claude_api")
            return AgentResult(success=False, error=f"API error: {err[:80]}", path_used="claude_api")

        # Step 1: try to extract ```json ... ``` block first
        import re as _re
        _fence_match = _re.search(r'```json\s*(.*?)\s*```', raw, _re.DOTALL)
        if _fence_match:
            raw = _fence_match.group(1).strip()
        else:
            # Step 2: strip any fence markers and find first { ... } block
            raw = _re.sub(r'```json\s*|```\s*', '', raw).strip()
            _json_match = _re.search(r'(\{[\s\S]*\})', raw)
            if _json_match:
                raw = _json_match.group(1).strip()

        try:
            result_data = json.loads(raw)
        except json.JSONDecodeError:
            return AgentResult(
                success=False,
                error="Claude returned invalid JSON",
                tokens_used=tokens_used,
                path_used="claude_api",
            )

        if not result_data.get("changes"):
            return AgentResult(
                success=False,
                error=result_data.get("root_cause", "no changes"),
                confidence=result_data.get("confidence", "LOW"),
                tokens_used=tokens_used,
                path_used="claude_api",
            )

        changes_applied: List[Dict[str, Any]] = []

        if shadow:
            for change in result_data["changes"]:
                changes_applied.append({
                    "file": change.get("file", ""),
                    "line": change.get("line", ""),
                    "old": (change.get("old") or "")[:80],
                    "new": (change.get("new") or "")[:80],
                })
            return AgentResult(
                success=True,
                changes_applied=changes_applied,
                root_cause=result_data.get("root_cause", ""),
                confidence=result_data.get("confidence", "MED"),
                tokens_used=tokens_used,
                path_used="claude_api",
            )

        # Apply each change
        for change in result_data["changes"]:
            change_rel = change.get("file", "")
            if not change_rel:
                continue
            abs_path = os.path.join(repo_path, change_rel)
            if not os.path.isfile(abs_path):
                if (change.get("old") or "").strip() == "":
                    real_repo = os.path.realpath(repo_path)
                    real_abs = os.path.realpath(os.path.normpath(abs_path))
                    if not real_abs.startswith(real_repo + os.sep):
                        continue
                    os.makedirs(os.path.dirname(real_abs), exist_ok=True)
                    self._write_atomic(real_abs, (change.get("new") or "") + "\n")
                    changes_applied.append({
                        "file": change_rel,
                        "line": 1,
                        "old": "",
                        "new": (change.get("new") or "")[:80],
                    })
                continue
            if not self._verify_change_safe(abs_path, change):
                continue

            try:
                with open(abs_path, "r", encoding="utf-8", errors="replace") as fh:
                    lines = fh.readlines()
            except Exception:
                continue

            target_idx = (change.get("line") or 1) - 1  # 0-based
            old_stripped = (change.get("old") or "").strip()
            new_line_content = change.get("new") or ""

            found_idx = target_idx
            if not (0 <= found_idx < len(lines)):
                continue

            # Preserve original indentation
            orig = lines[found_idx]
            indent_len = len(orig) - len(orig.lstrip())
            new_line = " " * indent_len + new_line_content.lstrip() + "\n"
            lines[found_idx] = new_line

            self._write_atomic(abs_path, "".join(lines))
            changes_applied.append({
                "file": change_rel,
                "line": found_idx + 1,
                "old": old_stripped[:80],
                "new": new_line_content[:80],
            })

        if not changes_applied:
            return AgentResult(
                success=False,
                error="no changes could be applied safely",
                root_cause=result_data.get("root_cause", ""),
                confidence=result_data.get("confidence", "LOW"),
                tokens_used=tokens_used,
                path_used="claude_api",
            )

        return AgentResult(
            success=True,
            changes_applied=changes_applied,
            root_cause=result_data.get("root_cause", ""),
            confidence=result_data.get("confidence", "HIGH"),
            tokens_used=tokens_used,
            path_used="claude_api",
        )

    # ── Utility ───────────────────────────────────────────────────────────────

    @staticmethod
    def _norm_finding(finding: dict, repo_path: str) -> dict:
        """
        Normalise both shapes to {rule_id, file_path, line_number, message}.
        Handles: fix_writer shape (file_path) and raw scored-layer findings via resolve().
        """
        if "file_path" in finding:
            return {
                "rule_id":     finding.get("rule_id", ""),
                "file_path":   finding["file_path"],
                "line_number": finding.get("line_number") or 0,
                "message":     finding.get("message", ""),
            }

        r = resolve(finding, repo_path)
        f = r.raw_finding
        fp = r.abs_path or (
            os.path.normpath(os.path.join(repo_path, r.rel_path)) if r.rel_path else ""
        )
        line = r.line or 0

        if r.source == "chain_walker":
            chain = f.get("chain", "OTHER")
            missing = f.get("missing", "")
            rule_id = f"{str(chain).lower()}-{missing.lower().replace(' ', '-')}"
            msg = f.get("issue", "")
        elif r.source in ("semgrep", "probe") and f.get("check_id"):
            cid = f.get("check_id") or ""
            rule_id = cid.split(".")[-1] if cid else ""
            msg = (f.get("extra") or {}).get("message", "")
            if isinstance(msg, str) and "\n" in msg:
                msg = msg.split("\n")[0]
        elif r.source == "schema":
            rule_id = f.get("check") or ""
            msg = f.get("fix_hint") or f.get("check") or ""
        elif r.source == "fs_checks":
            rule_id = f.get("rule") or ""
            msg = f.get("message", "")
        else:
            rule_id = finding.get("rule_id", "")
            msg = finding.get("message", "")

        return {
            "rule_id":     rule_id,
            "file_path":   fp,
            "line_number": line,
            "message":     msg,
        }

    @staticmethod
    def _write_atomic(path: str, content: str) -> None:
        d = os.path.dirname(os.path.abspath(path)) or "."
        fd, tmp = tempfile.mkstemp(prefix=".rkt_", suffix=".tmp", dir=d)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as w:
                w.write(content)
            os.replace(tmp, path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
