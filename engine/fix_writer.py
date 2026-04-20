"""
Deterministic file fixes from structured findings (Semgrep + schema + chain_walker).

Uses tree-sitter for TypeScript/TSX structure; regex for SQL and simple line swaps.
"""

from __future__ import annotations

import difflib
import glob
import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

# ── tree-sitter (optional at import time; rules degrade to regex if missing) ──
_TS_LANG = None
_TS_PARSER = None

try:
    from tree_sitter import Language as _TSLanguage
    from tree_sitter import Parser as _TSParser

    import tree_sitter_typescript as _tsts

    _TS_LANG = _TSLanguage(_tsts.language_tsx())
    _TS_PARSER = _TSParser(_TS_LANG)
except Exception as e:  # pragma: no cover - import guard
    sys.stderr.write(f"[fix_writer] tree-sitter unavailable: {e}\n")


# SQL column type only: not a substring of a word, not TIMESTAMPTZ / TIMESTAMP WITH TIME ZONE,
# not immediately after "--" (two-char lookbehind), and only on lines that are not full-line -- comments.
_TIMESTAMP_SQL_TYPE_RE = re.compile(
    r"(?<![\w])(?<!--)TIMESTAMP(?!\s*with\s+time\s+zone)(?!Z)(?![\w])",
    re.IGNORECASE,
)


def _sql_line_is_full_line_comment(line: str) -> bool:
    """True when the line is only a SQL -- comment (optional leading whitespace)."""
    return bool(re.match(r"^\s*--", line))


def _sql_content_has_bare_timestamp_column(content: str) -> bool:
    for line in content.splitlines():
        if _sql_line_is_full_line_comment(line):
            continue
        if _TIMESTAMP_SQL_TYPE_RE.search(line):
            return True
    return False

_IMPORT_CREATE_CLIENT = re.compile(
    r"^import\s*\{\s*createClient\s*\}\s*from\s*['\"]@supabase/supabase-js['\"]\s*;?\s*$",
    re.MULTILINE,
)
_NON_IMPORT_CREATECLIENT_CALL_RE = re.compile(
    r"^(?!\s*import\b).*\bcreateClient\s*\(",
    re.MULTILINE,
)

_RE_GET_SESSION = re.compile(r"\.auth\.getSession\s*\(\s*\)")
_RE_DESTR_SESSION = re.compile(
    r"\{\s*data:\s*\{\s*session\s*\}\s*\}"
)
_RE_DESTR_SESSION_ERR = re.compile(
    r"\{\s*data:\s*\{\s*session\s*\}\s*,\s*error\s*\}"
)
# After renaming the destructured variable session→user, fix body references.
# session?.user and session.user both become plain `user` (getUser returns user directly).
# Only applied when session does NOT appear as a callback parameter elsewhere in the file
# (e.g. onAuthStateChange(_event, session) => {...}) — that's a different variable.
_RE_SESSION_OPT_USER = re.compile(r"\bsession\?\.user\b")
_RE_SESSION_DOT_USER = re.compile(r"\bsession\.user\b")
_RE_SESSION_AS_PARAM = re.compile(r"\(\s*[^)]*\bsession\b[^)]*\)\s*=>")

_RE_AWAIT_REQUEST_JSON = re.compile(r"await\s+request\.json\s*\(\s*\)")
_RE_AWAIT_REQ_JSON = re.compile(
    r"await\s+([a-zA-Z_$][\w$]*)\.json\s*\(\s*\)"
)

_DYNAMIC_SNIPPET = "\nexport const dynamic = 'force-dynamic'\n"

_CANONICAL_MIDDLEWARE = """// middleware.ts — PROJECT ROOT, not /app/middleware.ts
import { type NextRequest } from 'next/server'
import { updateSession } from '@/lib/supabase/middleware'
export async function middleware(request: NextRequest) {
  return await updateSession(request)
}
export const config = { matcher: ['/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)'] }
"""


