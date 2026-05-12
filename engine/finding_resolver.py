"""
finding_resolver.py — Single place to turn triage findings into {file, line} locations.

Handles scored-entry shapes from chain_walker, probe, semgrep, schema, and fs_checks.
"""

from __future__ import annotations

import glob as glob_module
import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import chain_walker
from context_filter import _CATEGORY_FILE_HINTS
from dedup import _category

_ENV_LINE_RE = re.compile(r"^([^\s:]+):(\d+)\b")


@dataclass(frozen=True)
class ResolvedLocation:
    abs_path: Optional[str]
    rel_path: Optional[str]
    line: Optional[int]
    source: str
    kind: str
    exists: bool
    raw_finding: Dict[str, Any]


def _unwrap_entry(entry: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    inner = entry.get("finding")
    if isinstance(inner, dict):
        return (entry.get("source") or "", inner)
    return ("", entry)


def _infer_source(f: Dict[str, Any]) -> str:
    if f.get("chain") or f.get("broken_at"):
        return "chain_walker"
    if "check" in f and "found" in f and "file" in f:
        return "schema"
    if f.get("rule") and f.get("message") is not None and not f.get("path"):
        return "fs_checks"
    if f.get("check_id") and f.get("path"):
        return "semgrep"
    if f.get("path") and f.get("start"):
        return "semgrep"
    return "unknown"


def _file_kind(abs_path: Optional[str], rel_path: Optional[str]) -> str:
    path = abs_path or rel_path or ""
    lower = path.lower()
    if lower.endswith("/") or path.endswith(os.sep):
        return "directory"
    if "/migrations/" in lower.replace("\\", "/") and lower.endswith(".sql"):
        return "sql"
    base = os.path.basename(path)
    if base.startswith(".env"):
        return "env"
    if any(lower.endswith(ext) for ext in (".ts", ".tsx", ".js", ".jsx")):
        return "code"
    if lower.endswith(".sql"):
        return "sql"
    if lower.endswith((".json", ".yaml", ".yml", ".toml", ".md")):
        return "config"
    return "config"


def _norm_line(val: Any) -> Optional[int]:
    if val is None:
        return None
    try:
        n = int(val)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _rel_for(repo_path: str, abs_path: str) -> str:
    try:
        return os.path.relpath(abs_path, repo_path)
    except ValueError:
        return abs_path


def _chain_walker_line_from_missing(abs_path: str, missing: str) -> Optional[int]:
    if not missing or not abs_path or not os.path.isfile(abs_path):
        return None
    try:
        with open(abs_path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return None
    needle = missing.strip()
    if not needle:
        return None
    low_needle = needle.lower()
    for i, line in enumerate(lines, start=1):
        if needle in line:
            return i
        if low_needle in line.lower():
            return i
    return None


def _expand_chain_glob(repo_path: str, pattern: str) -> Optional[str]:
    full = os.path.join(repo_path, pattern)
    matches = sorted(glob_module.glob(full, recursive=True))
    for p in matches:
        if os.path.isfile(p):
            return p
    return None


def _resolve_chain_path(repo_path: str, broken_at: str) -> Tuple[Optional[str], Optional[str]]:
    if not broken_at:
        return None, None
    if "*" in broken_at:
        abs_g = _expand_chain_glob(repo_path, broken_at)
        if abs_g:
            return abs_g, _rel_for(repo_path, abs_g)
        return None, broken_at
    abs_p = os.path.normpath(os.path.join(repo_path, broken_at))
    if os.path.isfile(abs_p):
        return abs_p, _rel_for(repo_path, abs_p)
    return None, broken_at


def _resolve_probe_semgrep_path(repo_path: str, path: str) -> Tuple[Optional[str], Optional[str]]:
    if not path:
        return None, None
    if os.path.isabs(path):
        abs_p = os.path.normpath(path)
        if os.path.isfile(abs_p):
            return abs_p, _rel_for(repo_path, abs_p)
        return abs_p, _rel_for(repo_path, abs_p)
    abs_p = os.path.normpath(os.path.join(repo_path, path))
    return abs_p, _rel_for(repo_path, abs_p)


def _parse_fs_checks_message(message: str) -> Tuple[Optional[str], Optional[int]]:
    if not message:
        return None, None
    m = _ENV_LINE_RE.match(message.strip())
    if m:
        rel, line_s = m.group(1), m.group(2)
        try:
            return rel, int(line_s)
        except ValueError:
            return rel, None
    return None, None


def _hint_candidate_paths(repo_path: str, rel_hint: str, layout: Dict[str, str]) -> List[str]:
    """Try layout-aware paths then plain repo-relative fallbacks."""
    seen: set = set()
    out: List[str] = []

    def add(p: str) -> None:
        ap = os.path.normpath(p)
        if ap not in seen:
            seen.add(ap)
            out.append(ap)

    lib_dir = layout.get("lib_dir") or "lib"
    app_dir = layout.get("app_dir") or "app"

    if rel_hint.startswith("lib/"):
        suffix = rel_hint[len("lib/") :]
        add(os.path.join(repo_path, lib_dir, suffix))
    if rel_hint.startswith("app/"):
        suffix = rel_hint[len("app/") :]
        add(os.path.join(repo_path, app_dir, suffix))

    add(os.path.join(repo_path, rel_hint))
    add(os.path.join(repo_path, "src", rel_hint))
    return out


def resolve(entry: Dict[str, Any], repo_path: str) -> ResolvedLocation:
    """
    Resolve a findings_scored-style entry (or raw inner finding) to a single location.

    - chain_walker: expands glob in broken_at to first matching file.
    - probe / semgrep: path + start.line (line omitted if missing or <= 0).
    - schema: file is a migrations directory label — abs_path None, kind directory.
    - fs_checks: no file field — abs_path None; rel_path/line parsed from message when possible.
    """
    repo_path = os.path.abspath(os.path.expanduser(repo_path))
    src, f = _unwrap_entry(entry)
    if not src:
        src = _infer_source(f)

    if src == "chain_walker":
        broken = f.get("broken_at") or ""
        abs_p, rel_p = _resolve_chain_path(repo_path, broken)
        exists = bool(abs_p and os.path.isfile(abs_p))
        line = _chain_walker_line_from_missing(abs_p, f.get("missing") or "") if exists else None
        kind = _file_kind(abs_p, rel_p) if exists else ("directory" if "*" in broken else "config")
        return ResolvedLocation(
            abs_path=abs_p if exists else None,
            rel_path=rel_p,
            line=line,
            source=src,
            kind=kind,
            exists=exists,
            raw_finding=f,
        )

    if src in ("semgrep", "probe", "unknown") and f.get("path"):
        if src == "unknown":
            src = "semgrep"
        abs_p, rel_p = _resolve_probe_semgrep_path(repo_path, f.get("path") or "")
        start = f.get("start") or {}
        line = _norm_line(start.get("line"))
        exists = bool(abs_p and os.path.isfile(abs_p))
        kind = _file_kind(abs_p, rel_p)
        return ResolvedLocation(
            abs_path=abs_p if exists else None,
            rel_path=rel_p,
            line=line,
            source=src,
            kind=kind,
            exists=exists,
            raw_finding=f,
        )

    if src == "schema":
        rel_dir = (f.get("file") or "supabase/migrations/").rstrip("/") + "/"
        return ResolvedLocation(
            abs_path=None,
            rel_path=rel_dir,
            line=None,
            source=src,
            kind="directory",
            exists=False,
            raw_finding=f,
        )

    if src == "fs_checks":
        msg = f.get("message") or ""
        rel_hint, parsed_line = _parse_fs_checks_message(msg)
        rel_out = rel_hint
        abs_out: Optional[str] = None
        exists = False
        if rel_hint:
            cand = os.path.normpath(os.path.join(repo_path, rel_hint))
            if os.path.isfile(cand):
                abs_out = cand
                rel_out = _rel_for(repo_path, cand)
                exists = True
        return ResolvedLocation(
            abs_path=abs_out,
            rel_path=rel_out,
            line=parsed_line,
            source=src,
            kind=_file_kind(abs_out, rel_out),
            exists=exists,
            raw_finding=f,
        )

    return ResolvedLocation(
        abs_path=None,
        rel_path=None,
        line=None,
        source=src or "unknown",
        kind="config",
        exists=False,
        raw_finding=f,
    )


def resolve_companions(
    entry: Dict[str, Any],
    repo_path: str,
    max_files: int = 5,
) -> List[ResolvedLocation]:
    """
    Additional repo files to load for context (category hints + layout).

    Excludes the primary path returned by resolve() when it is a real file.
    """
    repo_path = os.path.abspath(os.path.expanduser(repo_path))
    primary = resolve(entry, repo_path)
    primary_abs = primary.abs_path if primary.exists else None

    wrapped = entry if "finding" in entry else {"finding": entry, "source": entry.get("source", "")}
    category = _category(wrapped)
    layout = chain_walker.detect_layout(repo_path)

    candidates: List[str] = []

    mw = layout.get("middleware")
    if mw:
        candidates.append(os.path.normpath(os.path.join(repo_path, mw)))

    for hint in _CATEGORY_FILE_HINTS.get(category, []):
        for p in _hint_candidate_paths(repo_path, hint, layout):
            if os.path.isfile(p):
                candidates.append(p)

    lib_dir = layout.get("lib_dir") or "lib"
    for extra in (
        os.path.join(repo_path, lib_dir, "supabase", "middleware.ts"),
        os.path.join(repo_path, lib_dir, "supabase", "session.ts"),
    ):
        ep = os.path.normpath(extra)
        if os.path.isfile(ep):
            candidates.append(ep)

    out: List[ResolvedLocation] = []
    seen: set = set()
    for abs_p in candidates:
        if abs_p in seen:
            continue
        seen.add(abs_p)
        if primary_abs and os.path.normpath(abs_p) == os.path.normpath(primary_abs):
            continue
        if not os.path.isfile(abs_p):
            continue
        rel = _rel_for(repo_path, abs_p)
        out.append(
            ResolvedLocation(
                abs_path=abs_p,
                rel_path=rel,
                line=None,
                source="companion",
                kind=_file_kind(abs_p, rel),
                exists=True,
                raw_finding={},
            )
        )
        if len(out) >= max_files:
            break

    return out
