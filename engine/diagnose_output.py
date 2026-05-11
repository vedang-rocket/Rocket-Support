#!/usr/bin/env python3
"""
diagnose_output.py — Rich-formatted steps [2/4]–[4/4] for rkt-diagnose.

CLI:
    python diagnose_output.py --repo-path <path> [--hint <hint>]
                               [--thread <id>] [--project-name <name>]
                               [--shadow] [--out-file <path>]

Exit codes:  0 = success  2 = engine error
"""
import argparse
import contextlib
import glob
import io
import json
import os
import re
import sys
import threading
import time

ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ENGINE_DIR)

import tracer as _tracer
from finding_resolver import resolve

from rich.console import Console
from rich.table import Table
from rich.text import Text
from rich import box

# Capture real stdout BEFORE any suppression context changes sys.stdout
_REAL_STDOUT = sys.stdout
console = Console(file=_REAL_STDOUT, highlight=False)

# ── Colors ────────────────────────────────────────────────────────────────────

_CONF_COLOR = {"HIGH": "bright_green", "MED": "yellow", "LOW": "bright_red"}
_CAT_COLOR  = {
    "AUTH": "cyan", "STRIPE": "magenta", "SUPABASE": "blue",
    "BUILD": "yellow", "ENV": "orange1", "RLS": "red",
    "SCHEMA": "dark_orange", "UI": "white", "OTHER": "white",
}


# ── Step line helpers ─────────────────────────────────────────────────────────

def _step_start(n: int, total: int, label: str) -> None:
    line   = f"  \033[1;36m[{n}/{total}]\033[0m \033[1m{label}...\033[0m"
    plain  = f"  [{n}/{total}] {label}..."
    pad    = max(0, 44 - len(plain))
    _REAL_STDOUT.write(line + " " * pad)
    _REAL_STDOUT.flush()


def _step_done(detail: str = "") -> None:
    det = f"  {detail}" if detail else ""
    _REAL_STDOUT.write(f"\033[0;32m✓\033[0m{det}\n")
    _REAL_STDOUT.flush()


def _step_warn(detail: str = "") -> None:
    det = f"  {detail}" if detail else ""
    _REAL_STDOUT.write(f"\033[1;33m⚠\033[0m{det}\n")
    _REAL_STDOUT.flush()


def _step_fail(detail: str = "") -> None:
    det = f"  {detail}" if detail else ""
    _REAL_STDOUT.write(f"\033[0;31m✗\033[0m{det}\n")
    _REAL_STDOUT.flush()


# ── Output suppressor ─────────────────────────────────────────────────────────

@contextlib.contextmanager
def _quiet():
    """Redirect sys.stdout/stderr to /dev/null for noisy engine calls."""
    devnull = io.StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout = devnull
    sys.stderr = devnull
    try:
        yield
    finally:
        sys.stdout = old_out
        sys.stderr = old_err


# ── Confidence helpers ────────────────────────────────────────────────────────

def _conf_label(conf: float) -> str:
    if conf >= 0.85:
        return "HIGH"
    if conf >= 0.60:
        return "MED"
    return "LOW"


# ── Finding extraction ────────────────────────────────────────────────────────

def _root_cause(state: dict) -> str:
    scored = state.get("findings_scored") or []
    if scored:
        top = scored[0]
        src = top.get("source", "")
        f   = top.get("finding", {})
        if src == "chain_walker":
            return (f.get("issue") or f.get("missing") or "chain break")[:100]
        if src in ("semgrep", "probe"):
            msg = (f.get("extra") or {}).get("message", "")
            return (msg.split("\n")[0] if msg else (f.get("check_id") or "").split(".")[-1])[:100]
        if src == "schema":
            return (f.get("fix_hint") or f.get("check") or "schema issue")[:100]
        return f.get("message", "")[:100]

    db_match = state.get("db_match")
    if db_match:
        return db_match.get("pattern", "")[:100]

    cw = state.get("cw_findings") or []
    if cw:
        return cw[0].get("issue", "no issue text")[:100]

    return "no root cause identified"


def _files_for_display(state: dict, repo_path: str) -> list:
    files = []
    seen = set()
    for s in (state.get("findings_scored") or [])[:5]:
        r = resolve(s, repo_path)
        rel = r.rel_path or ""
        if not rel or rel in seen:
            continue
        seen.add(rel)
        line = r.line if r.line is not None else ""
        files.append({"path": rel, "line": line})
    return files


# ── Normalized findings for fix_writer ───────────────────────────────────────

