"""
chain_walker.py — Layer 0 fast chain checker.

Pure Python: no Claude calls, no subprocess. Completes in < 1 second.

Walks four dependency chains — AUTH, STRIPE, RLS, ENV.
ALL chains always run (no early exit).
Returns a list of all breaks found (one per chain, empty = all pass).

Precondition guards (chains only run when relevant):
  AUTH   → @supabase found in package.json
  STRIPE → stripe found in package.json
  RLS    → supabase/migrations/ directory exists
  ENV    → @supabase OR stripe found in package.json

File-missing policy (non-glob patterns):
  File not found → skip that chain entry silently (not a break).
  Chain walker checks for WRONG patterns in EXISTING files only.
"""

import os
import glob as _glob
from typing import Dict, Any, List, Optional, Tuple


# ── Layout detection ──────────────────────────────────────────────────────────

def detect_layout(repo_path: str) -> Dict[str, str]:
    """Return resolved paths for the three layout-dependent locations."""

    def e(rel: str) -> bool:
        return os.path.exists(os.path.join(repo_path, rel))

    app_dir = "src/app" if e("src/app") else "app"
    lib_dir = "src/lib" if e("src/lib") else "lib"

    if e("src/middleware.ts"):
        middleware = "src/middleware.ts"
    elif e("middleware.ts"):
        middleware = "middleware.ts"
    else:
        middleware = None

    return {
        "app_dir": app_dir,
        "lib_dir": lib_dir,
        "middleware": middleware,
    }


# ── File helpers ──────────────────────────────────────────────────────────────

def _read(path: str) -> Optional[str]:
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except Exception:
        return None


def _glob_read_all(pattern: str, repo_path: str) -> Optional[Tuple[str, str]]:
    """
    Expand a glob pattern rooted at repo_path.
    Returns (display_path, concatenated_content) of ALL matches, or None if no matches.
    """
    full_pattern = os.path.join(repo_path, pattern)
    matches = sorted(_glob.glob(full_pattern, recursive=True))
    if not matches:
        return None

    parts: List[str] = []
    for path in matches:
        content = _read(path)
        if content:
            parts.append(content)

    if not parts:
        return None

    display = os.path.relpath(matches[0], repo_path) if len(matches) == 1 else pattern
    return (display, "\n".join(parts))


def _read_pkg(repo_path: str) -> str:
    """Return package.json content as a string (empty string if not found)."""
    return _read(os.path.join(repo_path, "package.json")) or ""


def _first_missing(content: str, needles: List[str]) -> Optional[str]:
    """Return the first needle not found in content, or None if all present."""
    for needle in needles:
        if needle not in content and needle.lower() not in content.lower():
            return needle
    return None


# ── Chain definitions ─────────────────────────────────────────────────────────

# Each entry: (file_pattern, [required_strings], issue_message, fix_hint)
# Glob patterns (has *):  optional feature — skip chain entry if no files found
# Exact paths (no *):     check the file IF it exists; skip silently if missing

def build_chains(layout: Dict[str, str]) -> Dict[str, List[Tuple]]:
    app = layout["app_dir"]
    lib = layout["lib_dir"]
    mw  = layout["middleware"] or "middleware.ts"

    AUTH_CHAIN: List[Tuple] = [
        (
            mw,
            ["updateSession"],
            "middleware.ts missing updateSession() — cookies won't refresh, users get logged out unexpectedly",
            "Refactor middleware to call updateSession(request) from lib/supabase/middleware.ts — "
            "raw createServerClient in middleware skips the cookie-refresh path",
        ),
        (
            lib + "/supabase/server.ts",
            ["createServerClient"],
            "server.ts uses wrong Supabase client — not @supabase/ssr createServerClient",
            "Replace with: import { createServerClient } from '@supabase/ssr'",
        ),
        (
            app + "/auth/callback/route.ts",
            ["exchangeCodeForSession"],
            "auth callback route missing or lacks exchangeCodeForSession — OAuth PKCE flow broken",
            "Create " + app + "/auth/callback/route.ts calling supabase.auth.exchangeCodeForSession(code)",
        ),
    ]

    STRIPE_CHAIN: List[Tuple] = [
        (
            "**/webhooks/stripe/route.ts",
            ["request.text()"],
            "Stripe webhook uses request.json() — body consumed before signature check, always 400",
            "Change: const body = await request.json()  →  const body = await request.text()",
        ),
        (
            "**/webhooks/stripe/route.ts",
            ["constructEvent"],
            "Stripe webhook missing stripe.webhooks.constructEvent() — events not verified",
            "Add: const event = stripe.webhooks.constructEvent(body, sig, process.env.STRIPE_WEBHOOK_SECRET!)",
        ),
        (
            "**/stripe/checkout/route.ts",
            ["metadata", "user_id"],
            "Stripe checkout missing user_id in metadata — can't link payment to user",
            "Add metadata: { user_id: user.id } inside stripe.checkout.sessions.create()",
        ),
    ]

    RLS_CHAIN: List[Tuple] = [
        (
            "supabase/migrations/*.sql",
            ["on_auth_user_created"],
            "Missing on_auth_user_created trigger — profiles not created on signup, dashboard blank",
            "Add trigger: CREATE OR REPLACE TRIGGER on_auth_user_created "
            "AFTER INSERT ON auth.users FOR EACH ROW EXECUTE PROCEDURE public.handle_new_user()",
        ),
        (
            "supabase/migrations/*.sql",
            ["enable row level security"],
            "RLS not enabled on tables — all data publicly readable/writable",
            "Add for each user table: ALTER TABLE <table> ENABLE ROW LEVEL SECURITY; + policies",
        ),
    ]

    ENV_CHAIN: List[Tuple] = [
        (
            ".env.local",
            ["SUPABASE_SERVICE_ROLE_KEY"],
            "SUPABASE_SERVICE_ROLE_KEY missing from .env.local — admin operations will fail",
            "Add SUPABASE_SERVICE_ROLE_KEY=<value> from Supabase Dashboard → Settings → API",
        ),
        (
            ".env.local",
            ["STRIPE_WEBHOOK_SECRET"],
            "STRIPE_WEBHOOK_SECRET missing from .env.local — webhook verification will fail",
            "Add STRIPE_WEBHOOK_SECRET=whsec_... from Stripe Dashboard → Webhooks → Signing secret",
        ),
    ]

    return {
        "AUTH":   AUTH_CHAIN,
        "STRIPE": STRIPE_CHAIN,
        "RLS":    RLS_CHAIN,
        "ENV":    ENV_CHAIN,
    }


