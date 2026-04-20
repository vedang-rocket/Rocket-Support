"""
Project fingerprinter — detects Rocket.new project type from package.json + file structure.
Returns one of: SaaS | E-Commerce | AI | Booking | Landing | Blog | Unknown
"""

import fnmatch
import json
import os
from typing import Dict, Any, List, Optional

SKIP_DIRS = {"node_modules", ".next", ".git", "__pycache__", ".rkt_snapshot", "dist", ".turbo"}


# ── Signal definitions ───────────────────────────────────────────────────────

PROJECT_TYPE_SIGNALS = {
    "SaaS": {
        "deps": ["stripe", "@stripe/stripe-js"],
        "table_keywords": ["subscriptions", "subscription", "plans", "billing"],
        "file_patterns": ["**/subscriptions/**", "**/billing/**", "**/pricing/**"],
        "common_failure": "Stripe webhook 400 — request.json() used instead of request.text()",
        "category": "STRIPE",
    },
    "E-Commerce": {
        "deps": ["stripe", "@stripe/stripe-js", "shopify", "woocommerce"],
        "table_keywords": ["products", "orders", "inventory", "cart", "order_items"],
        "file_patterns": ["**/products/**", "**/orders/**", "**/cart/**", "**/shop/**"],
        "common_failure": "No inventory decrement on checkout or RLS gap on orders table",
        "category": "SUPABASE",
    },
    "AI": {
        "deps": ["openai", "@anthropic-ai/sdk", "anthropic", "langchain", "@langchain/core", "ai", "@google/generative-ai"],
        "table_keywords": ["conversations", "messages", "chat_history", "embeddings", "tokens"],
        "file_patterns": ["**/chat/**", "**/assistant/**", "**/ai/**"],
        "common_failure": "No rate limiting on AI endpoints — users can exhaust API quota",
        "category": "OTHER",
    },
    "Booking": {
        "deps": ["cal.com", "calendly", "date-fns", "dayjs", "luxon"],
        "table_keywords": ["bookings", "appointments", "slots", "availability", "reservations"],
        "file_patterns": ["**/bookings/**", "**/appointments/**", "**/calendar/**", "**/schedule/**"],
        "common_failure": "Double-booking possible — no unique constraint on time slot + resource",
        "category": "SUPABASE",
    },
    "Landing": {
        "deps": [],
        "table_keywords": ["leads", "subscribers", "newsletter", "waitlist", "contacts"],
        "file_patterns": ["**/contact/**", "**/leads/**", "**/newsletter/**", "**/waitlist/**"],
        "common_failure": "RLS blocking anonymous INSERT on leads/subscribers table",
        "category": "SUPABASE",
    },
    "Blog": {
        "deps": ["@sanity/client", "contentlayer", "gray-matter", "mdx-bundler", "next-mdx-remote"],
        "table_keywords": ["posts", "articles", "categories", "tags", "authors"],
        "file_patterns": ["**/posts/**", "**/blog/**", "**/articles/**", "content/**"],
        "common_failure": "Missing sitemap.xml generation or dynamic OG images returning 500",
        "category": "BUILD",
    },
}


def _load_package_json(repo_path: str) -> Dict[str, Any]:
    pkg_path = os.path.join(repo_path, "package.json")
    if not os.path.exists(pkg_path):
        return {}
    with open(pkg_path) as f:
        return json.load(f)


def _get_all_deps(pkg: Dict[str, Any]) -> List[str]:
    deps = list(pkg.get("dependencies", {}).keys())
    deps += list(pkg.get("devDependencies", {}).keys())
    return [d.lower() for d in deps]


def _find_sql_files(repo_path: str) -> List[str]:
    """Find SQL files using os.walk, pruning skip dirs before descending."""
    found = []
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if f.endswith(".sql"):
                found.append(os.path.join(root, f))
    return found


def _read_sql_content(sql_files: List[str]) -> str:
    """Read all SQL content, lowercased, for keyword matching."""
    content = ""
    for f in sql_files[:20]:  # Cap at 20 files
        try:
            with open(f) as fh:
                content += fh.read().lower() + "\n"
        except Exception:
            pass
    return content