def _normalized_findings(state: dict, repo_path: str) -> list:
    def _first_sql_file() -> str:
        matches = sorted(glob.glob(os.path.join(repo_path, "supabase", "migrations", "*.sql")))
        return matches[0] if matches else ""

    out = []
    for cw in state.get("cw_findings") or []:
        r = resolve({"source": "chain_walker", "finding": cw}, repo_path)
        f = r.raw_finding
        chain = f.get("chain", "auth")
        missing = f.get("missing", "")
        rule_id = f"{str(chain).lower()}-{missing.lower().replace(' ', '-')}"
        fp = r.abs_path or (
            os.path.normpath(os.path.join(repo_path, r.rel_path)) if r.rel_path else repo_path
        )
        out.append({
            "rule_id":     rule_id,
            "file_path":   fp,
            "line_number": r.line or 0,
            "message":     f.get("issue", ""),
            "_repo_root":  repo_path,
        })
    for f in state.get("semgrep_findings") or []:
        r = resolve({"source": "semgrep", "finding": f}, repo_path)
        raw_f = r.raw_finding
        if not raw_f.get("path") and not r.rel_path:
            continue
        cid = raw_f.get("check_id") or ""
        rid = cid.split(".")[-1] if cid else ""
        msg = (raw_f.get("extra") or {}).get("message", "")
        if isinstance(msg, str) and "\n" in msg:
            msg = msg.split("\n")[0]
        fp = r.abs_path or (
            os.path.normpath(os.path.join(repo_path, r.rel_path)) if r.rel_path else ""
        )
        if not fp:
            continue
        out.append({
            "rule_id":     rid,
            "file_path":   fp,
            "line_number": r.line or 0,
            "message":     msg,
            "_repo_root":  repo_path,
        })
    for sc in state.get("schema_findings") or []:
        if sc.get("found", True):
            continue
        r = resolve({"source": "schema", "finding": sc}, repo_path)
        msg = (sc.get("fix_hint") or sc.get("check") or "schema finding").strip()
        fp = r.abs_path or ""
        if not fp or not os.path.isfile(fp):
            fp = _first_sql_file()
        if not fp:
            continue
        out.append({
            "rule_id":     (sc.get("check") or "schema-finding").replace(":", "-"),
            "file_path":   fp,
            "line_number": r.line or 1,
            "message":     msg,
            "_repo_root":  repo_path,
        })
    if not out and state.get("db_match"):
        db_match = state.get("db_match") or {}
        fp = _first_sql_file()
        if not fp:
            for candidate in (
                os.path.join(repo_path, "middleware.ts"),
                os.path.join(repo_path, "src", "middleware.ts"),
                os.path.join(repo_path, "package.json"),
            ):
                if os.path.isfile(candidate):
                    fp = candidate
                    break
        if fp:
            synthetic = {
                "chain": db_match.get("category", "OTHER"),
                "broken_at": "detected via brain.db pattern match",
                "missing": (db_match.get("pattern", "") or "")[:60],
                "issue": db_match.get("pattern", ""),
                "confidence": 0.74,
            }
            out.append({
                "rule_id":     f"db-{str(db_match.get('category', 'other')).lower()}",
                "file_path":   fp,
                "line_number": 1,
                "message":     synthetic.get("issue") or "db pattern match",
                "_repo_root":  repo_path,
            })
    return out


# ── Rich display helpers ──────────────────────────────────────────────────────

def _print_finding_block(root_cause: str, category: str, conf_label: str,
                          conf_float: float, db_match, files: list) -> None:
    conf_color = _CONF_COLOR.get(conf_label, "white")
    cat_color  = _CAT_COLOR.get(category, "white")
    uses       = db_match.get("uses", 0) if db_match else 0
    if uses and conf_label != "LOW":
        conf_note = f"(matched {uses}× in brain.db)"
    else:
        conf_note = f"({conf_float:.0%})"

    console.print("")

    g = Table.grid(padding=(0, 2))
    g.add_column(width=16, style="bold dim")
    g.add_column()
    g.add_row("ROOT CAUSE:", Text(root_cause, style="bold white"))
    g.add_row("CATEGORY:",   Text(category,   style=f"bold {cat_color}"))
    g.add_row("CONFIDENCE:", Text(f"{conf_label}  {conf_note}", style=f"bold {conf_color}"))

    if files:
        first = files[0]
        ls    = f":{first['line']}" if first.get("line") else ""
        ftext = Text(f"{first['path']}{ls}", style="cyan")
        for f in files[1:]:
            ls2 = f":{f['line']}" if f.get("line") else ""
            ftext.append(f"\n{f['path']}{ls2}", style="cyan")
        g.add_row("FILES:", ftext)

    console.print(g)
    console.print("")