# ── Walker ────────────────────────────────────────────────────────────────────

def _walk_chain(
    chain_name: str,
    chain: List[Tuple],
    repo_path: str,
    layout: Dict[str, str],
) -> Optional[Dict[str, Any]]:
    """
    Walk one chain. Returns the first break found, or None if chain passes.
    Missing files are always skipped silently (not treated as breaks).
    """
    for file_pattern, needles, issue, fix_hint in chain:
        has_glob = "*" in file_pattern

        if has_glob:
            result = _glob_read_all(file_pattern, repo_path)
            if result is None:
                continue  # feature not present — not a bug
            rel_path, content = result
        else:
            # Resolve layout-aware path for middleware
            if layout.get("middleware") and (
                file_pattern.endswith("middleware.ts") or file_pattern.endswith("middleware.js")
            ):
                resolved = layout["middleware"]
            else:
                resolved = file_pattern

            abs_path = os.path.join(repo_path, resolved)
            content = _read(abs_path)
            rel_path = resolved

            if content is None:
                continue  # file not found → skip silently

        missing = _first_missing(content, needles)
        if missing:
            return {
                "chain":      chain_name,
                "broken_at":  rel_path,
                "missing":    missing,
                "issue":      issue,
                "fix_hint":   fix_hint,
                "confidence": 1.0,
            }

    return None


def walk(repo_path: str) -> List[Dict[str, Any]]:
    """
    Walk all applicable chains. ALL chains run — no early exit.
    Returns a list of all breaks found (0–4 items, one per chain at most).
    Empty list = all chains pass.

    Preconditions applied:
      AUTH   → @supabase in package.json
      STRIPE → stripe in package.json
      RLS    → supabase/migrations/ directory exists
      ENV    → @supabase OR stripe in package.json
    """
    repo_path = os.path.abspath(repo_path)
    layout = detect_layout(repo_path)
    chains = build_chains(layout)

    pkg = _read_pkg(repo_path)
    has_supabase   = "@supabase" in pkg
    has_stripe     = "\"stripe\"" in pkg or "'stripe'" in pkg or ": \"stripe\"" in pkg or '"stripe"' in pkg
    has_migrations = os.path.isdir(os.path.join(repo_path, "supabase", "migrations"))

    # Normalise: also catch e.g. "@stripe/stripe-js" and "stripe" as a dep
    has_stripe = has_stripe or ('"stripe"' in pkg) or ('stripe' in pkg.lower() and 'stripe' in [
        k.strip().strip('"').strip("'") for k in pkg.lower().split() if 'stripe' in k
    ])

    active: Dict[str, List[Tuple]] = {}
    if has_supabase:
        active["AUTH"]   = chains["AUTH"]
    if has_stripe:
        active["STRIPE"] = chains["STRIPE"]
    if has_migrations:
        active["RLS"]    = chains["RLS"]
    if has_supabase or has_stripe:
        active["ENV"]    = chains["ENV"]

    findings: List[Dict[str, Any]] = []
    for chain_name, chain in active.items():
        result = _walk_chain(chain_name, chain, repo_path, layout)
        if result:
            findings.append(result)

    return findings


# ── CLI for quick testing ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import time

    if len(sys.argv) < 2:
        print("Usage: python chain_walker.py <repo_path>")
        sys.exit(1)

    path = sys.argv[1]
    t0 = time.perf_counter()
    findings = walk(path)
    elapsed = (time.perf_counter() - t0) * 1000

    print(f"chain_walker  {elapsed:.1f}ms")

    if findings:
        for finding in findings:
            print(f"\n  BREAK  [{finding['chain']}]")
            print(f"  broken_at  : {finding['broken_at']}")
            print(f"  missing    : {finding['missing']}")
            print(f"  issue      : {finding['issue']}")
            print(f"  fix_hint   : {finding['fix_hint']}")
            print(f"  confidence : {finding['confidence']}")
    else:
        print("\n  all chains PASS — no structural breaks found")