@dataclass
class FixResult:
    files_modified: List[str] = field(default_factory=list)
    fixes_applied: int = 0
    fixes_skipped: int = 0
    diffs: Dict[str, str] = field(default_factory=dict)
    audit_log: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class FileProposal:
    file_path: str
    proposed_content: Optional[str]
    proposed_diff: str
    rules: List[str] = field(default_factory=list)
    confidence_summary: str = "HIGH"
    change_class: str = "APPLY_CANDIDATE"
    post_apply_audit_entries: List[Dict[str, Any]] = field(default_factory=list)
    preview_only: bool = False


@dataclass
class FixPlan:
    proposals: List[FileProposal] = field(default_factory=list)
    audit_log: List[Dict[str, Any]] = field(default_factory=list)


def collect_schema_timestamptz_findings(repo_root: str) -> List[Dict[str, Any]]:
    """Synthetic findings per migration file that still contains bare TIMESTAMP."""
    repo_root = os.path.abspath(os.path.expanduser(repo_root))
    migrations_dir = os.path.join(repo_root, "supabase", "migrations")
    if not os.path.isdir(migrations_dir):
        return []
    out: List[Dict[str, Any]] = []
    for sql_path in sorted(glob.glob(os.path.join(migrations_dir, "*.sql"))):
        try:
            with open(sql_path, "r", encoding="utf-8", errors="replace") as fh:
                txt = fh.read()
        except OSError:
            continue
        if _sql_content_has_bare_timestamp_column(txt):
            out.append(
                {
                    "rule_id": "schema-timestamptz",
                    "file_path": sql_path,
                    "line_number": 0,
                    "message": "bare TIMESTAMP — use TIMESTAMPTZ",
                    "_repo_root": repo_root,
                }
            )
    return out


def dedupe_findings(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: Set[Tuple[str, str]] = set()
    out: List[Dict[str, Any]] = []
    for f in findings:
        key = (f.get("file_path") or "", f.get("rule_id") or "")
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    return out


def _confidence_rank(confidence: str) -> int:
    return {"LOW": 1, "MED": 2, "HIGH": 3}.get((confidence or "HIGH").upper(), 3)


def _confidence_for_rules(entries: List[Dict[str, Any]]) -> str:
    if not entries:
        return "HIGH"
    weakest = min(
        (e.get("confidence", "HIGH") for e in entries),
        key=_confidence_rank,
    )
    return (weakest or "HIGH").upper()


def _read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


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


def _backup_once(path: str) -> None:
    bak = path + ".rkt_backup"
    shutil.copy2(path, bak)


def _unified_diff(a_path: str, before: str, after: str) -> str:
    a_lines = before.splitlines(keepends=True)
    b_lines = after.splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(
            a_lines,
            b_lines,
            fromfile="a/" + os.path.basename(a_path),
            tofile="b/" + os.path.basename(a_path),
            lineterm="\n",
        )
    )


def colorize_unified_diff(diff_text: str, enable_color: Optional[bool] = None) -> str:
    """
    Render unified diff with ANSI colors:
    - '+' lines green
    - '-' lines red
    - hunk headers cyan
    - file headers bold
    """
    if enable_color is None:
        enable_color = bool(sys.stdout.isatty() and not os.environ.get("NO_COLOR"))
    if not enable_color or not diff_text:
        return diff_text

    c_reset = "\033[0m"
    c_green = "\033[32m"
    c_red = "\033[31m"
    c_cyan = "\033[36m"
    c_bold = "\033[1m"

    out: List[str] = []
    for line in diff_text.splitlines(keepends=True):
        if line.startswith("+++ ") or line.startswith("--- "):
            out.append(f"{c_bold}{line}{c_reset}")
        elif line.startswith("@@ "):
            out.append(f"{c_cyan}{line}{c_reset}")
        elif line.startswith("+") and not line.startswith("+++ "):
            out.append(f"{c_green}{line}{c_reset}")
        elif line.startswith("-") and not line.startswith("--- "):
            out.append(f"{c_red}{line}{c_reset}")
        else:
            out.append(line)
    return "".join(out)


def _ts_root_node(source: str) -> Tuple[Optional[Any], bytes]:
    src_b = source.encode("utf-8")
    if _TS_PARSER is None:
        return None, src_b
    tree = _TS_PARSER.parse(src_b)
    root = tree.root_node
    if root is None or root.type != "program":
        return None, src_b
    return root, src_b


