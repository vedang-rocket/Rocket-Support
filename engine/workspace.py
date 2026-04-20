"""
workspace.py — Manages per-project workspaces for the rkt support engine.

Lifecycle:
  create_workspace(zip_path, issue_description)
    → unzip → flatten → snapshot → .rkt_meta.json

  compute_diff(workspace_path)
    → compare current files vs .rkt_snapshot/ → unified diffs

  get_active_workspace() → most recent .rkt_meta.json
  list_workspaces()      → all workspaces newest first
  get_port(workspace_path) → int from package.json dev script
"""

import os
import json
import re
import shutil
import zipfile
import difflib
import datetime
from typing import Dict, Any, List, Optional

# ── Constants ─────────────────────────────────────────────────────────────────

WORKSPACE_BASE = os.path.expanduser("~/rocket-support/workspace")

SNAPSHOT_DIR   = ".rkt_snapshot"
META_FILE      = ".rkt_meta.json"

TRACKED_EXTS   = {".ts", ".tsx", ".js", ".jsx", ".sql", ".env", ".json", ".css"}

SKIP_DIRS      = {"node_modules", ".next", ".git", SNAPSHOT_DIR, "__pycache__"}

_PORT_RE       = re.compile(r"(?:^|\s)-p\s+(\d+)|--port[=\s]+(\d+)")

DEFAULT_PORT   = 3000


# ── Internal helpers ──────────────────────────────────────────────────────────

def _is_skipped(path: str) -> bool:
    """Return True if any path component is in SKIP_DIRS."""
    parts = set(path.replace("\\", "/").split("/"))
    return bool(parts & SKIP_DIRS)


def _tracked_files(root: str) -> List[str]:
    """Walk root and return relative paths of tracked-extension files."""
    result = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Prune skip dirs in-place so os.walk doesn't descend into them
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            if fname == META_FILE:
                continue  # never track the meta file itself
            if os.path.splitext(fname)[1] in TRACKED_EXTS:
                abs_path = os.path.join(dirpath, fname)
                rel = os.path.relpath(abs_path, root)
                result.append(rel)
    return sorted(result)


