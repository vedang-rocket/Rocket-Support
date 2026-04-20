import json
import os
import subprocess
import sys
import time
from typing import Any, Dict, List

ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ENGINE_DIR)
sys.path.insert(0, os.path.join(ENGINE_DIR, "kb"))

from flutter_chain_walker import walk
from flutter_dart_scanner import scan
from schema_checker import check as schema_check
from db import lookup_flutter_fix, save_flutter_fix
from kb_search import search as kb_search

FLUTTER_BIN = "/Users/sarvadhisolution/flutter/bin/flutter"


def _read(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""


def fingerprint(repo_path: str) -> Dict[str, Any]:
    repo_path = os.path.abspath(os.path.expanduser(repo_path))
    pubspec = _read(os.path.join(repo_path, "pubspec.yaml"))
    main = _read(os.path.join(repo_path, "lib/main.dart"))
    has_supabase = "supabase_flutter" in pubspec
    supabase_version = "unknown"
    for line in pubspec.splitlines():
        if "supabase_flutter:" in line:
            supabase_version = line.split(":", 1)[1].strip()
            break
    state = "none"
    for name, label in (
        ("flutter_riverpod", "Riverpod"),
        ("provider", "Provider"),
        ("bloc", "BLoC"),
        ("getx", "GetX"),
    ):
        if f"{name}:" in pubspec:
            state = label
            break
    likely_failures = [
        "Missing deep link callbacks",
        "env.json not bundled in pubspec assets",
        "Missing onAuthStateChange listener",
    ]
    if supabase_version.startswith("^1."):
        likely_failures.insert(0, "supabase_flutter v1 APIs still used")

    output = {
        "framework": "Flutter",
        "has_supabase": has_supabase,
        "supabase_version": supabase_version,
        "state_management": state,
        "has_google_auth": "google_sign_in:" in pubspec,
        "has_stripe": "flutter_stripe:" in pubspec or "\npay:" in pubspec,
        "has_push": "firebase_messaging:" in pubspec or "flutter_local_notifications:" in pubspec,
        "likely_failures": likely_failures,
        "main_has_binding": "WidgetsFlutterBinding.ensureInitialized" in main,
        "main_has_supabase_init": "Supabase.initialize" in main,
    }
    return output


def run_flutter_analyze(repo_path: str) -> str:
    try:
        result = subprocess.run(
            [FLUTTER_BIN, "analyze", "--no-pub"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        raw_output = (result.stdout or "") + (result.stderr or "")
        lines = [line for line in raw_output.splitlines() if line.strip()]
        if not lines:
            return ""

        error_lines = [
            line for line in lines
            if ("error •" in line or "warning •" in line or "uri_does_not_exist" in line or "Target of URI doesn't exist" in line)
        ]
        uri_missing_count = sum(1 for line in lines if "uri_does_not_exist" in line)
        has_flutter_pkg_missing = "Target of URI doesn't exist: 'package:flutter/" in raw_output

        show_lines = error_lines if error_lines else lines
        shown = show_lines[:5]
        remaining = max(len(show_lines) - len(shown), 0)

        output_lines = []
        if uri_missing_count >= 10 or has_flutter_pkg_missing:
            output_lines.append("NOTE: Most errors are 'uri_does_not_exist' — run 'flutter pub get' first to download packages. These are NOT code bugs.")
        output_lines.extend(shown)
        if remaining > 0:
            output_lines.append(f"... and {remaining} more (run flutter pub get to resolve)")
        return "\n".join(output_lines)
    except Exception as exc:
        return f"flutter analyze failed: {exc}"


def determine_category(chain_results: List[Dict], dart_results: List[Dict], analyze_output: str = "") -> str:
    chain_names = {c.get("chain", "") for c in chain_results}
    pattern_ids = " ".join(d.get("pattern_id", "") for d in dart_results).lower()
    if "AUTH" in chain_names or "auth" in pattern_ids:
        return "AUTH"
    if "SUPABASE" in chain_names:
        return "SUPABASE"
    if "DEEPLINK" in chain_names:
        return "DEEPLINK"
    if "BUILD" in chain_names or "error" in (analyze_output or "").lower():
        return "BUILD"
    return "OTHER"


def save_flutter_findings(findings: List[Dict], repo_path: str) -> None:
    for f in findings:
        save_flutter_fix(f, repo_path)


def print_findings(
    chain_results: List[Dict],
    schema_results: List[Dict],
    dart_results: List[Dict],
    db_match: Dict,
    kb_hits: List[Dict],
    analyze_output: str,
    hint: str,
) -> None:
    if chain_results:
        print("\n[chain_walker findings]")
        for f in chain_results:
            print(f"- [{f['chain']}] {f['broken_at']}: {f['issue']}")
    if schema_results:
        missing = [x for x in schema_results if not x.get("found", True)]
        if missing:
            print("\n[schema_checker findings]")
            for f in missing:
                print(f"- {f['check']}: {f['fix_hint']}")
    if dart_results:
        print("\n[dart_scanner findings]")
        for f in dart_results[:15]:
            print(f"- {f['file']}:{f['line']} [{f['pattern_id']}] {f['issue']}")
    if db_match:
        print(f"\n[db_lookup] best match score={db_match.get('_score', 0):.2f}")
        print(f"- pattern_id={db_match.get('pattern_id')} fix_hint={db_match.get('fix_hint')}")
    if kb_hits:
        print("\n[kb_search]")
        for h in kb_hits:
            print(f"- {h['source']} score={h['score']}")
    if analyze_output:
        print("\n[flutter_analyze]")
        lines = analyze_output.strip().splitlines()
        for line in lines:
            print(line)
    if hint:
        print(f"\n[hint] {hint}")


def diagnose(repo_path: str, hint: str = "") -> Dict[str, Any]:
    repo_path = os.path.abspath(os.path.expanduser(repo_path))

    t0 = time.perf_counter()
    chain_results = walk(repo_path)
    t_chain = (time.perf_counter() - t0) * 1000
    print(f"[chain_walker]    {t_chain:.1f}ms  -> {len(chain_results)} finding(s)")

    t1 = time.perf_counter()
    schema_results = schema_check(repo_path)
    t_schema = (time.perf_counter() - t1) * 1000
    print(f"[schema_checker]  {t_schema:.1f}ms  -> {len(schema_results)} checks")

    t2 = time.perf_counter()
    dart_results = scan(repo_path)
    t_dart = (time.perf_counter() - t2) * 1000
    print(f"[dart_scanner]    {t_dart:.1f}ms  -> {len(dart_results)} violation(s)")

    t3 = time.perf_counter()
    db_match = lookup_flutter_fix(chain_results + dart_results)
    t_db = (time.perf_counter() - t3) * 1000
    db_msg = "no match" if not db_match else f"{db_match.get('_score', 0):.0%} match"
    print(f"[db_lookup]       {t_db:.1f}ms  -> {db_msg}")

    t4 = time.perf_counter()
    issue_category = determine_category(chain_results, dart_results)
    kb_hits = kb_search(f"flutter {issue_category} supabase", top_k=2, source_tag="flutter")
    t_kb = (time.perf_counter() - t4) * 1000
    print(f"[kb_search]       {t_kb:.1f}ms  -> {len(kb_hits)} chunk(s)")

    t5 = time.perf_counter()
    analyze_output = run_flutter_analyze(repo_path)
    t_analyze = (time.perf_counter() - t5) * 1000
    print(f"[flutter_analyze] {t_analyze/1000:.1f}s")

    print_findings(chain_results, schema_results, dart_results, db_match, kb_hits, analyze_output, hint)
    save_flutter_findings(chain_results + dart_results, repo_path)

    return {
        "repo_path": repo_path,
        "chain_results": chain_results,
        "schema_results": schema_results,
        "dart_results": dart_results,
        "db_match": db_match,
        "kb_hits": kb_hits,
        "analyze_output": analyze_output,
    }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: flutter_rkt_engine.py [fingerprint|scan|diagnose] <repo_path> [hint]")
        sys.exit(1)
    command = sys.argv[1]
    path = sys.argv[2]
    hint = sys.argv[3] if len(sys.argv) > 3 else ""
    if command == "fingerprint":
        print(json.dumps(fingerprint(path), indent=2))
    elif command in ("scan", "diagnose"):
        diagnose(path, hint)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
