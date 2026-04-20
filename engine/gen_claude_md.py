#!/usr/bin/env python3
import json
import os
import re
import sys


def read_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""


def detect(project_dir: str):
    pubspec = read_file(os.path.join(project_dir, "pubspec.yaml"))
    env_text = read_file(os.path.join(project_dir, "env.json"))
    main_text = read_file(os.path.join(project_dir, "lib", "main.dart"))

    sdk = "unknown"
    sdk_match = re.search(r"sdk:\s*['\"]([^'\"]+)['\"]", pubspec)
    if sdk_match:
        sdk = sdk_match.group(1).strip()

    supabase_v = "none"
    supabase_match = re.search(r"^\s*supabase_flutter:\s*([^\n#]+)", pubspec, re.MULTILINE)
    has_supabase = bool(supabase_match)
    if supabase_match:
        supabase_v = supabase_match.group(1).strip()

    def has_dep(name: str) -> bool:
        return bool(re.search(rf"^\s*{re.escape(name)}\s*:", pubspec, re.MULTILINE))

    state = "none"
    for dep, label in (
        ("flutter_riverpod", "riverpod"),
        ("provider", "provider"),
        ("bloc", "bloc"),
        ("getx", "getx"),
    ):
        if has_dep(dep):
            state = label
            break

    has_stripe = has_dep("flutter_stripe") or has_dep("pay")
    has_google = has_dep("google_sign_in")
    has_push = has_dep("firebase_messaging") or has_dep("flutter_local_notifications")

    env_ok = False
    if env_text:
        try:
            env = json.loads(env_text)
            env_ok = bool(env.get("SUPABASE_URL")) and bool(env.get("SUPABASE_ANON_KEY"))
        except Exception:
            env_ok = False

    return {
        "sdk": sdk,
        "supabase_v": supabase_v,
        "state": state,
        "has_supabase": has_supabase,
        "has_stripe": has_stripe,
        "has_google": has_google,
        "has_push": has_push,
        "env_ok": env_ok,
        "has_binding": "WidgetsFlutterBinding.ensureInitialized" in main_text,
        "has_supabase_init": "Supabase.initialize" in main_text,
    }


def build_markdown(project_name: str, signals: dict) -> str:
    likely_failures = [
        "Missing deep link callbacks",
        "env.json not bundled in pubspec assets",
        "Missing onAuthStateChange listener",
    ]
    if str(signals.get("supabase_v", "")).startswith("^1."):
        likely_failures.insert(0, "supabase_flutter v1 APIs still used")
    failures_block = "\n".join(f"- {item}" for item in likely_failures)

    return f"""# {project_name} — Flutter Project Context
## Stack
Flutter | SDK {signals['sdk']} | supabase_flutter {signals['supabase_v']} | {signals['state']}
Supabase: {str(signals['has_supabase']).lower()} | Stripe: {str(signals['has_stripe']).lower()} | Google auth: {str(signals['has_google']).lower()} | Push: {str(signals['has_push']).lower()}

## Flutter Hard Rules
1. Always use supabase_flutter ^2.x
2. WidgetsFlutterBinding.ensureInitialized() before Supabase.initialize()
3. Keys from env.json, never hardcoded in Dart
4. Use onAuthStateChange listener for auth navigation
5. Deep link scheme must match Android namespace
6. flutter analyze must pass before submitting fixes

## Project Signals
env.json keys ready: {str(signals['env_ok']).lower()}
main has ensureInitialized: {signals['has_binding']}
main has Supabase.initialize: {signals['has_supabase_init']}

## Likely Failure Modes
{failures_block}
"""


def main():
    if len(sys.argv) < 2:
        print("Usage: gen_claude_md.py <project_dir>", file=sys.stderr)
        sys.exit(1)
    project_dir = os.path.abspath(os.path.expanduser(sys.argv[1]))
    project_name = os.path.basename(project_dir)
    signals = detect(project_dir)
    print(build_markdown(project_name, signals))


if __name__ == "__main__":
    main()