def _print_shadow_block(plan, repo_path: str, manual_changes: list = None) -> None:
    manual_changes = manual_changes or []
    candidates: list = []
    if plan and plan.proposals:
        candidates = [
            p for p in plan.proposals
            if not p.preview_only and p.proposed_content is not None
        ]

    if not candidates and not manual_changes:
        console.print(Text("  Shadow — no changes would be applied", style="dim yellow"))
        return

    console.print("")
    console.print(Text("WOULD APPLY (shadow — no files modified):", style="bold yellow"))
    console.print("─" * 57)
    for p in candidates:
        rel   = os.path.relpath(p.file_path, repo_path) if os.path.isabs(p.file_path) else p.file_path
        rules = ", ".join(p.rules[:2]) if getattr(p, "rules", None) else "fix"
        t = Text()
        t.append(f"{rel:<32}", style="cyan")
        t.append(f"  {rules[:40]}", style="dim yellow")
        console.print(t)
    for m in manual_changes:
        t = Text()
        t.append(f"{m['path']:<32}", style="cyan")
        t.append(f"  {m.get('desc', 'manual fix')[:40]}", style="dim yellow")
        console.print(t)
    console.print("─" * 57)
    total = len(candidates) + len(manual_changes)
    console.print(Text(f"  {total} fix(es) would be applied", style="yellow"))
    console.print("")


_MIDDLEWARE_CANONICAL_IMPORT = """\
import {{ type NextRequest }} from 'next/server'
import {{ updateSession }} from '{src}'

export async function middleware(request: NextRequest) {{
  return await updateSession(request)
}}

export const config = {{
  matcher: [
    '/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)',
  ],
}}
"""

# Used when no separate lib/supabase/middleware.ts exists — inline the session refresh
_MIDDLEWARE_CANONICAL_INLINE = """\
import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'

export async function middleware(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request })
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() { return request.cookies.getAll() },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value))
          supabaseResponse = NextResponse.next({ request })
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options))
        },
      },
    }
  )
  await supabase.auth.getUser()
  return supabaseResponse
}

export const config = {
  matcher: [
    '/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)',
  ],
}
"""


def _resolve_update_session_source(repo_path: str) -> str | None:
    """
    Find where updateSession is exported in this project.
    Returns @/ import path if found, None if updateSession must be inlined.

    Two explicit layouts:
      src/ variant  →  src/lib/supabase/middleware.ts  (tsconfig: @/* → src/*)
      root variant  →  lib/supabase/middleware.ts      (tsconfig: @/* → ./*)
    Both map to the same @/lib/supabase/middleware import path.
    Also checks session.ts — some Rocket projects use that name instead.
    """
    import glob as _glob

    # ── src/ layout: src/lib/supabase/{middleware,session}.ts ────────────────
    for name in ("middleware.ts", "session.ts"):
        if os.path.exists(os.path.join(repo_path, "src", "lib", "supabase", name)):
            return f"@/lib/supabase/{name[:-3]}"   # strip .ts

    # ── root layout: lib/supabase/{middleware,session}.ts ────────────────────
    for name in ("middleware.ts", "session.ts"):
        if os.path.exists(os.path.join(repo_path, "lib", "supabase", name)):
            return f"@/lib/supabase/{name[:-3]}"

    # ── Fallback: grep any .ts that exports updateSession ────────────────────
    for ts_file in _glob.glob(os.path.join(repo_path, "**/*.ts"), recursive=True):
        if "node_modules" in ts_file or ts_file.endswith("middleware.ts"):
            continue
        try:
            with open(ts_file, "r", encoding="utf-8", errors="replace") as fh:
                content = fh.read()
            if "export" in content and "updateSession" in content:
                rel        = os.path.relpath(ts_file, repo_path)
                rel_no_ext = rel.rsplit(".", 1)[0]
                # Normalise: src/lib/… → lib/… so @/ path is consistent
                if rel_no_ext.startswith("src/"):
                    rel_no_ext = rel_no_ext[4:]
                return f"@/{rel_no_ext}"
        except Exception:
            continue

    return None  # nothing found — caller must use inline pattern


def _rewrite_middleware_body(content: str, new_body: str) -> str:
    """
    Replace the body of the `middleware` async function using brace counting.
    Returns original content if function not found.
    """
    m = re.search(r'export\s+async\s+function\s+middleware\s*\(', content)
    if not m:
        return content
    brace_start = content.find('{', m.end())
    if brace_start == -1:
        return content
    depth = 1
    i = brace_start + 1
    while i < len(content) and depth > 0:
        if content[i] == '{':
            depth += 1
        elif content[i] == '}':
            depth -= 1
        i += 1
    brace_end = i - 1
    return content[:brace_start + 1] + "\n  " + new_body + "\n" + content[brace_end:]