def _last_import_insert_byte(root: Any, src_b: bytes) -> int:
    """Byte offset immediately after the last top-level import or re-export-from."""
    last_end: Optional[int] = None
    for child in root.named_children:
        t = child.type
        if t == "import_statement":
            last_end = child.end_byte
        elif t == "export_statement":
            chunk = src_b[child.start_byte : child.end_byte].decode(
                "utf-8", errors="replace"
            )
            if " from " in chunk or "from '" in chunk or 'from "' in chunk:
                last_end = child.end_byte
    if last_end is not None:
        return last_end
    # Fallback: first line (no imports)
    return 0


def _line_fallback_import_insert(source: str) -> int:
    lines = source.split("\n")
    last_idx = -1
    for i, line in enumerate(lines):
        s = line.strip()
        if not s or s.startswith("//") or s.startswith("/*"):
            continue
        if s.startswith("import ") or s.startswith("import{"):
            last_idx = i
        elif s.startswith("export ") and " from " in s:
            last_idx = i
    if last_idx < 0:
        return 0
    return len("\n".join(lines[: last_idx + 1])) + (1 if last_idx + 1 < len(lines) else 0)


def _has_force_dynamic(source: str) -> bool:
    return bool(
        re.search(
            r"export\s+const\s+dynamic\s*=\s*['\"]force-dynamic['\"]",
            source,
        )
    )


def _is_client_component(source: str) -> bool:
    """
    True when file declares a top-level 'use client' directive.
    """
    for raw_line in source.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("//"):
            continue
        if line in ("'use client'", '"use client"', "'use client';", '"use client";'):
            return True
        return False
    return False


def _apply_sql_timestamptz(content: str) -> Tuple[str, int]:
    """Replace bare TIMESTAMP column types; skip whole-line -- comments."""
    n = 0
    pat = _TIMESTAMP_SQL_TYPE_RE
    out_chunks: List[str] = []
    for line in content.splitlines(keepends=True):
        if _sql_line_is_full_line_comment(line):
            out_chunks.append(line)
            continue

        def repl(_m: re.Match) -> str:
            nonlocal n
            n += 1
            return "TIMESTAMPTZ"

        out_chunks.append(pat.sub(repl, line))
    return "".join(out_chunks), n