def _scan_file_patterns(repo_path: str, patterns: List[str]) -> int:
    """Count files matching any pattern using os.walk, pruning skip dirs before descending."""
    count = 0
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            full = os.path.join(root, f)
            rel  = os.path.relpath(full, repo_path)
            for pat in patterns:
                if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(f, pat.split("/")[-1]):
                    count += 1
                    break  # only count each file once
    return count


def _score_project_type(repo_path: str, pkg: Dict[str, Any]) -> Dict[str, float]:
    """Score each project type 0.0–1.0 based on signals."""
    all_deps = _get_all_deps(pkg)
    sql_files = _find_sql_files(repo_path)
    sql_content = _read_sql_content(sql_files)
    scores: Dict[str, float] = {}

    for ptype, signals in PROJECT_TYPE_SIGNALS.items():
        score = 0.0

        # Dependency matches (weight: 0.4)
        dep_hits = sum(1 for d in signals["deps"] if d in all_deps)
        if signals["deps"]:
            score += (dep_hits / len(signals["deps"])) * 0.4

        # SQL table keyword matches (weight: 0.4)
        table_hits = sum(1 for kw in signals["table_keywords"] if kw in sql_content)
        if signals["table_keywords"]:
            score += (table_hits / len(signals["table_keywords"])) * 0.4

        # File pattern matches (weight: 0.2)
        file_hits = _scan_file_patterns(repo_path, signals["file_patterns"])
        if file_hits > 0:
            score += 0.2

        scores[ptype] = round(score, 3)

    return scores


def _detect_next_version(pkg: Dict[str, Any]) -> Optional[str]:
    next_ver = pkg.get("dependencies", {}).get("next", "")
    if not next_ver:
        next_ver = pkg.get("devDependencies", {}).get("next", "")
    return next_ver or None


def _detect_has_supabase(all_deps: List[str]) -> bool:
    return any("supabase" in d for d in all_deps)


def _detect_has_stripe(all_deps: List[str]) -> bool:
    return any("stripe" in d for d in all_deps)


def _detect_framework(pkg: Dict[str, Any], repo_path: str) -> str:
    all_deps = _get_all_deps(pkg)
    if "next" in all_deps:
        return "Next.js"
    if "remix" in all_deps:
        return "Remix"
    if "vite" in all_deps:
        return "Vite"
    if "gatsby" in all_deps:
        return "Gatsby"
    return "Unknown"


def _check_env_vars(repo_path: str) -> Dict[str, bool]:
    """Check which env vars are set in .env or .env.local."""
    env_content = ""
    for env_file in [".env", ".env.local", ".env.production"]:
        path = os.path.join(repo_path, env_file)
        if os.path.exists(path):
            try:
                with open(path) as f:
                    env_content += f.read() + "\n"
            except Exception:
                pass

    required = [
        "NEXT_PUBLIC_SUPABASE_URL",
        "NEXT_PUBLIC_SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY",
    ]
    result = {}
    for var in required:
        result[var] = var in env_content and f"{var}=your" not in env_content and f"{var}=dummy" not in env_content
    return result