def _invoke_claude_manual_fixes(
    state: dict,
    repo_path: str,
    hint: str,
    shadow: bool = False,
) -> list:
    """
    For MANUAL chain_walker findings (middleware missing updateSession), apply
    the fix directly in Python — no subprocess, no LLM, no extra files created.

    Strategy:
      - If a lib helper (src/lib/supabase/middleware.ts or lib/supabase/middleware.ts)
        exists: add the import and replace the function body surgically.
      - Otherwise: replace the entire file with the inline canonical template.

    When shadow=True, no files are written; returns the planned changes only.

    Returns list of {"path", "line", "desc"} for each (planned or applied) file.
    """
    manual = [
        s for s in (state.get("findings_scored") or [])
        if s.get("fix_mode") == "MANUAL" and s.get("source") == "chain_walker"
    ]
    if not manual:
        return []

    update_session_src = _resolve_update_session_source(repo_path)
    applied: list = []

    for entry in manual:
        r = resolve(entry, repo_path)
        rel = r.rel_path or ""
        if not rel:
            continue
        abs_path = r.abs_path or os.path.normpath(os.path.join(repo_path, rel))

        if shadow:
            desc = (
                f"updateSession from {update_session_src}"
                if update_session_src else "updateSession inlined"
            )
            applied.append({"path": rel, "line": "", "desc": desc})
            continue

        _REAL_STDOUT.write(f"\n  \033[1;36m→ fix:\033[0m  {rel}")
        _REAL_STDOUT.flush()

        try:
            if update_session_src:
                # Lib helper exists — add import + replace function body only
                with open(abs_path, "r", encoding="utf-8", errors="replace") as fh:
                    content = fh.read()

                # Add import if missing
                import_line = f"import {{ updateSession }} from '{update_session_src}'"
                if "updateSession" not in content:
                    # Insert after the last existing import line
                    lines = content.splitlines(keepends=True)
                    last_import = max(
                        (i for i, ln in enumerate(lines) if ln.strip().startswith("import ")),
                        default=-1,
                    )
                    if last_import >= 0:
                        lines.insert(last_import + 1, import_line + "\n")
                    else:
                        lines.insert(0, import_line + "\n")
                    content = "".join(lines)

                # Replace middleware function body
                content = _rewrite_middleware_body(
                    content, "return await updateSession(request)"
                )
                desc = f"updateSession from {update_session_src}"
            else:
                # No lib helper — replace entire file with inline canonical form
                content = _MIDDLEWARE_CANONICAL_INLINE
                desc = "updateSession inlined"

            import tempfile as _tempfile
            _d = os.path.dirname(os.path.abspath(abs_path))
            _fd, _tmp = _tempfile.mkstemp(prefix=".rkt_", suffix=".tmp", dir=_d)
            try:
                with os.fdopen(_fd, "w", encoding="utf-8") as _w:
                    _w.write(content)
                os.replace(_tmp, abs_path)
            except BaseException:
                try:
                    os.unlink(_tmp)
                except OSError:
                    pass
                raise

            _REAL_STDOUT.write("  \033[0;32m✓\033[0m\n")
            applied.append({"path": rel, "line": "", "desc": desc})

        except Exception as exc:
            _REAL_STDOUT.write(f"  \033[0;31m✗\033[0m  {str(exc)[:50]}\n")

        _REAL_STDOUT.flush()

    return applied


def _diff_first_hunk_line(diff: str) -> str:
    for line in (diff or "").splitlines():
        m = re.match(r"@@ -(\d+)", line)
        if m:
            return m.group(1)
    return ""


def _diff_description(diff: str) -> str:
    for line in (diff or "").splitlines():
        if line.startswith("+") and not line.startswith("+++") and line[1:].strip():
            return line[1:].strip()[:50]
    for line in (diff or "").splitlines():
        if line.startswith("-") and not line.startswith("---") and line[1:].strip():
            return line[1:].strip()[:50]
    return "modified"


def _flat_first_line(s: str, n: int = 30) -> tuple:
    """
    Return (first_line_truncated_to_n_chars, extra_line_count).
    Use to safely render multi-line strings in single-row table panels.
    """
    if not s:
        return "", 0
    lines = s.splitlines() or [""]
    first = lines[0].strip()[:n]
    extra = max(0, len(lines) - 1)
    return first, extra