def _apply_ts_transforms(
    path: str,
    original: str,
    rules: Set[str],
) -> Tuple[str, List[str], List[Dict[str, Any]]]:
    """
    Returns (new_text, applied_rule_ids, audit_entries for this file).
    """
    working = original
    applied: List[str] = []
    audits: List[Dict[str, Any]] = []
    line_hint = 0

    def audit(rule: str, line: int, action: str, confidence: str) -> None:
        audits.append(
            {
                "rule": rule,
                "file": path,
                "line": line,
                "action": action,
                "confidence": confidence,
            }
        )

    # ── Parse (optional tree-sitter) ─────────────────────────────────────────
    root, src_b = _ts_root_node(working)

    # Rule 4: getSession → getUser
    if "supabase-getsession-not-getuser" in rules:
        before = working
        working = _RE_GET_SESSION.sub(".auth.getUser()", working)
        working = _RE_DESTR_SESSION_ERR.sub("{ data: { user }, error }", working)
        working = _RE_DESTR_SESSION.sub("{ data: { user } }", working)
        # Fix body references: getUser() returns user directly (not session.user).
        # Skip if session is also a callback parameter in this file (different variable scope).
        if not _RE_SESSION_AS_PARAM.search(working):
            working = _RE_SESSION_OPT_USER.sub("user", working)
            working = _RE_SESSION_DOT_USER.sub("user", working)
        if working != before:
            applied.append("supabase-getsession-not-getuser")
            audit("supabase-getsession-not-getuser", line_hint, "applied", "HIGH")

    # Rule 3: Stripe webhook body
    for stripe_rule in (
        "stripe-webhook-request-json",
        "stripe-webhook-req-json-var",
    ):
        if stripe_rule not in rules:
            continue
        before = working
        working = _RE_AWAIT_REQUEST_JSON.sub("await request.text()", working)
        working = _RE_AWAIT_REQ_JSON.sub(
            lambda m: f"await {m.group(1)}.text()", working
        )
        if working != before:
            applied.append(stripe_rule)
            audit(stripe_rule, line_hint, "applied", "HIGH")

    # Rule 2 MED: wrong import
    if "supabase-js-in-server-file" in rules:
        # Safety gate: if createClient(...) calls still exist in non-import lines,
        # don't apply a partial import swap that would break runtime/typing.
        has_createclient_calls = bool(_NON_IMPORT_CREATECLIENT_CALL_RE.search(working))
        if not has_createclient_calls:
            working, n_sub = _IMPORT_CREATE_CLIENT.subn(
                "import { createServerClient } from '@supabase/ssr'", working
            )
            if n_sub:
                applied.append("supabase-js-in-server-file")
                audit("supabase-js-in-server-file", line_hint, "applied", "MED")
        else:
            audit("supabase-js-in-server-file", line_hint, "skipped", "MED")

    # Rule 1: force-dynamic after imports (server components/pages only).
    # Never inject into 'use client' files.
    if (
        "supabase-missing-dynamic-export" in rules
        and not _has_force_dynamic(working)
        and not _is_client_component(working)
    ):
        insert_at: int
        if root is not None and _TS_PARSER is not None:
            src_b2 = working.encode("utf-8")
            tree2 = _TS_PARSER.parse(src_b2)
            r2 = tree2.root_node
            if r2 and r2.type == "program":
                insert_at = _last_import_insert_byte(r2, src_b2)
            else:
                insert_at = _line_fallback_import_insert(working)
        else:
            insert_at = _line_fallback_import_insert(working)
        wb = working.encode("utf-8")
        new_b = wb[:insert_at] + _DYNAMIC_SNIPPET.encode("utf-8") + wb[insert_at:]
        new_s = new_b.decode("utf-8")
        if new_s != working:
            working = new_s
            applied.append("supabase-missing-dynamic-export")
            audit("supabase-missing-dynamic-export", line_hint, "applied", "HIGH")
    elif "supabase-missing-dynamic-export" in rules and _is_client_component(working):
        audit("supabase-missing-dynamic-export", line_hint, "skipped", "HIGH")

    return working, applied, audits


def _process_sql_file(
    path: str, original: str, audits: List[Dict[str, Any]]
) -> Tuple[str, bool, List[str]]:
    new_content, n = _apply_sql_timestamptz(original)
    if n == 0:
        audits.append(
            {
                "rule": "schema-timestamptz",
                "file": path,
                "line": 0,
                "action": "skipped",
                "confidence": "HIGH",
            }
        )
        return original, False, []
    audits.append(
        {
            "rule": "schema-timestamptz",
            "file": path,
            "line": 0,
            "action": "applied",
            "confidence": "HIGH",
        }
    )
    return new_content, True, ["schema-timestamptz"]


def _process_middleware_diff_only(
    path: str, audits: List[Dict[str, Any]], diffs: Dict[str, str]
) -> None:
    try:
        original = _read_text(path)
    except OSError:
        audits.append(
            {
                "rule": "middleware-missing-updatesession",
                "file": path,
                "line": 0,
                "action": "skipped",
                "confidence": "LOW",
            }
        )
        return
    diff = _unified_diff(path, original, _CANONICAL_MIDDLEWARE)
    if diff.strip():
        diffs[path] = diff
    audits.append(
        {
            "rule": "middleware-missing-updatesession",
            "file": path,
            "line": 0,
            "action": "diff_only",
            "confidence": "LOW",
        }
    )