def _read_text(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


# ── Public API ────────────────────────────────────────────────────────────────

def get_port(workspace_path: str) -> int:
    """
    Read port from package.json dev script.
    Looks for -p NNNN or --port NNNN.
    Returns DEFAULT_PORT (3000) if not found.
    """
    pkg = os.path.join(workspace_path, "package.json")
    if not os.path.isfile(pkg):
        return DEFAULT_PORT
    try:
        data = json.loads(_read_text(pkg))
        dev_script = data.get("scripts", {}).get("dev", "")
        m = _PORT_RE.search(dev_script)
        if m:
            port_str = m.group(1) or m.group(2)
            return int(port_str)
    except (json.JSONDecodeError, ValueError):
        pass
    return DEFAULT_PORT


def create_workspace(zip_path: str, issue_description: str) -> Dict[str, Any]:
    """
    Unzip project, set up Rocket folder structure, snapshot source files.

    Steps:
      1. Unzip to WORKSPACE_BASE/<projectname>_YYYYMMDD_HHMMSS/ (temp)
      2. Hoist if single top-level subfolder
      3. Build ~/Documents/Rocket/<project>/old/ and fixed/
         - old/<project>.zip  — copy of original zip
         - old/<project>/     — extracted original
         - fixed/<project>/   — working copy (this becomes workspace_path)
      4. Detect port from package.json
      5. Snapshot all tracked files → fixed/<project>/.rkt_snapshot/
      6. Write .rkt_meta.json to fixed/<project>/ and a tracking stub to temp dir
      7. Return meta dict
    """
    os.makedirs(WORKSPACE_BASE, exist_ok=True)

    zip_path = os.path.abspath(os.path.expanduser(zip_path))
    project_name   = os.path.splitext(os.path.basename(zip_path))[0]
    timestamp      = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    workspace_name = f"{project_name}_{timestamp}"
    temp_path      = os.path.join(WORKSPACE_BASE, workspace_name)

    # 1. Unzip into temp dir
    os.makedirs(temp_path, exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(temp_path)

    # 2. Hoist if single subfolder was extracted
    entries = [e for e in os.listdir(temp_path) if not e.startswith(".")]
    if len(entries) == 1:
        inner = os.path.join(temp_path, entries[0])
        if os.path.isdir(inner):
            for item in os.listdir(inner):
                shutil.move(os.path.join(inner, item), temp_path)
            os.rmdir(inner)

    # 3. Build Rocket folder structure
    rocket_base       = os.path.expanduser(f"~/Documents/Rocket/{project_name}")
    old_dir           = os.path.join(rocket_base, "old")
    fixed_dir         = os.path.join(rocket_base, "fixed")
    old_project_dir   = os.path.join(old_dir,   project_name)
    fixed_project_dir = os.path.join(fixed_dir, project_name)

    os.makedirs(old_dir,   exist_ok=True)
    os.makedirs(fixed_dir, exist_ok=True)

    # old/ — copy of original zip
    shutil.copy2(zip_path, os.path.join(old_dir, f"{project_name}.zip"))

    # old/ — extracted original snapshot
    if os.path.exists(old_project_dir):
        shutil.rmtree(old_project_dir)
    shutil.copytree(temp_path, old_project_dir)

    # fixed/ — working copy (this is where all editing happens)
    if os.path.exists(fixed_project_dir):
        shutil.rmtree(fixed_project_dir)
    shutil.copytree(temp_path, fixed_project_dir)

    # Actual workspace is the fixed copy
    workspace_path = fixed_project_dir

    # 4. Detect port
    port = get_port(workspace_path)

    # 5. Snapshot tracked files in the fixed working copy
    snapshot_path = os.path.join(workspace_path, SNAPSHOT_DIR)
    os.makedirs(snapshot_path, exist_ok=True)

    for rel in _tracked_files(workspace_path):
        src  = os.path.join(workspace_path, rel)
        dest = os.path.join(snapshot_path, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(src, dest)

    # 5b. Hide rkt internals from Cursor sidebar via .gitignore
    gitignore_path = os.path.join(workspace_path, ".gitignore")
    snapshot_entry = (
        "\n# rkt internal\n"
        ".rkt_snapshot/\n"
        ".rkt_meta.json\n"
        ".rkt_handoff_prompt.md\n"
        "bun.lock\n"
        "ruvector.db\n"
    )
    try:
        with open(gitignore_path, "a") as f:
            f.write(snapshot_entry)
    except Exception:
        pass

    # 6. Write meta
    meta: Dict[str, Any] = {
        "workspace_name":    workspace_name,
        "workspace_path":    workspace_path,
        "snapshot_path":     snapshot_path,
        "zip_path":          zip_path,
        "issue_description": issue_description,
        "port":              port,
        "created_at":        datetime.datetime.utcnow().isoformat(),
        "status":            "triaging",
        "rocket_dir":        rocket_base,
        "project_name":      project_name,
    }

    # Write meta to the fixed working dir (read by deliverer and tools)
    meta_file = os.path.join(workspace_path, META_FILE)
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    # Write tracking stub to temp dir so list_workspaces() can find this session
    stub_file = os.path.join(temp_path, META_FILE)
    with open(stub_file, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    return meta


def compute_diff(workspace_path: str) -> Dict[str, str]:
    """
    Compare current tracked files against their .rkt_snapshot/ copies.

    Returns {relative_path: unified_diff_string} for:
      - files that have changed since snapshot
      - new files that did not exist in snapshot
    Files removed since snapshot are not included (nothing to diff against).
    """
    workspace_path = os.path.abspath(os.path.expanduser(workspace_path))
    snapshot_path  = os.path.join(workspace_path, SNAPSHOT_DIR)

    diffs: Dict[str, str] = {}

    for rel in _tracked_files(workspace_path):
        current_file  = os.path.join(workspace_path, rel)
        snapshot_file = os.path.join(snapshot_path,  rel)

        current_text  = _read_text(current_file).splitlines(keepends=True)

        if not os.path.isfile(snapshot_file):
            # New file — show entire content as addition
            diff_lines = list(difflib.unified_diff(
                [], current_text,
                fromfile=f"a/{rel}",
                tofile=f"b/{rel}",
            ))
        else:
            snapshot_text = _read_text(snapshot_file).splitlines(keepends=True)
            diff_lines = list(difflib.unified_diff(
                snapshot_text, current_text,
                fromfile=f"a/{rel}",
                tofile=f"b/{rel}",
            ))

        if diff_lines:
            diffs[rel] = "".join(diff_lines)

    return diffs


def get_active_workspace() -> Optional[Dict[str, Any]]:
    """
    Scan WORKSPACE_BASE subdirs for .rkt_meta.json.
    Return the most recently created one (by created_at field), or None.
    """
    metas = list_workspaces()
    return metas[0] if metas else None


def list_workspaces() -> List[Dict[str, Any]]:
    """
    Return all workspace metas found under WORKSPACE_BASE, sorted newest first.
    """
    if not os.path.isdir(WORKSPACE_BASE):
        return []

    metas: List[Dict[str, Any]] = []
    for entry in os.scandir(WORKSPACE_BASE):
        if not entry.is_dir():
            continue
        meta_file = os.path.join(entry.path, META_FILE)
        if os.path.isfile(meta_file):
            try:
                data = json.loads(_read_text(meta_file))
                metas.append(data)
            except json.JSONDecodeError:
                pass

    metas.sort(key=lambda m: m.get("created_at", ""), reverse=True)
    return metas
