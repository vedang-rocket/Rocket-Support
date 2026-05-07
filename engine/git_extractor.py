"""
git_extractor.py — scan Rocket project git histories for support fix patterns.

Looks for commits whose messages suggest a bug fix, checks out the state
BEFORE the commit (the broken state), runs chain_walker to extract the
symptom, then saves the diff + symptom as a brain.db pattern.

Usage:
    engine/.venv/bin/python engine/git_extractor.py [--repos-dir ~/Documents/Rocket] [--dry-run]

Target: extract 80-120 new patterns from real client history.
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Support-indicating keywords in commit messages
SUPPORT_KEYWORDS = [
    "fix:", "fix(", "bugfix", "hotfix", "support", "patch",
    "getSession", "getUser", "stripe", "webhook", "rls", "supabase",
    "auth", "middleware", "cookies", "headers", "revalidate",
    "404", "500", "403", "rls", "permission",
]

SKIP_DIRS = {"node_modules", ".next", ".git", "__pycache__", "dist", ".turbo"}


def _is_support_commit(msg: str) -> bool:
    msg_lower = msg.lower()
    return any(kw.lower() in msg_lower for kw in SUPPORT_KEYWORDS)


def _git(repo_path: str, *args) -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "-C", repo_path] + list(args),
            capture_output=True, text=True, timeout=30
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def _get_support_commits(repo_path: str) -> List[Tuple[str, str]]:
    """Return list of (sha, message) for commits that look like support fixes."""
    log = _git(repo_path, "log", "--oneline", "--no-merges", "-100")
    if not log:
        return []
    commits = []
    for line in log.splitlines():
        parts = line.split(" ", 1)
        if len(parts) == 2:
            sha, msg = parts
            if _is_support_commit(msg):
                commits.append((sha.strip(), msg.strip()))
    return commits


def _get_diff(repo_path: str, sha: str) -> str:
    diff = _git(repo_path, "show", "--stat", "--patch", sha)
    return diff or ""


def _checkout_before(repo_path: str, sha: str, dest_dir: str) -> bool:
    """Checkout the tree of SHA~1 (parent commit) into dest_dir."""
    parent = _git(repo_path, "rev-parse", f"{sha}^")
    if not parent:
        return False
    # Use git archive to extract without modifying the working tree
    result = subprocess.run(
        ["git", "-C", repo_path, "archive", parent, "--format=tar"],
        capture_output=True, timeout=60
    )
    if result.returncode != 0:
        return False
    extract = subprocess.run(
        ["tar", "-x", "-C", dest_dir],
        input=result.stdout, capture_output=True, timeout=30
    )
    return extract.returncode == 0


def _detect_category(diff: str, msg: str) -> str:
    text = (diff + " " + msg).lower()
    if any(kw in text for kw in ["getuser", "getsession", "supabase.auth", "middleware", "cookies", "headers"]):
        return "AUTH"
    if any(kw in text for kw in ["stripe", "webhook", "constructevent", "request.text"]):
        return "STRIPE"
    if any(kw in text for kw in ["rls", "row level security", "policy", "pgrst"]):
        return "RLS"
    if any(kw in text for kw in [".env", "service_role", "anon_key", "stripe_webhook"]):
        return "ENV"
    if any(kw in text for kw in ["build", "tsc", "error", "type", "import", "export"]):
        return "BUILD"
    return "OTHER"


def _extract_symptom_from_chain(repo_path: str) -> str:
    """Run chain_walker on the extracted repo state."""
    try:
        import chain_walker
        findings = chain_walker.walk(repo_path)
        if findings:
            return " | ".join(f.get("issue", "") for f in findings[:2])
    except Exception:
        pass
    return ""


def extract_patterns(
    repos_dir: str,
    dry_run: bool = False,
    max_per_repo: int = 20,
) -> List[Dict[str, Any]]:
    """
    Scan all git repos in repos_dir for support commits.
    Returns list of pattern dicts (also saves to brain.db unless dry_run).
    """
    repos_dir = os.path.expanduser(repos_dir)
    if not os.path.isdir(repos_dir):
        print(f"Repos dir not found: {repos_dir}")
        return []

    import db
    db.init_db()

    all_patterns = []
    repos = [
        os.path.join(repos_dir, d) for d in os.listdir(repos_dir)
        if os.path.isdir(os.path.join(repos_dir, d, ".git"))
    ]
    print(f"Found {len(repos)} git repos in {repos_dir}")

    for repo_path in repos:
        repo_name = os.path.basename(repo_path)
        commits = _get_support_commits(repo_path)
        print(f"  {repo_name}: {len(commits)} support commits")

        extracted = 0
        for sha, msg in commits[:max_per_repo]:
            diff = _get_diff(repo_path, sha)
            if not diff or len(diff) < 30:
                continue

            category = _detect_category(diff, msg)
            symptom = ""

            # Try to extract symptom by checking out the broken state
            with tempfile.TemporaryDirectory() as tmpdir:
                if _checkout_before(repo_path, sha, tmpdir):
                    symptom = _extract_symptom_from_chain(tmpdir)

            if not symptom:
                symptom = msg

            # Build pattern
            error_sig = f"{repo_name} | {msg[:80]}"
            pattern = {
                "pattern": f"{msg[:120]}",
                "error_signature": error_sig,
                "category": category,
                "fix_diff": diff[:2000],
                "verified": 0,
            }
            all_patterns.append(pattern)

            if not dry_run:
                fix_id = db.save_fix(
                    pattern=pattern["pattern"],
                    error_signature=pattern["error_signature"],
                    category=pattern["category"],
                    fix_diff=pattern["fix_diff"],
                    verified=0,
                )
                print(f"    Saved: {fix_id[:8]}... [{category}] {msg[:50]}")

            extracted += 1

        if extracted > 0:
            print(f"  → {extracted} patterns extracted from {repo_name}")

    print(f"\nTotal: {len(all_patterns)} patterns extracted")
    return all_patterns


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract fix patterns from git history")
    parser.add_argument("--repos-dir", default="~/Documents/Rocket", help="Directory containing git repos")
    parser.add_argument("--dry-run", action="store_true", help="Don't save to brain.db")
    parser.add_argument("--max-per-repo", type=int, default=20, help="Max commits per repo")
    args = parser.parse_args()

    patterns = extract_patterns(args.repos_dir, dry_run=args.dry_run, max_per_repo=args.max_per_repo)
    if args.dry_run:
        print(json.dumps(patterns[:3], indent=2))