def fingerprint(repo_path: str) -> Dict[str, Any]:
    """
    Fingerprint a repository.

    Returns:
        {
            "project_type": "SaaS",           # Best match
            "confidence": 0.85,               # 0.0–1.0
            "all_scores": {...},              # All type scores
            "common_failure": "...",          # Most likely issue
            "category": "STRIPE",             # Issue category
            "framework": "Next.js",
            "next_version": "15.1.11",
            "has_supabase": True,
            "has_stripe": False,
            "env_vars": {...},
            "sql_files_found": 2,
        }
    """
    repo_path = os.path.abspath(repo_path)
    pkg = _load_package_json(repo_path)
    all_deps = _get_all_deps(pkg)

    scores = _score_project_type(repo_path, pkg)
    best_type = max(scores, key=scores.__getitem__) if scores else "Unknown"
    confidence = scores.get(best_type, 0.0)
    used_fallback = False
    signal_health = "ok"
    fallback_reason = ""
    max_score = max(scores.values()) if scores else 0.0

    # If all scores are zero or very low, do a heuristic fallback
    if confidence < 0.05:
        used_fallback = True
        signal_health = "low_signal"
        fallback_reason = f"max score {max_score:.3f} below threshold"
        has_stripe = _detect_has_stripe(all_deps)
        has_supabase = _detect_has_supabase(all_deps)
        sql_files = _find_sql_files(repo_path)
        sql_content = _read_sql_content(sql_files).lower()

        if has_stripe and "subscription" in sql_content:
            best_type = "SaaS"
        elif has_stripe and ("product" in sql_content or "order" in sql_content):
            best_type = "E-Commerce"
        elif any(ai in all_deps for ai in ["openai", "anthropic", "ai"]):
            best_type = "AI"
        elif "booking" in sql_content or "appointment" in sql_content:
            best_type = "Booking"
        elif "post" in sql_content or "article" in sql_content:
            best_type = "Blog"
        else:
            best_type = "Landing"
        confidence = 0.3  # low confidence heuristic

    signals = PROJECT_TYPE_SIGNALS.get(best_type, {})
    sql_files = _find_sql_files(repo_path)
    env_vars = _check_env_vars(repo_path)

    return {
        "project_type": best_type,
        "confidence": confidence,
        "all_scores": scores,
        "common_failure": signals.get("common_failure", "Unknown"),
        "category": signals.get("category", "OTHER"),
        "framework": _detect_framework(pkg, repo_path),
        "next_version": _detect_next_version(pkg),
        "has_supabase": _detect_has_supabase(all_deps),
        "has_stripe": _detect_has_stripe(all_deps),
        "env_vars": env_vars,
        "sql_files_found": len(sql_files),
        "all_deps": all_deps[:30],  # First 30 for context
        "used_fallback": used_fallback,
        "signal_health": signal_health,
        "fallback_reason": fallback_reason,
        "max_score": max_score,
    }


def print_human(result: Dict[str, Any], repo_path: str = ""):
    """Pretty-print fingerprint result to stdout."""
    name = os.path.basename(repo_path or result.get("repo_path", ""))
    if name:
        print(f"\nProject:         {name}")
    print(f"Type:            {result['project_type']} (confidence: {result['confidence']:.0%})")
    print(f"Framework:       {result['framework']} {result.get('next_version', '')}")
    print(f"Has Supabase:    {result['has_supabase']}")
    print(f"Has Stripe:      {result['has_stripe']}")
    print(f"SQL files:       {result['sql_files_found']}")
    print(f"Most likely bug: {result['common_failure']}")
    print(f"Category:        {result['category']}")
    if result.get("used_fallback"):
        print("Signal health:   low-signal (heuristic fallback used)")
        print(f"Fallback reason: {result.get('fallback_reason', 'insufficient project signals')}")
    print(f"\nType scores:")
    for t, s in sorted(result["all_scores"].items(), key=lambda x: -x[1]):
        bar = "█" * int(s * 20)
        print(f"  {t:<12} {s:.3f} {bar}")
    print(f"\nEnv vars:")
    for k, v in result["env_vars"].items():
        status = "\033[0;32m✓\033[0m" if v else "\033[0;31m✗\033[0m"
        print(f"  {status} {k}")


if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="Rocket.new project fingerprinter")
    parser.add_argument("repo_path", nargs="?", default=".", help="Path to repo")
    parser.add_argument("--json", action="store_true", help="Output JSON (for scripting)")
    parser.add_argument("--save", action="store_true", help="Save fingerprint to brain.db")
    args = parser.parse_args()

    result = fingerprint(args.repo_path)
    result["repo_path"] = os.path.abspath(args.repo_path)

    if args.save:
        try:
            import sys as _sys
            _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            import db as fix_db
            fix_db.save_project_fingerprint(result)
            if not args.json:
                print(f"\033[0;32m✓\033[0m Fingerprint saved to {fix_db.DB_PATH}", file=sys.stderr)
        except Exception as e:
            print(f"\033[1;33m⚠\033[0m Could not save to DB: {e}", file=sys.stderr)

    if args.json:
        import json as _json
        # Emit clean JSON — remove non-serialisable items
        out = {k: v for k, v in result.items() if k != "all_deps"}
        print(_json.dumps(out))
    else:
        print_human(result, args.repo_path)
