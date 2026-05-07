"""
fix_validator.py — oxc lint gate after fix_writer generates a diff.

Applies the diff to a temp copy of the file → runs oxc → returns errors.
If oxc not found, returns [] (non-blocking).

Usage in triage_graph:
    from fix_validator import validate_fix_plan
    errors = validate_fix_plan(fix_plan, repo_path)
    if errors:
        # retry fix_writer with errors as extra context
"""
import os
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List, Optional


def _oxc_available() -> bool:
    return shutil.which("oxlint") is not None or shutil.which("oxc") is not None


def _run_oxc(file_path: str) -> List[str]:
    """Run oxlint on a single file. Returns list of error strings."""
    cmd = shutil.which("oxlint") or shutil.which("oxc")
    if cmd is None:
        return []
    try:
        result = subprocess.run(
            [cmd, file_path],
            capture_output=True, text=True, timeout=10
        )
        errors = []
        for line in (result.stdout + result.stderr).splitlines():
            line = line.strip()
            if line and ("error" in line.lower() or "warning" in line.lower()):
                errors.append(line)
        return errors
    except Exception:
        return []


def _apply_unified_diff(original: str, diff: str) -> Optional[str]:
    """Apply a unified diff to original content. Returns patched content or None."""
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ts", delete=False) as orig_f:
            orig_f.write(original)
            orig_path = orig_f.name

        with tempfile.NamedTemporaryFile(mode="w", suffix=".patch", delete=False) as patch_f:
            patch_f.write(diff)
            patch_path = patch_f.name

        result = subprocess.run(
            ["patch", "--quiet", orig_path, patch_path],
            capture_output=True, timeout=10
        )
        if result.returncode == 0:
            with open(orig_path) as f:
                patched = f.read()
            return patched
        return None
    except Exception:
        return None
    finally:
        try:
            os.unlink(orig_path)
            os.unlink(patch_path)
        except Exception:
            pass


def validate_fix_plan(
    fix_plan: Any,
    repo_path: str,
) -> List[Dict[str, Any]]:
    """
    Apply fix_plan diffs to temp files, run oxlint on each.
    Returns list of {file, errors} dicts. Empty list = all valid.

    fix_plan must have .proposals attribute (list of FileProposal objects with
    .path and .new_content or .diff attributes).
    """
    if not _oxc_available():
        return []

    validation_errors = []
    proposals = getattr(fix_plan, "proposals", []) or []

    for proposal in proposals:
        file_path = getattr(proposal, "path", None)
        if not file_path:
            continue
        if not (file_path.endswith(".ts") or file_path.endswith(".tsx")):
            continue

        abs_path = os.path.join(repo_path, file_path) if not os.path.isabs(file_path) else file_path

        # Get the patched content
        new_content = getattr(proposal, "new_content", None)
        diff = getattr(proposal, "diff", None)

        if new_content:
            content_to_validate = new_content
        elif diff:
            try:
                with open(abs_path) as f:
                    original = f.read()
                content_to_validate = _apply_unified_diff(original, diff)
                if content_to_validate is None:
                    continue
            except OSError:
                continue
        else:
            continue

        # Write to temp file and lint
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".ts", delete=False, dir="/tmp"
        ) as tmp:
            tmp.write(content_to_validate)
            tmp_path = tmp.name

        try:
            errors = _run_oxc(tmp_path)
            if errors:
                validation_errors.append({"file": file_path, "errors": errors})
        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    return validation_errors


def validation_errors_to_context(errors: List[Dict[str, Any]]) -> str:
    """Format validation errors as context string for fix_writer retry."""
    if not errors:
        return ""
    lines = ["oxlint validation failed — fix these issues:"]
    for item in errors:
        lines.append(f"\n{item['file']}:")
        for err in item["errors"][:5]:
            lines.append(f"  {err}")
    return "\n".join(lines)
