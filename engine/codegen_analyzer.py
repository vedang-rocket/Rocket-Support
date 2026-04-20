"""
Graph-backed violation discovery using the Codegen graph-sitter Codebase.

Requires the `graph-sitter` PyPI package (import name `graph_sitter`) and Python 3.12–3.13
(wheels are not published for 3.14+). The project path must lie inside a git work tree.

Output matches Semgrep JSON `results[]` entries so `fix_writer.apply_fixes` and
`rkt_smart._build_normalized_findings` can consume results unchanged.
"""

from __future__ import annotations

import os
import sys
from collections import deque
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from graph_sitter import Codebase as _CodegenCodebase  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    _CodegenCodebase = None  # type: ignore

SUPABASE_JS_MODULE = "@supabase/supabase-js"
# Align with engine/rules/supabase-wrong-import.yml server paths
_SERVER_SUFFIXES: Tuple[str, ...] = (
    "server.ts",
    "server.tsx",
    "actions.ts",
    "actions.tsx",
)

_SEMGREP_CHECK_ID = "rules.supabase-wrong-import.supabase-js-in-server-file"
_SEMGREP_MESSAGE = (
    "In server components, route handlers, and Server Actions: use createServerClient from @supabase/ssr, "
    "not createClient from @supabase/supabase-js. The browser client doesn't handle "
    "the cookie-based auth session required in server context."
)


def _inside_git_worktree(path: str) -> bool:
    cur = os.path.abspath(path)
    while True:
        if os.path.isdir(os.path.join(cur, ".git")):
            return True
        parent = os.path.dirname(cur)
        if parent == cur:
            return False
        cur = parent


def _is_server_context_file(relative_posix: str) -> bool:
    """
    True if path matches the Semgrep server-file scope:
    - **/app/**/route.ts[x]
    - **/app/**/page.ts[x]
    - **/app/**/layout.tsx
    - lib/supabase/**, utils/supabase/**
    - explicit server.ts[x], actions.ts[x]
    """
    p = relative_posix.replace("\\", "/").lstrip("./")
    pl = p.lower()
    for suf in _SERVER_SUFFIXES:
        if pl.endswith(suf.lower()) or f"/{suf.lower()}" in f"/{pl}":
            return True
    if "/app/" in f"/{pl}":
        if pl.endswith("/route.ts") or pl.endswith("/route.tsx"):
            return True
        if pl.endswith("/page.ts") or pl.endswith("/page.tsx"):
            return True
        if pl.endswith("/layout.tsx"):
            return True
    if pl.startswith("lib/supabase/") or "/lib/supabase/" in f"/{pl}":
        return True
    if pl.startswith("utils/supabase/") or "/utils/supabase/" in f"/{pl}":
        return True
    return False


def _norm_module_string(imp: Any) -> str:
    mod = getattr(imp, "module", None)
    if mod is None:
        return ""
    return (getattr(mod, "source", "") or "").strip()


def _import_resolves_to_supabase_js(imp: Any) -> bool:
    rs = getattr(imp, "resolved_symbol", None)
    if rs is not None and type(rs).__name__ == "ExternalModule":
        src = (getattr(rs, "source", "") or "").strip().strip("`\"'")
        if src == SUPABASE_JS_MODULE:
            return True
        if src.endswith("@supabase/supabase-js"):
            return True
    mod_s = _norm_module_string(imp)
    return SUPABASE_JS_MODULE in mod_s.replace('"', "'")


def _import_start_line(imp: Any) -> int:
    ist = getattr(imp, "import_statement", None)
    if ist is None:
        return 1
    for attr in ("lineno", "line_number", "line"):
        v = getattr(ist, attr, None)
        if isinstance(v, int) and v >= 1:
            return v
    sp = getattr(ist, "span", None) or getattr(imp, "span", None)
    if sp is not None:
        start = getattr(sp, "start_point", None)
        if start is not None:
            row = getattr(start, "row", None)
            if isinstance(row, int):
                return row + 1
    return 1


def _to_semgrep_result(project_root: str, abs_file: str, line: int) -> Dict[str, Any]:
    try:
        rel = os.path.relpath(abs_file, project_root)
    except ValueError:
        rel = abs_file
    rel = rel.replace("\\", "/")
    col = 1
    return {
        "check_id": _SEMGREP_CHECK_ID,
        "path": rel,
        "start": {"line": line, "col": col},
        "end": {"line": line, "col": col},
        "extra": {
            "message": _SEMGREP_MESSAGE,
            "lines": "",
        },
    }


def _external_module_is_supabase_js(em: Any) -> bool:
    if type(em).__name__ != "ExternalModule":
        return False
    src = (getattr(em, "source", "") or "").strip().strip("`\"'")
    if src == SUPABASE_JS_MODULE:
        return True
    fn = getattr(em, "full_name", None)
    if fn and SUPABASE_JS_MODULE in str(fn):
        return True
    return False