def plan_fixes(
    findings: List[Dict[str, Any]], db_match=None, kb_hits=None
) -> FixPlan:
    plan = FixPlan()
    if not findings:
        return plan

    findings = dedupe_findings(list(findings))
    by_file: Dict[str, Set[str]] = {}
    repo_root_by_file: Dict[str, str] = {}
    for f in findings:
        p = f.get("file_path") or ""
        if not p:
            plan.audit_log.append(
                {
                    "rule": "(invalid)",
                    "file": "",
                    "line": 0,
                    "action": "skipped",
                    "confidence": "HIGH",
                }
            )
            continue
        p = os.path.normpath(os.path.abspath(os.path.expanduser(p)))
        rid = f.get("rule_id") or ""
        by_file.setdefault(p, set()).add(rid)
        rr = f.get("_repo_root") or ""
        if rr:
            repo_root_by_file[p] = rr

    for path in sorted(by_file.keys()):
        rules = set(by_file[path])
        ext = os.path.splitext(path)[1].lower()

        if ext == ".sql":
            if "schema-timestamptz" not in rules:
                continue
            if not os.path.isfile(path):
                plan.audit_log.append(
                    {
                        "rule": "schema-timestamptz",
                        "file": path,
                        "line": 0,
                        "action": "skipped",
                        "confidence": "HIGH",
                    }
                )
                continue
            orig_sql = _read_text(path)
            file_audits: List[Dict[str, Any]] = []
            new_sql, changed, _applied_rules = _process_sql_file(path, orig_sql, file_audits)
            plan.audit_log.extend(file_audits)
            if not changed:
                continue
            diff_txt = _unified_diff(path, orig_sql, new_sql)
            if diff_txt.strip():
                plan.proposals.append(
                    FileProposal(
                        file_path=path,
                        proposed_content=new_sql,
                        proposed_diff=diff_txt,
                        rules=["schema-timestamptz"],
                        confidence_summary=_confidence_for_rules(file_audits),
                        change_class="APPLY_CANDIDATE",
                        post_apply_audit_entries=file_audits,
                        preview_only=False,
                    )
                )
            continue

        if "middleware-missing-updatesession" in rules and ext in (".ts", ".tsx", ".js", ".mjs"):
            tmp_diffs: Dict[str, str] = {}
            middleware_audits: List[Dict[str, Any]] = []
            _process_middleware_diff_only(path, middleware_audits, tmp_diffs)
            plan.audit_log.extend(middleware_audits)
            diff_txt = tmp_diffs.get(path, "")
            if diff_txt.strip():
                plan.proposals.append(
                    FileProposal(
                        file_path=path,
                        proposed_content=None,
                        proposed_diff=diff_txt,
                        rules=["middleware-missing-updatesession"],
                        confidence_summary=_confidence_for_rules(middleware_audits),
                        change_class="PREVIEW_ONLY",
                        post_apply_audit_entries=middleware_audits,
                        preview_only=True,
                    )
                )
            rules.discard("middleware-missing-updatesession")
            if not rules:
                continue

        if ext not in (".ts", ".tsx", ".js", ".jsx", ".mjs"):
            for r in rules:
                plan.audit_log.append(
                    {
                        "rule": r,
                        "file": path,
                        "line": 0,
                        "action": "skipped",
                        "confidence": "HIGH",
                    }
                )
            continue

        if not os.path.isfile(path):
            for r in rules:
                plan.audit_log.append(
                    {
                        "rule": r,
                        "file": path,
                        "line": 0,
                        "action": "skipped",
                        "confidence": "HIGH",
                    }
                )
            continue

        try:
            original = _read_text(path)
        except OSError as e:
            sys.stderr.write(f"[fix_writer] skip unreadable {path}: {e}\n")
            for r in rules:
                plan.audit_log.append(
                    {
                        "rule": r,
                        "file": path,
                        "line": 0,
                        "action": "skipped",
                        "confidence": "HIGH",
                    }
                )
            continue

        new_text, applied_rules, chunk_audits = _apply_ts_transforms(path, original, rules)
        plan.audit_log.extend(chunk_audits)
        if new_text != original:
            diff_txt = _unified_diff(path, original, new_text)
            if diff_txt.strip():
                plan.proposals.append(
                    FileProposal(
                        file_path=path,
                        proposed_content=new_text,
                        proposed_diff=diff_txt,
                        rules=sorted(applied_rules),
                        confidence_summary=_confidence_for_rules(chunk_audits),
                        change_class="APPLY_CANDIDATE",
                        post_apply_audit_entries=chunk_audits,
                        preview_only=False,
                    )
                )

        # LOW: import-only swap preview if createClient( remains
        if "supabase-js-in-server-file" in rules:
            swapped = _IMPORT_CREATE_CLIENT.sub(
                "import { createServerClient } from '@supabase/ssr'", original
            )
            if "createClient(" in swapped:
                low_diff = _unified_diff(path, original, swapped)
                if low_diff.strip():
                    warn_entry = {
                        "rule": "supabase-js-in-server-file",
                        "file": path,
                        "line": 0,
                        "action": "warn_refactor",
                        "confidence": "LOW",
                    }
                    plan.audit_log.append(warn_entry)
                    plan.proposals.append(
                        FileProposal(
                            file_path=path,
                            proposed_content=None,
                            proposed_diff=low_diff,
                            rules=["supabase-js-in-server-file"],
                            confidence_summary="LOW",
                            change_class="WARN_REFACTOR",
                            post_apply_audit_entries=[warn_entry],
                            preview_only=True,
                        )
                    )

        for r in rules:
            if r in ("middleware-missing-updatesession", "schema-timestamptz"):
                continue
            if r in applied_rules:
                continue
            if r == "supabase-js-in-server-file":
                continue
            if r not in (
                "stripe-webhook-request-json",
                "stripe-webhook-req-json-var",
                "supabase-getsession-not-getuser",
                "supabase-missing-dynamic-export",
            ):
                continue
            plan.audit_log.append(
                {
                    "rule": r,
                    "file": path,
                    "line": 0,
                    "action": "skipped",
                    "confidence": "HIGH",
                }
            )

    return plan


