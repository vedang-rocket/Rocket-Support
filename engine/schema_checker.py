"""
schema_checker.py — Pure-Python SQL migration auditor.

Reads supabase/migrations/*.sql in chronological order and checks
for required patterns. No API calls, no external deps.

Returns [] immediately for non-Supabase projects (no migrations dir).
"""
import glob
import os
import re
from typing import Dict, List


# ── Required patterns ────────────────────────────────────────────────────────

CHECKS = [
    {
        "check":     "trigger:on_auth_user_created",
        "needle":    "on_auth_user_created",
        "found_ok":  True,   # found=True is good
        "fix_hint":  (
            "Profile trigger missing — add handle_new_user() function + "
            "on_auth_user_created trigger (see CLAUDE.md profile trigger template)"
        ),
    },
    {
        "check":    "rls:enable_row_level_security",
        "needle":   "enable row level security",
        "found_ok": True,
        "fix_hint": (
            "RLS not enabled on any table — "
            "add: ALTER TABLE <table> ENABLE ROW LEVEL SECURITY;"
        ),
    },
    {
        "check":    "foreign_key:on_delete_cascade",
        "needle":   "on delete cascade",
        "found_ok": True,
        "fix_hint": (
            "No ON DELETE CASCADE found — foreign keys referencing auth.users "
            "should use ON DELETE CASCADE to avoid orphaned rows"
        ),
    },
    # TIMESTAMPTZ check is handled separately (regex, not plain string)
]

# Matches TIMESTAMP not followed by WITH TIME ZONE or TZ (case-insensitive)
_BARE_TIMESTAMP_RE = re.compile(
    r"\btimestamp\b(?!\s*with\s+time\s+zone)(?!tz)", re.IGNORECASE
)


def check(repo_path: str) -> List[Dict]:
    """Audit supabase/migrations/*.sql for required patterns.

    Args:
        repo_path: Absolute path to the project root.

    Returns:
        List of {check, found, file, fix_hint} dicts.
        found=True  → pattern present (good).
        found=False → pattern missing (issue).
        Returns [] if no migrations directory exists.
    """
    migrations_dir = os.path.join(os.path.expanduser(repo_path), "supabase", "migrations")
    if not os.path.isdir(migrations_dir):
        return []

    sql_files = sorted(glob.glob(os.path.join(migrations_dir, "*.sql")))
    if not sql_files:
        return []

    # Concatenate all migrations (lowercase for case-insensitive checks)
    combined = ""
    for path in sql_files:
        try:
            with open(path, "r", errors="replace") as fh:
                combined += fh.read() + "\n"
        except (IOError, OSError):
            pass

    combined_lower = combined.lower()
    rel_dir = "supabase/migrations/"
    results: List[Dict] = []

    # ── String-based checks ──────────────────────────────────────────────────
    for spec in CHECKS:
        found = spec["needle"] in combined_lower
        results.append({
            "check":    spec["check"],
            "found":    found,
            "file":     rel_dir,
            "fix_hint": "" if found else spec["fix_hint"],
        })

    # ── TIMESTAMPTZ check (regex) ─────────────────────────────────────────────
    # found=True means NO bare TIMESTAMP (good).
    has_bare = bool(_BARE_TIMESTAMP_RE.search(combined))
    results.append({
        "check":    "schema:timestamptz",
        "found":    not has_bare,
        "file":     rel_dir,
        "fix_hint": (
            "" if not has_bare else
            "Bare TIMESTAMP columns found — replace with TIMESTAMPTZ "
            "to avoid timezone-related booking/scheduling bugs"
        ),
    })

    return results


def failures(results: List[Dict]) -> List[Dict]:
    """Filter to only the failing checks (found=False)."""
    return [r for r in results if not r["found"]]