def _safe_symbol_usages(node: Any) -> List[Any]:
    fn = getattr(node, "symbol_usages", None)
    if not callable(fn):
        return []
    try:
        out = fn()
    except TypeError:
        try:
            out = fn(None)
        except Exception:
            return []
    except Exception:
        return []
    return list(out or [])


def _graph_collect_supabase_imports(codebase: Any) -> List[Any]:
    """
    Traverse the resolved import graph starting at ExternalModule('@supabase/supabase-js').

    Uses BFS over graph edges from ``symbol_usages()`` (pre-computed in Codebase) instead of
    walking the filesystem. Cycles are guarded with a global ``visited`` set on ``id(node)``.
    """
    hits: List[Any] = []
    visited: Set[int] = set()
    queue: deque[Any] = deque()

    for em in getattr(codebase, "external_modules", []) or []:
        if _external_module_is_supabase_js(em):
            queue.append(em)

    while queue:
        node = queue.popleft()
        nid = id(node)
        if nid in visited:
            continue
        visited.add(nid)
        cls = type(node).__name__

        if cls == "Import" and _import_resolves_to_supabase_js(node):
            hits.append(node)

        for sym in _safe_symbol_usages(node):
            if type(sym).__name__ not in ("Import", "ExternalModule"):
                continue
            if type(sym).__name__ == "ExternalModule" and not _external_module_is_supabase_js(sym):
                continue
            sid = id(sym)
            if sid not in visited:
                queue.append(sym)

    return hits


def _fallback_import_scan(codebase: Any) -> List[Any]:
    """Single-hop over Codebase.imports (graph index), no directory walk."""
    out: List[Any] = []
    seen: Set[int] = set()
    for imp in getattr(codebase, "imports", []) or []:
        if not _import_resolves_to_supabase_js(imp):
            continue
        iid = id(imp)
        if iid in seen:
            continue
        seen.add(iid)
        out.append(imp)
    return out


class CodegenAnalyzer:
    """Thin wrapper around graph-sitter ``Codebase`` (Codegen local graph engine)."""

    def __init__(self, project_path: str) -> None:
        self.project_path = os.path.abspath(os.path.expanduser(project_path))
        self._codebase: Any = None
        self._init_error: Optional[str] = None

        if _CodegenCodebase is None:
            self._init_error = (
                "graph_sitter not installed. Install with: "
                "pip install 'graph-sitter>=0.56.2,<0.57' (Python 3.12–3.13 required for wheels)."
            )
            return
        if not _inside_git_worktree(self.project_path):
            self._init_error = (
                "Codebase() requires a git work tree (.git in this directory or a parent)."
            )
            return
        try:
            self._codebase = _CodegenCodebase(self.project_path)
        except Exception as e:  # pragma: no cover - parse / env errors
            self._init_error = str(e)
            self._codebase = None

    @property
    def available(self) -> bool:
        return self._codebase is not None

    @property
    def init_error(self) -> Optional[str]:
        return self._init_error

    def find_violations(self) -> List[Dict[str, Any]]:
        """
        Return Semgrep-shaped dicts for ``supabase-js-in-server-file`` using graph queries.

        Discovery order:
        1) BFS from ``ExternalModule`` node(s) for ``@supabase/supabase-js`` via ``symbol_usages``.
        2) If that yields no imports, fall back to the indexed ``codebase.imports`` list
           (still graph-backed, not filesystem walk).
        """
        if self._codebase is None:
            if self._init_error:
                sys.stderr.write(f"[codegen_analyzer] {self._init_error}\n")
            return []

        imps = _graph_collect_supabase_imports(self._codebase)
        if not imps:
            imps = _fallback_import_scan(self._codebase)

        findings: List[Dict[str, Any]] = []
        seen_files: Set[Tuple[str, int]] = set()
        for imp in imps:
            fp = getattr(imp, "filepath", None) or getattr(getattr(imp, "file", None), "filepath", "")
            if not fp:
                continue
            abs_file = os.path.normpath(fp if os.path.isabs(fp) else os.path.join(self.project_path, fp))
            try:
                rel = os.path.relpath(abs_file, self.project_path).replace("\\", "/")
            except ValueError:
                rel = fp.replace("\\", "/")
            if not _is_server_context_file(rel):
                continue
            line = _import_start_line(imp)
            key = (abs_file, line)
            if key in seen_files:
                continue
            seen_files.add(key)
            findings.append(_to_semgrep_result(self.project_path, abs_file, line))

        return findings


def find_violations(project_path: str) -> List[Dict[str, Any]]:
    """Functional shortcut: parse once and return Semgrep-shaped results."""
    return CodegenAnalyzer(project_path).find_violations()
