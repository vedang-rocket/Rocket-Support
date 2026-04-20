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
from typing import List, Set

# Ensure engine dir is on path
ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ENGINE_DIR)

import db as fix_db
import rkt_engine as engine
import fix_writer
import codegen_analyzer


def _print_fix_result_summary(fr: fix_writer.FixResult, total_issues: int) -> None:
    applied = fr.fixes_applied
    skipped = sum(1 for a in fr.audit_log if a.get("action") == "skipped")
    diff_only = sum(1 for a in fr.audit_log if a.get("action") == "diff_only")
    warned = sum(1 for a in fr.audit_log if a.get("action") == "warn_refactor")

    # Actionable excludes purely diff-only/manual-review items.
    actionable = max(total_issues - diff_only, 0)
    print(
        f"\n[fix_writer] Applied {applied} new fixes this run",
        flush=True,
    )
    print(
        f"[fix_writer] Skipped {skipped} (already fixed/non-actionable)",
        flush=True,
    )
    print(
        f"[fix_writer] Diff-only {diff_only} (manual review required)",
        flush=True,
    )
    if warned:
        print(
            f"[fix_writer] Warnings {warned} (partial auto-fix; follow-up refactor needed)",
            flush=True,
        )
    print(
        f"[fix_writer] Progress {applied}/{actionable} actionable issues across {len(fr.files_modified)} file(s)",
        flush=True,
    )


def _truncate_diff(diff_text: str, max_lines: int = 80) -> str:
    lines = diff_text.splitlines()
    if len(lines) <= max_lines:
        return diff_text
    shown = "\n".join(lines[:max_lines])
    remaining = len(lines) - max_lines
    return f"{shown}\n... ({remaining} more lines; use 'v' to view full diff)"


def _proposal_risk_label(proposal: fix_writer.FileProposal) -> str:
    conf = (proposal.confidence_summary or "HIGH").upper()
    if proposal.change_class in ("PREVIEW_ONLY", "WARN_REFACTOR"):
        return "HIGH_RISK_MANUAL"
    if conf == "LOW":
        return "HIGH_RISK"
    if conf == "MED":
        return "MEDIUM_RISK"
    return "LOW_RISK"


def _interactive_review(
    proposals: List[fix_writer.FileProposal],
) -> Set[str]:
    approved: Set[str] = set()
    stop_review = False
    has_apply_candidates = any(
        (not p.preview_only) and (p.proposed_content is not None) for p in proposals
    )
    if not has_apply_candidates:
        print(
            "\n[review] Review-only mode: no write-capable proposals in this run.",
            flush=True,
        )

    for idx, p in enumerate(proposals, start=1):
        if stop_review:
            break
        print(f"\n+{'=' * 108}+", flush=True)
        print(f"| REVIEW {idx}/{len(proposals)}", flush=True)
        print(f"| FILE: {p.file_path}", flush=True)
        print(
            f"| META: class={p.change_class} rules={','.join(p.rules) or '-'} confidence={p.confidence_summary} risk={_proposal_risk_label(p)}",
            flush=True,
        )
        print(f"+{'-' * 108}+", flush=True)
        print(
            fix_writer.colorize_unified_diff(_truncate_diff(p.proposed_diff)),
            flush=True,
        )
        print(f"+{'=' * 108}+", flush=True)

        if p.preview_only or p.proposed_content is None:
            print("[review] preview-only proposal; cannot auto-apply", flush=True)
            while True:
                try:
                    ans = input(
                        "[review] action? [y]next/[v]iew full/[q]uit (Enter=next): "
                    ).strip().lower()
                except EOFError:
                    ans = "q"
                if ans in ("", "y", "yes", "n", "next"):
                    if ans == "":
                        print("[review] continuing (default next)", flush=True)
                    break
                if ans in ("v", "view"):
                    print(fix_writer.colorize_unified_diff(p.proposed_diff), flush=True)
                    continue
                if ans in ("q", "quit"):
                    stop_review = True
                    print("[review] stopping review loop", flush=True)
                    break
                print("[review] invalid action, choose v/n/q", flush=True)
            continue

        while True:
            try:
                ans = input(
                    "[review] action? [a]pply/[s]kip/[v]iew full/[q]uit (Enter=choose): "
                ).strip().lower()
            except EOFError:
                ans = "q"

            if ans == "":
                print("[review] no default action; choose a/s/v/q", flush=True)
                continue

            if ans in ("a", "apply", "y", "yes"):
                approved.add(p.file_path)
                print("[review] marked for apply", flush=True)
                break
            if ans in ("s", "skip", "n", "next", "", "no"):
                print("[review] skipped", flush=True)
                break
            if ans in ("v", "view"):
                print(fix_writer.colorize_unified_diff(p.proposed_diff), flush=True)
                continue
            if ans in ("q", "quit"):
                stop_review = True
                print("[review] stopping review loop", flush=True)
                break
            print("[review] invalid action, choose a/s/v/n/q", flush=True)

    return approved


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
    parser.add_argument("--yes", action="store_true", help="Apply all write-capable files without prompts")
    parser.add_argument("--preview-only", action="store_true", help="Show proposals and write no files")
    parser.add_argument("--non-interactive", action="store_true", help="Disable prompts; requires --yes or --preview-only")
    parser.add_argument("--quick", action="store_true", help="Zero-LLM fast path: chain_walker + brain.db only, skips semgrep/fingerprint")
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


