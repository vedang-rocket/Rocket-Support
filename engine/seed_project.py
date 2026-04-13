#!/usr/bin/env python3
"""
seed_project.py — Read fingerprint JSON from stdin, save to brain.db.
Called by rkt-main after fingerprinting a project.

Usage:
  echo "$FP_JSON" | python3 seed_project.py
  python3 seed_project.py < fingerprint.json
"""

import sys
import json
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db as fix_db


def main():
    raw = sys.stdin.read().strip()
    if not raw:
        print("  \033[1;33m⚠\033[0m seed_project: no input on stdin", file=sys.stderr)
        sys.exit(1)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  \033[0;31m✗\033[0m seed_project: invalid JSON — {e}", file=sys.stderr)
        sys.exit(1)

    fix_db.save_project_fingerprint(data)
    projects = fix_db.get_project_history()
    print(f"  \033[0;32m✓\033[0m Fingerprint saved — {len(projects)} project(s) in {fix_db.DB_PATH}")


if __name__ == "__main__":
    main()