def _print_agent_changes_panel(agent_result, repo_path: str, extra_manual: list = None) -> None:
    """Rich panel for AgentResult changes. Shows old→new per line."""
    extra_manual = extra_manual or []
    changes = agent_result.changes_applied
    if not changes and not extra_manual:
        return

    sep = "─" * 57
    console.print(Text("CHANGES APPLIED:", style="bold white"))
    console.print(sep)

    seen_files: set = set()
    for c in changes:
        rel  = c.get("file", "")
        line = c.get("line", "")
        old_text, _          = _flat_first_line(c.get("old"))
        new_text, new_extra  = _flat_first_line(c.get("new"))
        seen_files.add(rel)

        t = Text()
        t.append(f"{rel:<32}", style="cyan")
        ln_str = f"line {line:<5}" if line else " " * 10
        t.append(f"  {ln_str}  ", style="dim")
        if old_text and new_text:
            suffix = f" (+{new_extra} more)" if new_extra else ""
            t.append(f"{old_text} → {new_text}{suffix}", style="white")
        elif new_text:
            suffix = f" (+{new_extra} more)" if new_extra else ""
            t.append(f"{new_text}{suffix}", style="white")
        console.print(t)

    for m in extra_manual:
        rel = m.get("path", "")
        seen_files.add(rel)
        t = Text()
        t.append(f"{rel:<32}", style="cyan")
        t.append(f"  {' ' * 10}  ", style="dim")
        t.append(m.get("desc", "manual fix")[:40], style="white")
        console.print(t)

    console.print(sep)
    n = len(seen_files)
    path_label = ""
    if agent_result.path_used == "brain_db_diff":
        path_label = "  ·  brain.db diff"
    elif agent_result.tokens_used:
        path_label = f"  ·  {agent_result.tokens_used:,} tokens"
    console.print(Text(
        f"  {n} file{'s' if n != 1 else ''} changed{path_label} · review in Cursor · then: rocket push",
        style="bold",
    ))
    console.print("")


def _print_shadow_agent_changes(
    agent_result,
    repo_path: str,
    extra_manual: list = None,
) -> None:
    """Shadow-mode variant of the agent changes panel."""
    extra_manual = extra_manual or []
    changes = agent_result.changes_applied
    if not changes and not extra_manual:
        console.print(Text("  Shadow — no changes would be applied", style="dim yellow"))
        return

    console.print("")
    console.print(Text("WOULD APPLY (shadow — no files modified):", style="bold yellow"))
    sep = "─" * 57
    console.print(sep)
    for c in changes:
        rel  = c.get("file", "")
        line = c.get("line", "")
        old_text, _         = _flat_first_line(c.get("old"))
        new_text, new_extra = _flat_first_line(c.get("new"))
        t = Text()
        t.append(f"{rel:<32}", style="cyan")
        ln_str = f"line {line:<5}" if line else " " * 10
        t.append(f"  {ln_str}  ", style="dim yellow")
        if old_text and new_text:
            suffix = f" (+{new_extra} more)" if new_extra else ""
            t.append(f"{old_text} → {new_text}{suffix}", style="dim yellow")
        elif new_text:
            suffix = f" (+{new_extra} more)" if new_extra else ""
            t.append(f"{new_text}{suffix}", style="dim yellow")
        console.print(t)
    for m in extra_manual:
        t = Text()
        t.append(f"{m['path']:<32}", style="cyan")
        t.append(f"  {' ' * 10}  ", style="dim yellow")
        t.append(m.get("desc", "manual fix")[:40], style="dim yellow")
        console.print(t)
    console.print(sep)

    path_label = "brain.db" if agent_result.path_used == "brain_db_diff" else \
                 f"Claude API · {agent_result.tokens_used:,} tokens"
    total = len(changes) + len(extra_manual)
    console.print(Text(
        f"  {total} change(s) would be applied · {path_label}",
        style="yellow",
    ))
    console.print("")


def _print_changes_panel(fr, plan, repo_path: str, extra: list = None) -> None:
    extra = extra or []

    # Map rel paths to descriptions from fix_writer proposals
    desc_map = {}
    if plan and hasattr(plan, "proposals"):
        for p in plan.proposals:
            rel  = os.path.relpath(p.file_path, repo_path) if os.path.isabs(p.file_path) else p.file_path
            diff = getattr(p, "proposed_diff", "") or ""
            line = _diff_first_hunk_line(diff)
            desc = _diff_description(diff)
            if getattr(p, "rules", None):
                desc = p.rules[0][:50]
            desc_map[rel] = (line, desc)

    changes = []
    seen = set()
    for fp in (fr.files_modified if fr else []):
        rel  = os.path.relpath(fp, repo_path) if os.path.isabs(fp) else fp
        line, desc = desc_map.get(rel, ("", "modified"))
        changes.append((rel, line, desc))
        seen.add(rel)

    # Append Claude-applied fixes (deduped)
    for item in extra:
        rel = item["path"]
        if rel not in seen:
            changes.append((rel, item.get("line", ""), item.get("desc", "claude fix")))
            seen.add(rel)

    if not changes:
        return

    sep = "─" * 57
    console.print(Text("CHANGES APPLIED:", style="bold white"))
    console.print(sep)
    for rel, line, desc in changes:
        t = Text()
        t.append(f"{rel:<28}", style="cyan")
        ln_str = f"line {line:<5}" if line else " " * 10
        t.append(f"  {ln_str}  ", style="dim")
        t.append(desc[:38], style="white")
        console.print(t)
    console.print(sep)
    n = len(changes)
    console.print(Text(
        f"  {n} file{'s' if n != 1 else ''} changed · review in Cursor · then: rocket push",
        style="bold",
    ))
    console.print("")