def _build_normalized_findings(result: dict, repo_path: str) -> list:
    """
    Merge semgrep JSON, schema timestamptz failures, and chain_walker middleware
    breaks into fix_writer input shape.
    """
    repo_path = os.path.abspath(os.path.expanduser(repo_path))
    out: list = []

    sem = result.get("semgrep") or {}
    for f in sem.get("findings") or []:
        cid = f.get("check_id") or ""
        rid = cid.split(".")[-1] if cid else ""
        raw_path = f.get("path") or ""
        if not raw_path:
            continue
        fp = (
            raw_path
            if os.path.isabs(raw_path)
            else os.path.normpath(os.path.join(repo_path, raw_path))
        )
        line = (f.get("start") or {}).get("line", 0)
        msg = (f.get("extra") or {}).get("message", "")
        if isinstance(msg, str) and "\n" in msg:
            msg = msg.split("\n")[0]
        out.append(
            {
                "rule_id": rid,
                "file_path": fp,
                "line_number": line,
                "message": msg,
                "_repo_root": repo_path,
            }
        )

    for row in result.get("schema") or []:
        if row.get("check") == "schema:timestamptz" and not row.get("found"):
            out.extend(
                fix_writer.collect_schema_timestamptz_findings(repo_path)
            )
            break

    for cw in result.get("chain_walker") or []:
        if cw.get("missing") == "updateSession":
            rel = cw.get("broken_at") or ""
            fp = os.path.normpath(os.path.join(repo_path, rel))
            out.append(
                {
                    "rule_id": "middleware-missing-updatesession",
                    "file_path": fp,
                    "line_number": 1,
                    "message": cw.get("issue", ""),
                    "_repo_root": repo_path,
                }
            )

    # Optional graph-backed findings source (Codegen graph-sitter).
    # Kept additive and best-effort so diagnosis still works if graph_sitter is unavailable.
    try:
        cg_findings = codegen_analyzer.find_violations(repo_path)
    except Exception as e:
        print(f"[codegen_analyzer] skipped: {e}", file=sys.stderr, flush=True)
        cg_findings = []

    for f in cg_findings:
        cid = f.get("check_id") or ""
        rid = cid.split(".")[-1] if cid else ""
        raw_path = f.get("path") or ""
        if not raw_path:
            continue
        fp = (
            raw_path
            if os.path.isabs(raw_path)
            else os.path.normpath(os.path.join(repo_path, raw_path))
        )
        line = (f.get("start") or {}).get("line", 0)
        msg = (f.get("extra") or {}).get("message", "")
        if isinstance(msg, str) and "\n" in msg:
            msg = msg.split("\n")[0]
        out.append(
            {
                "rule_id": rid,
                "file_path": fp,
                "line_number": line,
                "message": msg,
                "_repo_root": repo_path,
            }
        )

    return out


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