def apply_fix_plan(
    plan: FixPlan,
    selected_paths: Optional[Set[str]] = None,
    write_changes: bool = True,
) -> FixResult:
    result = FixResult()
    result.audit_log = list(plan.audit_log)
    selected = set(selected_paths or [])
    selected_all = selected_paths is None

    for proposal in plan.proposals:
        result.diffs[proposal.file_path] = proposal.proposed_diff
        if proposal.preview_only or proposal.proposed_content is None:
            continue
        should_apply = selected_all or proposal.file_path in selected
        if not should_apply:
            continue
        if write_changes:
            _backup_once(proposal.file_path)
            _write_atomic(proposal.file_path, proposal.proposed_content)
            if proposal.file_path not in result.files_modified:
                result.files_modified.append(proposal.file_path)
        result.fixes_applied += len(proposal.rules)

    result.fixes_skipped = sum(
        1 for a in result.audit_log if a.get("action") == "skipped"
    )
    return result


def apply_fixes(
    findings: List[Dict[str, Any]],
    write_changes: bool = True,
    selected_paths: Optional[Set[str]] = None,
) -> FixResult:
    """
    Backward-compatible apply entrypoint. When selected_paths is provided,
    only those write-capable file proposals are applied.
    """
    plan = plan_fixes(findings)
    return apply_fix_plan(plan, selected_paths=selected_paths, write_changes=write_changes)


def append_audit_jsonl(audit_path: str, entries: List[Dict[str, Any]]) -> None:
    audit_path = os.path.expanduser(audit_path)
    parent = os.path.dirname(audit_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(audit_path, "a", encoding="utf-8") as fh:
        for row in entries:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def print_diff_summary(diffs: Dict[str, str], max_lines_per_file: int = 48) -> None:
    if not diffs:
        print("\n[fix_writer] No unified diffs produced.", flush=True)
        return
    print("\n[fix_writer] Diff summary", flush=True)
    for p in sorted(diffs.keys()):
        body = diffs[p]
        lines = body.splitlines()
        print(f"\n+{'-' * 96}+", flush=True)
        print(f"| FILE: {p}", flush=True)
        print(f"| LINES: {len(lines)}", flush=True)
        print(f"+{'-' * 96}+", flush=True)
        preview_body = "\n".join(lines[:max_lines_per_file])
        if preview_body:
            print(colorize_unified_diff(preview_body), flush=True)
        if len(lines) > max_lines_per_file:
            print(f"... ({len(lines) - max_lines_per_file} more lines)", flush=True)
        print(f"+{'-' * 96}+", flush=True)
