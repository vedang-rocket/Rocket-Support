"""
deliverer.py — Final delivery step for rkt support workflow.

Lifecycle:
  deliver(workspace_path=None)
    1. Learn from diff → save any manual fixes to brain.db
    2. Cleanup → strip tooling artifacts from workspace
    3. Zip → compress fixed project to ~/Documents/Rocket/<project>/fixed/

Returns: {zip_path, zip_size_kb, files_learned, artifacts_removed}
"""

import os
import json
import shutil
import zipfile
import datetime
from typing import Any, Dict, List, Optional

import sys
ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ENGINE_DIR)

import workspace as ws_mod
import db as fix_db


def ask_outcome(fix_id: str) -> bool:
    """Prompt user to confirm fix worked; if yes, mark verified in brain.db."""
    if not sys.stdin.isatty():
        return False
    try:
        ans = input("\n[rkt] Did this fix work? [y/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    if ans in ("y", "yes"):
        conn = fix_db.get_conn()
        conn.execute(
            "UPDATE fixes SET verified = 1, uses = uses + 1 WHERE id = ?", (fix_id,)
        )
        conn.commit()
        conn.close()
        print("[rkt] Marked as verified in brain.db", flush=True)
        return True
    return False


# ── Cleanup targets ───────────────────────────────────────────────────────────

_CLEANUP_DIRS = {
    "node_modules", ".next", ".claude", ".cursor", ".swarm", ".claude-flow",
    "memory-bank", "graphify-out", "code-review-graph", ".code-review-graph",
    ".rkt_snapshot",
}

_CLEANUP_FILES = {
    "CLAUDE.md", "AGENTS.md", ".mcp.json", "the-rocket-guide.md",
    "TROUBLESHOOTING.md", ".rkt_meta.json", ".rkt_prompt.md",
    ".rkt_handoff_prompt.md", "bun.lock",
    "ruvector.db", "ruvector.db-shm", "ruvector.db-wal",
}

_CLEANUP_SUFFIXES = (".rkt_backup",)

# Dirs to skip when building the output zip (keep .git — included in all zips)
_ZIP_SKIP_DIRS = {"node_modules", ".next", "__pycache__"}


# ── Category inference ────────────────────────────────────────────────────────

def _infer_category(changed_files: List[str], issue_desc: str) -> str:
    """Infer fix category from changed filenames and issue description."""
    combined = " ".join(changed_files).lower() + " " + issue_desc.lower()

    if any(kw in combined for kw in ("stripe", "webhook", "payment")):
        return "STRIPE"
    if any(kw in combined for kw in ("auth", "login", "middleware")):
        return "AUTH"
    if any(kw in combined for kw in (".sql", "rls", "supabase", "migration")):
        return "SUPABASE"
    if any(kw in combined for kw in (".env", "env var", "environment")):
        return "ENV"
    if any(kw in combined for kw in ("build", "config", "next.config", "tsconfig")):
        return "BUILD"
    return "OTHER"


# ── Delivery ──────────────────────────────────────────────────────────────────

def deliver(workspace_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Run the full delivery pipeline for a workspace.

    Args:
        workspace_path: Absolute path to workspace dir.
                        If None, uses get_active_workspace().

    Returns:
        {zip_path, zip_size_kb, files_learned, artifacts_removed}
    """
    # ── Resolve workspace ─────────────────────────────────────────────────────
    if workspace_path is None:
        meta_record = ws_mod.get_active_workspace()
        if not meta_record:
            raise RuntimeError("No active workspace found. Pass workspace_path explicitly.")
        workspace_path = meta_record["workspace_path"]

    workspace_path = os.path.abspath(os.path.expanduser(workspace_path))

    # Load meta
    meta_file = os.path.join(workspace_path, ws_mod.META_FILE)
    meta: Dict[str, Any] = {}
    if os.path.isfile(meta_file):
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)
        except json.JSONDecodeError:
            pass

    issue_description = meta.get("issue_description", "unknown issue")
    workspace_name    = meta.get("workspace_name", os.path.basename(workspace_path))
    fp_result         = meta.get("fingerprint_result", {}) or {}
    project_type      = fp_result.get("project_type", "SaaS") if fp_result else "SaaS"

    files_learned    = 0
    artifacts_removed: List[str] = []

    # ── Step 1: Learn from diff ───────────────────────────────────────────────
    diffs = ws_mod.compute_diff(workspace_path)

    if diffs:
        changed_files = list(diffs.keys())
        category      = _infer_category(changed_files, issue_description)

        # Build combined diff string (first 5 files, max 2000 chars)
        combined_parts: List[str] = []
        char_budget = 2000
        for rel_path in changed_files[:5]:
            chunk = f"--- {rel_path} ---\n{diffs[rel_path]}"
            if len(chunk) > char_budget:
                chunk = chunk[:char_budget]
                char_budget = 0
            else:
                char_budget -= len(chunk)
            combined_parts.append(chunk)
            if char_budget <= 0:
                break
        combined_diff = "\n".join(combined_parts)

        pattern = f"Manual fix: {issue_description[:80]}"

        fix_id = fix_db.save_fix(
            pattern=pattern,
            error_signature=issue_description,
            category=category,
            fix_diff=combined_diff,
            project_type=project_type,
            verified=0,
        )
        files_learned = len(changed_files)

    # ── Step 2: Cleanup artifacts ─────────────────────────────────────────────
    for entry in os.scandir(workspace_path):
        if entry.is_dir(follow_symlinks=False):
            if entry.name in _CLEANUP_DIRS:
                shutil.rmtree(entry.path, ignore_errors=True)
                artifacts_removed.append(entry.name + "/")
        elif entry.is_file(follow_symlinks=False):
            if entry.name in _CLEANUP_FILES or entry.name.endswith(_CLEANUP_SUFFIXES):
                os.remove(entry.path)
                artifacts_removed.append(entry.name)

    # Also scan one level deep for nested cleanup targets (e.g. src/.next)
    for entry in os.scandir(workspace_path):
        if entry.is_dir(follow_symlinks=False) and entry.name not in _CLEANUP_DIRS:
            try:
                for sub in os.scandir(entry.path):
                    if sub.is_dir(follow_symlinks=False) and sub.name in _CLEANUP_DIRS:
                        shutil.rmtree(sub.path, ignore_errors=True)
                        artifacts_removed.append(f"{entry.name}/{sub.name}/")
            except PermissionError:
                pass

    # ── Step 3: Create zip inside fixed/ (sibling of working dir) ────────────
    # workspace_path = ~/Documents/Rocket/<project>/fixed/<project>/
    # zip goes to  → ~/Documents/Rocket/<project>/fixed/<project>_fixed.zip
    project_name = os.path.basename(workspace_path)
    fixed_dir    = os.path.dirname(workspace_path)
    zip_path     = os.path.join(fixed_dir, f"{project_name}_fixed.zip")

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for dirpath, dirnames, filenames in os.walk(workspace_path):
            dirnames[:] = [d for d in dirnames if d not in _ZIP_SKIP_DIRS]
            for fname in filenames:
                abs_path = os.path.join(dirpath, fname)
                arcname  = os.path.relpath(abs_path, workspace_path)
                try:
                    zf.write(abs_path, arcname)
                except (PermissionError, OSError):
                    pass

    zip_size_kb = round(os.path.getsize(zip_path) / 1024, 1)

    outcome_confirmed = False
    if diffs and files_learned:
        outcome_confirmed = ask_outcome(fix_id)

    return {
        "zip_path":           zip_path,
        "zip_size_kb":        zip_size_kb,
        "files_learned":      files_learned,
        "artifacts_removed":  artifacts_removed,
        "outcome_confirmed":  outcome_confirmed,
    }
