#!/usr/bin/env python3
"""
rkt_smart.py — Drop-in replacement for the `claude -p` call in ~/rocket-support/bin/rkt.

Usage:
  python3 rkt_smart.py <repo_path> [hint]
  rkt_smart <repo_path> [hint]

Interface is identical to the original claude -p call:
  - repo_path: absolute path to the cloned repo
  - hint: optional client hint string
  - output: diagnosis + diff on stdout (same format as CLAUDE.md spec)
"""

import sys
import os
import argparse

# Ensure engine dir is on path
ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ENGINE_DIR)

import db as fix_db
import rkt_engine as engine


def parse_args():
    parser = argparse.ArgumentParser(
        description="rkt_smart — Rocket.new intelligent fix engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  rkt_smart ~/Documents/Rocket/cliently
  rkt_smart ~/Documents/Rocket/cliently "auth broken after login"
  rkt_smart ~/Documents/Rocket/wedcraft_5415

Output format matches CLAUDE.md spec:
  ROOT CAUSE / CATEGORY / FIX / FILES CHANGED / DIFF / VERIFY / IF STILL BROKEN
        """
    )
    parser.add_argument("repo_path", nargs="?", default="", help="Path to the cloned client repository")
    parser.add_argument("hint", nargs="?", default="", help="Optional client hint for faster routing")
    parser.add_argument("--seed-db", action="store_true", help="Seed the fix database with built-in patterns")
    parser.add_argument("--fingerprint-only", action="store_true", help="Only fingerprint the project, don't run full diagnosis")
    parser.add_argument("--db-stats", action="store_true", help="Show fix database statistics")
    return parser.parse_args()


def show_db_stats():
    fix_db.init_db()
    fixes = fix_db.get_all_fixes()
    if not fixes:
        print("Fix database is empty. Run with --seed-db to populate.")
        return
    print(f"\nFix database: {fix_db.DB_PATH}")
    print(f"Total fixes:  {len(fixes)}")
    print(f"\n{'Category':<12} {'Uses':<6} {'V':<3} Pattern")
    print("-" * 70)
    for f in fixes:
        verified = "✓" if f.get("verified") else " "
        print(f"  {f.get('category', '?'):<10} {f.get('uses', 0):<6} {verified}   {f.get('pattern', '')[:50]}")


def fingerprint_only(repo_path: str):
    import fingerprint as fp
    result = fp.fingerprint(repo_path)
    print(f"\nProject:         {os.path.basename(repo_path)}")
    print(f"Type:            {result['project_type']} (confidence: {result['confidence']:.0%})")
    print(f"Framework:       {result['framework']} {result.get('next_version', '')}")
    print(f"Has Supabase:    {result['has_supabase']}")
    print(f"Has Stripe:      {result['has_stripe']}")
    print(f"SQL files:       {result['sql_files_found']}")
    print(f"Most likely bug: {result['common_failure']}")
    print(f"Category:        {result['category']}")
    print(f"\nAll scores:")
    for t, s in sorted(result["all_scores"].items(), key=lambda x: -x[1]):
        bar = "█" * int(s * 20)
        print(f"  {t:<12} {s:.3f} {bar}")
    print(f"\nEnv vars:")
    for k, v in result["env_vars"].items():
        status = "\033[0;32m✓\033[0m" if v else "\033[0;31m✗\033[0m"
        print(f"  {status} {k}")


def main():
    args = parse_args()

    if args.seed_db:
        print("Seeding fix database with built-in Rocket.new patterns...")
        fix_db.seed_builtin_fixes()
        fixes = fix_db.get_all_fixes()
        print(f"Done. {len(fixes)} fixes in database at {fix_db.DB_PATH}")
        return 0

    if args.db_stats:
        show_db_stats()
        return 0

    if not args.repo_path and not args.seed_db and not args.db_stats:
        print("Error: repo_path is required for diagnosis", file=sys.stderr)
        return 1

    if args.fingerprint_only:
        fingerprint_only(args.repo_path)
        return 0

    # Full diagnosis pipeline
    engine.diagnose(args.repo_path, args.hint)
    return 0


if __name__ == "__main__":
    sys.exit(main())
