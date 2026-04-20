import glob
import json
import os
import re
from typing import Dict, List


def _read(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        return ""


def _find_files(root: str, pattern: str) -> List[str]:
    return sorted(glob.glob(os.path.join(root, pattern), recursive=True))


def check_assets_exist(pubspec_content: str, project_root: str) -> bool:
    lines = pubspec_content.splitlines()
    in_assets = False
    assets_indent = None
    for line in lines:
        if re.match(r"^\s*assets:\s*$", line):
            in_assets = True
            assets_indent = len(line) - len(line.lstrip())
            continue
        if in_assets:
            if line.strip() == "":
                continue
            current_indent = len(line) - len(line.lstrip())
            if current_indent <= assets_indent and not line.lstrip().startswith("-"):
                in_assets = False
                continue
            m = re.match(r"^\s*-\s*(.+?)\s*$", line)
            if m:
                rel = m.group(1).strip().strip('"').strip("'")
                if not os.path.exists(os.path.join(project_root, rel)):
                    return False
    return True


def _has_supabase(pubspec: str) -> bool:
    return "supabase_flutter" in pubspec


def _is_supabase_v1(pubspec: str) -> bool:
    match = re.search(r"^\s*supabase_flutter:\s*([^\n#]+)", pubspec, re.MULTILINE)
    if not match:
        return False
    version_spec = match.group(1).strip()
    return "^1." in version_spec


def _has_auth_usage(project_root: str) -> bool:
    for path in _find_files(project_root, "lib/**/*.dart"):
        content = _read(path)
        if "signIn" in content or "onAuthStateChange" in content:
            return True
    return False


def _break(chain: str, broken_at: str, missing: str, issue: str, fix_hint: str) -> Dict:
    return {
        "chain": chain,
        "broken_at": broken_at,
        "missing": missing,
        "issue": issue,
        "fix_hint": fix_hint,
        "confidence": 1.0,
    }


def walk(project_root: str) -> List[Dict]:
    project_root = os.path.abspath(os.path.expanduser(project_root))
    findings: List[Dict] = []

    main_dart = os.path.join(project_root, "lib/main.dart")
    pubspec = os.path.join(project_root, "pubspec.yaml")
    env_json = os.path.join(project_root, "env.json")
    android_manifest = os.path.join(project_root, "android/app/src/main/AndroidManifest.xml")
    ios_plist = os.path.join(project_root, "ios/Runner/Info.plist")
    gradle = os.path.join(project_root, "android/app/build.gradle")
    gradle_kts = os.path.join(project_root, "android/app/build.gradle.kts")

    main_content = _read(main_dart)
    pubspec_content = _read(pubspec)
    env_content = _read(env_json)

    # AUTH_CHAIN
    if "WidgetsFlutterBinding.ensureInitialized" not in main_content:
        findings.append(_break(
            "AUTH",
            "lib/main.dart",
            "WidgetsFlutterBinding.ensureInitialized",
            "main.dart missing WidgetsFlutterBinding.ensureInitialized() before Supabase.initialize()",
            "Add WidgetsFlutterBinding.ensureInitialized(); before Supabase.initialize().",
        ))
    if "Supabase.initialize" not in main_content:
        findings.append(_break(
            "AUTH",
            "lib/main.dart",
            "Supabase.initialize",
            "main.dart missing Supabase.initialize() — app cannot connect to Supabase",
            "Call Supabase.initialize(...) in main() before runApp().",
        ))
    auth_listener_found = False
    for path in _find_files(project_root, "lib/**/*.dart"):
        if "onAuthStateChange" in _read(path):
            auth_listener_found = True
            break
    if not auth_listener_found:
        findings.append(_break(
            "AUTH",
            "lib/**/*.dart",
            "onAuthStateChange",
            "No onAuthStateChange listener — users stay on login screen after auth",
            "Subscribe to Supabase.instance.client.auth.onAuthStateChange and route on session changes.",
        ))

    # ENV_JSON_CHAIN
    env_missing = True
    if env_content:
        try:
            data = json.loads(env_content)
            env_missing = not (data.get("SUPABASE_URL") and data.get("SUPABASE_ANON_KEY"))
        except Exception:
            env_missing = True
    if env_missing:
        findings.append(_break(
            "ENV",
            "env.json",
            "SUPABASE_URL,SUPABASE_ANON_KEY",
            "env.json missing SUPABASE_URL or SUPABASE_ANON_KEY — Supabase calls will fail",
            "Add SUPABASE_URL and SUPABASE_ANON_KEY to env.json.",
        ))
    if "env.json" not in pubspec_content:
        findings.append(_break(
            "ENV",
            "pubspec.yaml",
            "assets: env.json",
            "env.json not declared in pubspec.yaml assets — keys not loaded at runtime",
            "Declare env.json under flutter/assets in pubspec.yaml.",
        ))

    has_supabase = _has_supabase(pubspec_content)

    # SUPABASE_V2_CHAIN
    if has_supabase:
        if _is_supabase_v1(pubspec_content):
            findings.append(_break(
                "SUPABASE",
                "pubspec.yaml",
                "supabase_flutter ^2.x",
                "supabase_flutter is v1 — must upgrade to ^2.x (breaking changes in auth API)",
                "Update pubspec.yaml to supabase_flutter: ^2.x and run flutter pub get.",
            ))
        if "authCallbackUrlHostname" in main_content:
            findings.append(_break(
                "SUPABASE",
                "lib/main.dart",
                "no authCallbackUrlHostname",
                "authCallbackUrlHostname found in Supabase.initialize() — removed in v2",
                "Remove authCallbackUrlHostname from Supabase.initialize().",
            ))

    # DEEP_LINK_CHAIN
    if has_supabase and _has_auth_usage(project_root):
        manifest_content = _read(android_manifest)
        if not ("intent-filter" in manifest_content and "scheme" in manifest_content):
            findings.append(_break(
                "DEEPLINK",
                "android/app/src/main/AndroidManifest.xml",
                "intent-filter + scheme",
                "AndroidManifest.xml missing deep link intent-filter — OAuth callback won't return to app",
                "Add intent-filter with callback scheme/host for OAuth redirect.",
            ))
        ios_content = _read(ios_plist)
        if "CFBundleURLSchemes" not in ios_content:
            findings.append(_break(
                "DEEPLINK",
                "ios/Runner/Info.plist",
                "CFBundleURLSchemes",
                "Info.plist missing CFBundleURLSchemes — OAuth callback won't return to iOS app",
                "Add CFBundleURLTypes/CFBundleURLSchemes matching app callback scheme.",
            ))

    # PUBSPEC_CHAIN
    if pubspec_content:
        if not check_assets_exist(pubspec_content, project_root):
            findings.append(_break(
                "BUILD",
                "pubspec.yaml",
                "valid assets paths",
                "pubspec.yaml declares asset paths that don't exist on disk — build will fail",
                "Fix or remove invalid asset entries in pubspec.yaml.",
            ))
        if "environment:" not in pubspec_content or "sdk:" not in pubspec_content:
            findings.append(_break(
                "BUILD",
                "pubspec.yaml",
                "environment:sdk",
                "pubspec.yaml missing SDK environment constraint",
                "Add flutter SDK constraint under environment:sdk in pubspec.yaml.",
            ))

    # MIGRATIONS_CHAIN
    if has_supabase:
        migrations_dir = os.path.join(project_root, "supabase/migrations")
        if not os.path.isdir(migrations_dir):
            findings.append(_break(
                "SUPABASE",
                "supabase/migrations/",
                "directory exists",
                "supabase/migrations/ directory missing — migration scripts not pushed to Supabase",
                "Create supabase/migrations and commit SQL migrations.",
            ))

    # non-standard layout probing marker for build files
    _ = gradle if os.path.exists(gradle) else gradle_kts
    return findings
