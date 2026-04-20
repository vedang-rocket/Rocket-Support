import glob
import os
import re
from typing import Dict, List


PATTERNS = [
    {
        "id": "flutter-deprecated-session",
        "regex": r"\.auth\.session\(\)",
        "issue": "Deprecated v1 auth.session() call — use .currentSession property",
        "fix": "Replace .auth.session() with .auth.currentSession",
        "confidence": "HIGH",
    },
    {
        "id": "flutter-v1-supabase-auth",
        "regex": r"SupabaseAuth\.instance",
        "issue": "SupabaseAuth.instance removed in v2 — use Supabase.instance.client.auth",
        "fix": "Replace SupabaseAuth.instance with Supabase.instance.client.auth",
        "confidence": "HIGH",
    },
    {
        "id": "flutter-missing-binding",
        "regex": r"Supabase\.initialize",
        "issue": "Supabase.initialize() called before WidgetsFlutterBinding.ensureInitialized()",
        "fix": "Add WidgetsFlutterBinding.ensureInitialized(); before Supabase.initialize()",
        "confidence": "HIGH",
    },
    {
        "id": "flutter-oauth-context-param",
        "regex": r"signInWithOAuth\([^)]*context[^)]*\)",
        "issue": "context parameter removed from signInWithOAuth() in supabase_flutter v2",
        "fix": "Remove context parameter from signInWithOAuth() call",
        "confidence": "HIGH",
    },
    {
        "id": "flutter-provider-enum-collision",
        "regex": r"Provider\.(google|github|apple|twitter|facebook|discord)",
        "issue": "Provider enum renamed to OAuthProvider in supabase_flutter v2",
        "fix": "Replace Provider.google with OAuthProvider.google (etc)",
        "confidence": "HIGH",
    },
    {
        "id": "flutter-hardcoded-supabase-key",
        "regex": r"(supabaseUrl|supabaseKey|SUPABASE_URL|SUPABASE_ANON_KEY)\s*=\s*['\"]https?://",
        "issue": "Supabase keys hardcoded in Dart file — should come from env.json",
        "fix": "Read keys from env.json: EnvConfig.supabaseUrl",
        "confidence": "MED",
    },
    {
        "id": "flutter-missing-await-supabase",
        "regex": r"(?<!await\s)(supabase\.(from|auth|storage|rpc)\()",
        "issue": "Supabase call without await — data will not be loaded, silent failure",
        "fix": "Add await before supabase call",
        "confidence": "MED",
    },
    {
        "id": "flutter-initial-session-removed",
        "regex": r"SupabaseAuth\.instance\.initialSession|initialSession",
        "issue": "initialSession removed in v2 — use Supabase.instance.client.auth.currentSession",
        "fix": "Replace initialSession with currentSession",
        "confidence": "HIGH",
    },
]


def check_binding_before(file_content: str, line_num: int) -> bool:
    lines = file_content.splitlines()
    start = max(0, line_num - 25)
    context = "\n".join(lines[start:line_num])
    return "WidgetsFlutterBinding.ensureInitialized" in context


def _result(file_path: str, line: int, spec: Dict) -> Dict:
    return {
        "file": file_path,
        "line": line,
        "pattern_id": spec["id"],
        "issue": spec["issue"],
        "fix_diff": spec["fix"],
        "confidence": spec["confidence"],
    }


def scan(repo_path: str) -> List[Dict]:
    repo_path = os.path.abspath(os.path.expanduser(repo_path))
    findings: List[Dict] = []
    files = sorted(glob.glob(os.path.join(repo_path, "lib/**/*.dart"), recursive=True))

    for path in files:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception:
            continue

        lines = content.splitlines()
        rel = os.path.relpath(path, repo_path)

        for spec in PATTERNS:
            rx = re.compile(spec["regex"])
            for idx, line in enumerate(lines, start=1):
                if not rx.search(line):
                    continue
                if spec["id"] == "flutter-missing-binding":
                    if check_binding_before(content, idx):
                        continue
                findings.append(_result(rel, idx, spec))

    return findings