def _quick_findings(repo_path: str, hint: str) -> list:
    """
    Zero-LLM fast path: chain_walker + brain.db cache only.
    Returns normalized findings list identical in shape to _build_normalized_findings().
    """
    import chain_walker as cw

    # Check cache first
    cached = fix_db.get_cached_findings(repo_path)
    if cached is not None:
        print("[quick] cache hit — skipping chain_walker", flush=True)
        return cached

    print("[quick] running chain_walker...", flush=True)
    raw = cw.walk(repo_path)

    out = []
    for f in raw:
        broken = f.get("broken_at", "")
        fp = os.path.normpath(os.path.join(repo_path, broken)) if broken else repo_path
        chain = f.get("chain", "OTHER")
        missing = f.get("missing", "unknown")
        out.append(
            {
                "rule_id": f"{chain.lower()}-{missing.lower().replace(' ', '-')}",
                "file_path": fp,
                "line_number": 1,
                "message": f.get("issue", ""),
                "_repo_root": repo_path,
            }
        )

    # Fall back to db if chain_walker found nothing
    if not out and hint:
        db_hits = fix_db.find_similar(hint, top_k=3)
        for h in db_hits:
            out.append(
                {
                    "rule_id": h.get("category", "OTHER").lower() + "-db-match",
                    "file_path": repo_path,
                    "line_number": 0,
                    "message": h.get("pattern", ""),
                    "_repo_root": repo_path,
                    "_fix_diff": h.get("fix_diff", ""),
                }
            )

    fix_db.set_cached_findings(repo_path, out)
    return out


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
    repo_path = os.path.abspath(os.path.expanduser(args.repo_path))

    if args.quick:
        findings = _quick_findings(repo_path, args.hint)
    else:
        diag = engine.diagnose(repo_path, args.hint)
        findings = _build_normalized_findings(diag, repo_path)
    findings = fix_writer.dedupe_findings(findings)
    total_issues = len(findings)
    plan = fix_writer.plan_fixes(
        findings,
        db_match=diag.get("db_match"),
        kb_hits=diag.get("kb_hits"),
    )
    preview = fix_writer.apply_fix_plan(plan, write_changes=False)
    diffs_to_show = preview.diffs
    if args.yes or args.non_interactive:
        preview_paths = {p.file_path for p in plan.proposals if p.preview_only}
        diffs_to_show = {k: v for k, v in preview.diffs.items() if k not in preview_paths}
    fix_writer.print_diff_summary(diffs_to_show)
    _print_fix_result_summary(preview, total_issues)
    if not plan.proposals:
        print("[fix_writer] No proposals generated; nothing to review.", flush=True)
        print("[fix_writer] No changes written.", flush=True)
        return 0

    if args.non_interactive and not (args.yes or args.preview_only):
        print(
            "\n[fix_writer] --non-interactive requires --yes or --preview-only",
            file=sys.stderr,
            flush=True,
        )
        return 2

    apply_candidates = [
        p for p in plan.proposals if not p.preview_only and p.proposed_content is not None
    ]
    selected_paths: Set[str] = set()

    if args.preview_only:
        print("\n[fix_writer] Preview-only mode enabled; no files will be written.", flush=True)
    elif args.yes:
        selected_paths = {p.file_path for p in apply_candidates}
    elif args.non_interactive or not sys.stdin.isatty():
        print(
            "\n[fix_writer] Non-interactive shell detected; skipping writes. Use --yes to apply or --preview-only.",
            flush=True,
        )
    else:
        selected_paths = _interactive_review(plan.proposals)

    if selected_paths:
        fr = fix_writer.apply_fix_plan(
            plan, selected_paths=selected_paths, write_changes=True
        )
        print("\n[fix_writer] Selected changes applied.", flush=True)
        _print_fix_result_summary(fr, total_issues)
        audit_path = os.path.expanduser("~/.rocket-support/fix_audit.jsonl")
        fix_writer.append_audit_jsonl(audit_path, fr.audit_log)
    else:
        print("[fix_writer] No changes written.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
