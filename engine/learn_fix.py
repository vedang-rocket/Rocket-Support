"""
learn_fix.py — interactive auto-learn prompt for rkt-done.

Prompts the engineer to confirm and save a fix pattern to brain.db after
a session completes.

Usage (from rkt-done):
    engine/.venv/bin/python engine/learn_fix.py --project "novylo" --thread "69ef38f..."
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

CATEGORIES = ["AUTH", "STRIPE", "SUPABASE", "BUILD", "ENV", "RLS", "OTHER"]

GREEN  = "\033[0;32m"
CYAN   = "\033[0;36m"
BOLD   = "\033[1m"
YELLOW = "\033[1;33m"
NC     = "\033[0m"


def prompt_learn(project: str, thread: str) -> None:
    print(f"\n  {BOLD}{CYAN}── Auto-Learn ─────────────────────────────────────────{NC}")
    print(f"\n  Save fix to brain.db for future tickets?")
    print(f"\n  {BOLD}Project:{NC}  {project}")
    print(f"  {BOLD}Thread:{NC}   {thread}\n")

    confirm = input(f"  Save fix? [y/N]: ").strip().lower()
    if confirm != "y":
        print(f"  {YELLOW}Skipped — no pattern saved.{NC}\n")
        return

    print(f"\n  {BOLD}What was the root cause?{NC}")
    pattern = input("  Pattern (e.g. 'getSession() used in server route'): ").strip()
    if not pattern:
        print(f"  {YELLOW}Skipped — empty pattern.{NC}\n")
        return

    print(f"\n  {BOLD}Error signature{NC} (what the user reported / error message):")
    error_sig = input("  Error signature: ").strip()

    print(f"\n  {BOLD}Category:{NC}")
    for i, cat in enumerate(CATEGORIES, 1):
        print(f"    {i}. {cat}")
    cat_input = input("  Choose [1-7]: ").strip()
    try:
        category = CATEGORIES[int(cat_input) - 1]
    except (ValueError, IndexError):
        category = "OTHER"

    print(f"\n  {BOLD}Fix diff{NC} (paste unified diff, or press Enter to skip):")
    print("  (End with a line containing only '---')")
    diff_lines = []
    while True:
        line = input()
        if line == "---":
            break
        diff_lines.append(line)
    fix_diff = "\n".join(diff_lines) if diff_lines else None

    import db
    fix_id = db.save_fix(
        pattern=pattern,
        error_signature=error_sig or f"{project}|{thread}",
        category=category,
        fix_diff=fix_diff,
        verified=1,
    )
    print(f"\n  {GREEN}✓{NC}  Pattern saved: {fix_id[:8]}... [{category}] {pattern[:60]}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Prompt to save fix pattern to brain.db")
    parser.add_argument("--project", default="unknown", help="Project name")
    parser.add_argument("--thread", default="", help="Thread ID")
    args = parser.parse_args()
    prompt_learn(args.project, args.thread)