# ── Non-blocking fix write-back ───────────────────────────────────────────────

def _log_writeback_warning(msg: str) -> None:
    _REAL_STDOUT.write(f"\n\033[1;33m⚠\033[0m  write-back failed: {msg[:120]}\n")
    _REAL_STDOUT.flush()


def _minimal_unified_diff_from_changes(changes: list) -> str:
    chunks = []
    for c in changes or []:
        rel = c.get("file", "")
        if not rel:
            continue
        line = int(c.get("line") or 1)
        old = (c.get("old") or "").replace("\n", " ")
        new = (c.get("new") or "").replace("\n", " ")
        chunks.append(
            "\n".join(
                [
                    f"--- a/{rel}",
                    f"+++ b/{rel}",
                    f"@@ -{line},1 +{line},1 @@",
                    f"-{old}",
                    f"+{new}",
                ]
            )
        )
    return "\n".join(chunks)


def _pattern_from_scored(state: dict) -> str:
    scored = state.get("findings_scored") or []
    if not scored:
        return ""
    top = scored[0]
    src = top.get("source", "")
    f = top.get("finding", {})
    if src == "chain_walker":
        return (f.get("issue") or f.get("missing") or "").strip()
    if src in ("semgrep", "probe"):
        return ((f.get("extra") or {}).get("message") or f.get("check_id") or "").strip()
    if src == "schema":
        return (f.get("fix_hint") or f.get("check") or "").strip()
    return (f.get("message") or "").strip()


