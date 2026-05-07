"""
slicer.py — tree-sitter surgical extraction of auth/stripe-touching functions.

Replaces whole-file reads in build_claude_prompt() with focused 8-40 line slices,
reducing per-ticket token cost from ~3000-8000 to ~400-700 tokens.

Usage:
    from slicer import slice_file
    slices = slice_file("/path/to/file.ts", keywords=["getUser", "createServerClient"])
    # returns [{function_name, start_line, end_line, source}, ...]
"""
import os
from typing import Any, Dict, List, Optional

# Reuse the parser already loaded in fix_writer to avoid double loading
_TS_PARSER = None
_TS_LANG = None

AUTH_KEYWORDS = {
    "getUser", "getSession", "createServerClient", "createBrowserClient",
    "createRouteHandlerClient", "updateSession", "supabase.auth",
    "auth.uid", "auth.users",
}
STRIPE_KEYWORDS = {
    "constructEvent", "stripe.webhooks", "request.text", "request.json",
    "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET",
}
RLS_KEYWORDS = {
    "enable row level security", "row level security", "rls",
}

ALL_KEYWORDS = AUTH_KEYWORDS | STRIPE_KEYWORDS


def _get_parser():
    global _TS_PARSER, _TS_LANG
    if _TS_PARSER is not None:
        return _TS_PARSER, _TS_LANG
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from fix_writer import _TS_PARSER as P, _TS_LANG as L
        _TS_PARSER, _TS_LANG = P, L
        return P, L
    except Exception:
        return None, None


def _node_text(node, source: bytes) -> str:
    return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")


def _find_function_nodes(root_node, source: bytes) -> List[Any]:
    """Walk tree and collect all function/arrow function nodes."""
    results = []
    cursor = root_node.walk()

    def visit(node):
        if node.type in (
            "function_declaration", "function_expression",
            "arrow_function", "method_definition",
            "export_statement",
        ):
            results.append(node)
        for child in node.children:
            visit(child)

    visit(root_node)
    return results


def slice_file(
    file_path: str,
    keywords: Optional[List[str]] = None,
    max_lines: int = 40,
) -> List[Dict[str, Any]]:
    """
    Extract functions from file_path that contain any of the keywords.

    Returns list of dicts:
        {file, function_name, start_line, end_line, source, keywords_found}

    Falls back to returning the full file content in one slice if tree-sitter
    is unavailable or parsing fails.
    """
    if keywords is None:
        keywords = list(ALL_KEYWORDS)

    try:
        with open(file_path, encoding="utf-8", errors="replace") as fh:
            content = fh.read()
    except OSError:
        return []

    kw_lower = [k.lower() for k in keywords]
    content_lower = content.lower()

    # Fast pre-check: does this file mention any keyword at all?
    if not any(kw in content_lower for kw in kw_lower):
        return []

    parser, lang = _get_parser()
    if parser is None:
        # Fallback: return whole file as one slice
        lines = content.splitlines()
        return [{
            "file": file_path,
            "function_name": os.path.basename(file_path),
            "start_line": 1,
            "end_line": len(lines),
            "source": content[:4000],
            "keywords_found": [k for k in keywords if k.lower() in content_lower],
        }]

    try:
        source_bytes = content.encode("utf-8")
        tree = parser.parse(source_bytes)
        fn_nodes = _find_function_nodes(tree.root_node, source_bytes)

        slices = []
        for node in fn_nodes:
            fn_text = _node_text(node, source_bytes)
            fn_lower = fn_text.lower()

            matched_kws = [k for k in keywords if k.lower() in fn_lower]
            if not matched_kws:
                continue

            start_line = node.start_point[0] + 1
            end_line   = node.end_point[0] + 1
            line_count = end_line - start_line + 1

            if line_count > max_lines:
                # Trim to first max_lines
                fn_lines = fn_text.splitlines()
                fn_text = "\n".join(fn_lines[:max_lines]) + f"\n  // ... ({line_count - max_lines} lines truncated)"
                end_line = start_line + max_lines - 1

            # Try to get function name
            fn_name = "anonymous"
            for child in node.children:
                if child.type == "identifier":
                    fn_name = _node_text(child, source_bytes)
                    break

            slices.append({
                "file": file_path,
                "function_name": fn_name,
                "start_line": start_line,
                "end_line": end_line,
                "source": fn_text,
                "keywords_found": matched_kws,
            })

        return slices
    except Exception:
        # Fallback on parse error
        lines = content.splitlines()
        return [{
            "file": file_path,
            "function_name": os.path.basename(file_path),
            "start_line": 1,
            "end_line": min(len(lines), max_lines),
            "source": "\n".join(lines[:max_lines]),
            "keywords_found": [k for k in keywords if k.lower() in content_lower],
        }]


def slice_repo(
    repo_path: str,
    keywords: Optional[List[str]] = None,
    max_files: int = 10,
) -> List[Dict[str, Any]]:
    """
    Walk repo and extract keyword-touching function slices from .ts/.tsx files.
    Returns up to max_files worth of slices.
    """
    if keywords is None:
        keywords = list(ALL_KEYWORDS)

    SKIP_DIRS = {"node_modules", ".next", ".git", "__pycache__", "dist", ".turbo"}
    all_slices: List[Dict[str, Any]] = []
    files_with_hits = 0

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fname in files:
            if not (fname.endswith(".ts") or fname.endswith(".tsx")):
                continue
            fpath = os.path.join(root, fname)
            slices = slice_file(fpath, keywords=keywords)
            if slices:
                all_slices.extend(slices)
                files_with_hits += 1
                if files_with_hits >= max_files:
                    return all_slices

    return all_slices


def format_slices_for_prompt(slices: List[Dict[str, Any]], repo_path: str = "") -> str:
    """Format slices as a compact context block for Claude prompts."""
    if not slices:
        return ""
    parts = []
    for s in slices:
        rel = os.path.relpath(s["file"], repo_path) if repo_path else s["file"]
        parts.append(
            f"// {rel}:{s['start_line']}-{s['end_line']}  [{', '.join(s['keywords_found'])}]\n"
            f"{s['source']}"
        )
    return "\n\n".join(parts)