def _spawn_save_fix_writeback(
    *,
    pattern: str,
    error_signature: str,
    category: str,
    fix_diff: str,
    project_type: str,
) -> None:
    def _worker() -> None:
        try:
            import db
            db.save_fix(
                pattern=pattern,
                error_signature=error_signature,
                category=category,
                fix_diff=fix_diff,
                project_type=project_type,
                verified=0,
            )
        except Exception as exc:
            _log_writeback_warning(str(exc))

    try:
        threading.Thread(target=_worker, daemon=True).start()
    except Exception as exc:
        _log_writeback_warning(str(exc))


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="rkt-diagnose engine runner (steps 2–4)")
    ap.add_argument("--repo-path",    required=True)
    ap.add_argument("--hint",         default="")
    ap.add_argument("--thread",       default="")
    ap.add_argument("--project-name", default="")
    ap.add_argument("--shadow",       action="store_true")
    ap.add_argument("--out-file",     default="")
    args = ap.parse_args()

    repo_path    = os.path.abspath(args.repo_path)
    hint         = args.hint
    shadow       = args.shadow
    out_file     = args.out_file
    trace_logger = _tracer.init_if_env()

    result = {"fixes_applied": False, "files_changed": 0, "confidence": "LOW",
              "root_cause": "", "error": None}

    # ── [2/4] Run engine ──────────────────────────────────────────────────────
    _step_start(2, 4, "running engine")

    try:
        import triage_graph
        import fix_writer as fw

        with _quiet():
            state = triage_graph.run_triage(repo_path, hint)

    except Exception as exc:
        _step_fail(str(exc)[:70])
        result["error"] = str(exc)
        _write_result(out_file, result)
        if trace_logger:
            trace_logger.print_summary()
        return 2

    overall_conf = state.get("overall_confidence", 0.0)
    conf_label   = _conf_label(overall_conf)
    category     = state.get("primary_category", "OTHER")
    db_match     = state.get("db_match")
    root_cause   = _root_cause(state)
    files        = _files_for_display(state, repo_path)

    _step_done()
    _print_finding_block(root_cause, category, conf_label, overall_conf, db_match, files)

    result["confidence"]  = conf_label
    result["root_cause"]  = root_cause

    # Build fix plan (quiet — fix_writer may print)
    with _quiet():
        raw      = _normalized_findings(state, repo_path)
        findings = fw.dedupe_findings(raw)
        plan     = fw.plan_fixes(findings, db_match=db_match, kb_hits=None)
    normalized_findings = findings

    candidates = [
        p for p in (plan.proposals or [])
        if not p.preview_only and p.proposed_content is not None
    ]

    # ── [3/4] Fix ─────────────────────────────────────────────────────────────
    _step_start(3, 4, "fixing")

    fr = None
    all_claude_changes: list = []
    agent_result = None
    loop_result = None
    shadow_manual_preview: list = []

    if shadow:
        # MANUAL middleware preview is always read-only — compute first
        with _quiet():
            shadow_manual_preview = _invoke_claude_manual_fixes(
                state, repo_path, hint, shadow=True
            )

        # Try run_fix_loop (agent + retry), fall back to fix_writer preview
        try:
            from agent_loop import run_fix_loop
            loop_result = run_fix_loop(
                findings=normalized_findings,
                repo_path=repo_path,
                db_match=db_match,
                hint=hint,
                shadow=True,
                max_attempts=3,
            )
            agent_result = loop_result.final_result
            if agent_result.success:
                n = len(agent_result.changes_applied) + len(shadow_manual_preview)
                path_label = "brain.db" if agent_result.path_used == "brain_db_diff" \
                             else f"Claude API · {agent_result.tokens_used:,} tokens"
                _step_warn(f"shadow — {n} change(s) would apply · {path_label}")
            else:
                total = len(candidates) + len(shadow_manual_preview)
                _step_warn(f"shadow — {total} fix(es) would apply")
                agent_result = None
        except Exception as _exc:
            agent_result = None
            total = len(candidates) + len(shadow_manual_preview)
            _step_warn(f"shadow — {total} fix(es) would apply")

        if agent_result is None:
            _print_shadow_block(plan, repo_path, manual_changes=shadow_manual_preview)

    elif overall_conf < 0.60:
        _step_warn(f"LOW confidence ({overall_conf:.0%}) — investigate in Cursor")

    elif state.get("fix_mode") == "MANUAL":
        manual_changes = _invoke_claude_manual_fixes(state, repo_path, hint)
        all_claude_changes.extend(manual_changes)
        if manual_changes:
            result["fixes_applied"] = True
            result["files_changed"] = len(manual_changes)
            _step_done(f"{len(manual_changes)} fix(es) applied · deterministic")
        else:
            _step_warn("MANUAL mode — check middleware.ts manually")

    else:
        # Try run_fix_loop (agent + retry)
        _agent_success     = False
        _agent_fail_reason = ""
        try:
            from agent_loop import run_fix_loop
            loop_result = run_fix_loop(
                findings=normalized_findings,
                repo_path=repo_path,
                db_match=db_match,
                hint=hint,
                shadow=False,
                max_attempts=3,
            )
            agent_result = loop_result.final_result
            if agent_result.success:
                _agent_success = True
                n = len(agent_result.changes_applied)
                if agent_result.path_used == "brain_db_diff":
                    path_label = "brain.db"
                else:
                    path_label = f"Claude API · {agent_result.tokens_used:,} tokens"
                detail = f"{n} change{'s' if n != 1 else ''} · {path_label}"
                if overall_conf < 0.85:
                    _step_warn(f"MED confidence — review carefully · {detail}")
                else:
                    _step_done(detail)
                if loop_result and loop_result.attempts > 1:
                    _REAL_STDOUT.write(f"      Fixed on attempt {loop_result.attempts}/3\n")
                    _REAL_STDOUT.flush()
                result["fixes_applied"] = True
                result["files_changed"] = len({c["file"] for c in agent_result.changes_applied})

                # Best-effort non-blocking write-back for successful AUTO patch.
                scored = state.get("findings_scored") or []
                pattern = (agent_result.root_cause or "").strip()
                if scored and pattern:
                    if agent_result.path_used == "brain_db_diff":
                        fix_diff = (db_match or {}).get("fix_diff", "") or ""
                    else:
                        fix_diff = _minimal_unified_diff_from_changes(
                            agent_result.changes_applied
                        )
                    if fix_diff:
                        _spawn_save_fix_writeback(
                            pattern=pattern,
                            error_signature=(hint or pattern).strip(),
                            category=state.get("primary_category", "OTHER"),
                            fix_diff=fix_diff,
                            project_type=(state.get("fingerprint") or {}).get("project_type", "Other"),
                        )
            else:
                # ClaudeAgent failed — note why and fall through to fix_writer
                loop_error = loop_result.error if loop_result else ""
                _agent_fail_reason = loop_error or agent_result.error or ""
        except Exception as _exc:
            agent_result = None
            _agent_fail_reason = str(_exc)[:60]

        if not _agent_success:
            # Fallback: fix_writer (regex) + pure Python middleware fix
            agent_note = f" · agent: {_agent_fail_reason[:40]}" if _agent_fail_reason else ""

            if not candidates:
                manual_changes = _invoke_claude_manual_fixes(state, repo_path, hint)
                all_claude_changes.extend(manual_changes)
                if manual_changes:
                    result["fixes_applied"] = True
                    result["files_changed"] = len(manual_changes)
                    _step_done(f"{len(manual_changes)} fix(es) applied{agent_note}")
                else:
                    _step_done(f"no auto-applicable fixes{agent_note}")
            else:
                try:
                    selected = {p.file_path for p in candidates}
                    with _quiet():
                        fr = fw.apply_fix_plan(plan, selected_paths=selected, write_changes=True)

                    n_fixes = fr.fixes_applied
                    n_files = len(fr.files_modified)
                    detail  = f"{n_fixes} fix{'es' if n_fixes != 1 else ''} · {n_files} file{'s' if n_files != 1 else ''}{agent_note}"

                    if overall_conf < 0.85:
                        _step_warn(f"MED confidence — review carefully · {detail}")
                    else:
                        _step_done(detail)

                    result["fixes_applied"] = n_files > 0
                    result["files_changed"] = n_files

                    manual_changes = _invoke_claude_manual_fixes(state, repo_path, hint)
                    all_claude_changes.extend(manual_changes)

                    # Best-effort non-blocking write-back for successful fallback apply.
                    scored = state.get("findings_scored") or []
                    if scored and n_files > 0:
                        if plan and getattr(plan, "proposals", None):
                            first = plan.proposals[0]
                            rules = getattr(first, "rules", None) or []
                            pattern = (rules[0] if rules else "").strip()
                        else:
                            pattern = ""
                        if not pattern:
                            pattern = _pattern_from_scored(state)
                        fix_diff = "\n".join(
                            d for d in (fr.diffs.values() if fr and fr.diffs else []) if d
                        )
                        if pattern and fix_diff:
                            _spawn_save_fix_writeback(
                                pattern=pattern,
                                error_signature=(hint or pattern).strip(),
                                category=state.get("primary_category", "OTHER"),
                                fix_diff=fix_diff,
                                project_type=(state.get("fingerprint") or {}).get("project_type", "Other"),
                            )

                except Exception as exc:
                    _step_fail(str(exc)[:70])

    # ── [4/4] Validate ────────────────────────────────────────────────────────
    _step_start(4, 4, "validating")

    if not shadow and loop_result and agent_result and agent_result.success:
        if loop_result.validation_passed:
            _step_done("oxc clean · tsc clean · chain_walker clean")
        else:
            _step_warn("validation failed")
            if loop_result.tsc_errors:
                if any("TS" in e or "Error:" in e for e in loop_result.tsc_errors):
                    _REAL_STDOUT.write("      ⚠ tsc errors — review in Cursor\n")
                else:
                    _REAL_STDOUT.write("      ⚠ oxc errors — review in Cursor\n")
                for err in loop_result.tsc_errors[:3]:
                    _REAL_STDOUT.write(f"      - {err}\n")
            if loop_result.chain_errors:
                _REAL_STDOUT.write("      ⚠ violations persist — review in Cursor\n")
            _REAL_STDOUT.flush()
    else:
        try:
            import chain_walker as cw_mod

            with _quiet():
                with _tracer.trace("PHASE8", "chain_walker:rescan") as trace_token:
                    new_findings = cw_mod.walk(repo_path)
                    trace_token.set_output(f"findings={len(new_findings)}")

            orig_issues = {
                (f.get("chain"), f.get("missing"))
                for f in (state.get("cw_findings") or [])
            }
            remaining = [
                f for f in new_findings
                if (f.get("chain"), f.get("missing")) in orig_issues
            ]

            if not orig_issues or not remaining:
                _step_done("chain_walker clean")
            else:
                summary = "; ".join(f.get("issue", "")[:35] for f in remaining[:2])
                _step_warn(f"still found: {summary[:65]}")

        except Exception as exc:
            _step_warn(f"validation error: {str(exc)[:50]}")

    # ── CHANGES APPLIED ───────────────────────────────────────────────────────
    console.print("")
    if shadow and agent_result and agent_result.success:
        _print_shadow_agent_changes(agent_result, repo_path, extra_manual=shadow_manual_preview)
    elif shadow and agent_result is None:
        pass  # already printed by _print_shadow_block above
    elif not shadow and agent_result and agent_result.success:
        _print_agent_changes_panel(agent_result, repo_path, extra_manual=all_claude_changes)
    elif not shadow and (fr or all_claude_changes):
        _print_changes_panel(fr, plan, repo_path, extra=all_claude_changes)
    elif not shadow and not fr and not all_claude_changes and overall_conf >= 0.60:
        console.print(Text("  No applicable fixes found — investigate in Cursor", style="dim"))
        console.print("")
    elif not shadow and overall_conf < 0.60:
        console.print(Text(
            "  LOW confidence — open Cursor and investigate manually",
            style="dim yellow",
        ))
        console.print("")

    _write_result(out_file, result)
    if trace_logger:
        trace_logger.print_summary()
    return 0


def _write_result(out_file: str, result: dict) -> None:
    if not out_file:
        return
    parent = os.path.dirname(out_file)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(out_file, "w") as f:
        json.dump(result, f)


if __name__ == "__main__":
    sys.exit(main())
