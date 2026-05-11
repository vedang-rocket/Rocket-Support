"""
probe_scanner.py — Fast AST + rg replacement for semgrep Layer 1.

Outputs findings in semgrep-compatible dict format so fix_writer.py
and format_output.py work with zero changes.

Rule mapping:
  Rule 1 (getsession-to-getuser)      → ast-grep-py (rg fallback)
  Rule 2 (auth-helpers-deprecated)    → rg
  Rule 3 (middleware-wrong-location)  → SKIP — chain_walker handles
  Rule 4 (stripe-webhook-json)        → rg + path glob
  Rule 5 (supabase-wrong-import)      → rg + path glob
  Rule 6 (cookies-without-await)      → ast-grep-py (rg fallback)
  Rule 7 (next-public-secret-key)     → rg + path glob
  Rule 13 (client-no-storage-fallback)→ rg + file-content check
"""

import os
import json
import shutil
import subprocess
from typing import Any, Dict, List, Optional

import tracer as _tracer

_RG  = shutil.which("rg")  or "/usr/local/bin/rg"
_FD  = shutil.which("fd")  or "/usr/local/bin/fd"

try:
    from ast_grep_py import SgRoot
    _AST_GREP_AVAILABLE = True
except ImportError:
    _AST_GREP_AVAILABLE = False

_SKIP_DIRS = {"node_modules", ".next", ".git", "__pycache__", "dist", ".turbo",
              ".rkt_snapshot", ".swarm", ".claude-flow"}


# ── Finding factory ───────────────────────────────────────────────────────────

def _make_finding(
    check_id: str,
    path: str,
    start_line: int,
    start_col: int,
    end_line: int,
    end_col: int,
    message: str,
    severity: str = "ERROR",
    fix: str = "",
    category: str = "OTHER",
    confidence: str = "HIGH",
) -> Dict[str, Any]:
    return {
        "check_id": check_id,
        "path": path,
        "start": {"line": start_line, "col": start_col},
        "end":   {"line": end_line,   "col": end_col},
        "extra": {
            "message": message,
            "severity": severity,
            "fix": fix,
            "metadata": {"category": category, "confidence": confidence},
        },
    }


# ── File collection ───────────────────────────────────────────────────────────

def _collect_ts_files(repo_path: str) -> List[str]:
    """Collect .ts/.tsx/.js/.jsx files, skipping build/dep directories."""
    if shutil.which("fd"):
        try:
            r = subprocess.run(
                [_FD, "--type", "f",
                 "-e", "ts", "-e", "tsx", "-e", "js", "-e", "jsx",
                 "--exclude", "node_modules", "--exclude", ".next",
                 "--exclude", "dist", "--exclude", ".turbo",
                 ".", repo_path],
                capture_output=True, text=True, timeout=10,
            )
            files = [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
            return files
        except Exception:
            pass
    # os.walk fallback
    files: List[str] = []
    for root, dirs, fnames in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
        for fname in fnames:
            if fname.endswith((".ts", ".tsx", ".js", ".jsx")):
                files.append(os.path.join(root, fname))
    return files


def _run_rg(args: List[str]) -> List[Dict]:
    """Run rg --json and return parsed match objects."""
    if _tracer.get_logger() is not None:
        return _tracer.trace_rg(args)
    try:
        r = subprocess.run(
            [_RG, "--json"] + args,
            capture_output=True, text=True, timeout=10,
        )
        results = []
        for line in r.stdout.splitlines():
            try:
                obj = json.loads(line)
                if obj.get("type") == "match":
                    results.append(obj["data"])
            except Exception:
                pass
        return results
    except Exception:
        return []


# ── Rule 1: getSession → getUser ─────────────────────────────────────────────

def scan_getsession(ts_files: List[str]) -> List[Dict[str, Any]]:
    """$CLIENT.auth.getSession() → ast-grep-py; rg fallback."""
    findings: List[Dict] = []

    if _AST_GREP_AVAILABLE:
        for fpath in ts_files:
            try:
                if os.path.getsize(fpath) > 200_000:
                    continue
                with open(fpath, encoding="utf-8", errors="replace") as fh:
                    source = fh.read()
                root = SgRoot(source, "typescript")
                for m in root.root().find_all(pattern="$CLIENT.auth.getSession()"):
                    r = m.range()
                    line = r.start.line + 1
                    col  = r.start.column
                    findings.append(_make_finding(
                        check_id="supabase-getsession-not-getuser",
                        path=fpath,
                        start_line=line, start_col=col,
                        end_line=r.end.line + 1, end_col=r.end.column,
                        message=(
                            "getSession() reads cookies but does NOT validate JWT. "
                            "Use getUser() in all server-side code. (ROCKET RULE 1)"
                        ),
                        severity="ERROR",
                        fix=m.text().replace("getSession()", "getUser()"),
                        category="AUTH",
                        confidence="HIGH",
                    ))
            except Exception:
                pass
        return findings

    # rg fallback
    for match in _run_rg(["-n", r"\.auth\.getSession\(\)"] + ts_files):
        fpath = match["path"]["text"]
        lno   = match["line_number"]
        col   = match["submatches"][0]["start"] if match.get("submatches") else 0
        findings.append(_make_finding(
            check_id="supabase-getsession-not-getuser",
            path=fpath,
            start_line=lno, start_col=col,
            end_line=lno, end_col=col + 20,
            message="getSession() skips JWT validation — use getUser(). (ROCKET RULE 1)",
            severity="ERROR",
            fix=".auth.getUser()",
            category="AUTH",
        ))
    return findings


# ── Rule 2: auth-helpers deprecated ──────────────────────────────────────────

def scan_auth_helpers(repo_path: str) -> List[Dict[str, Any]]:
    """Deprecated @supabase/auth-helpers-nextjs imports → rg."""
    findings: List[Dict] = []

    _ID_MAP = {
        "auth-helpers-nextjs":          "supabase-auth-helpers-nextjs-deprecated",
        "createClientComponentClient":  "supabase-create-client-component-deprecated",
        "createServerComponentClient":  "supabase-create-server-component-deprecated",
    }
    _MSG_MAP = {
        "auth-helpers-nextjs":
            "@supabase/auth-helpers-nextjs is deprecated. Use @supabase/ssr. (ROCKET RULE 4)",
        "createClientComponentClient":
            "createClientComponentClient() removed — use createBrowserClient() from @supabase/ssr.",
        "createServerComponentClient":
            "createServerComponentClient() removed — use createServerClient() from @supabase/ssr.",
    }

    pattern = r"auth-helpers-nextjs|createClientComponentClient|createServerComponentClient"
    for match in _run_rg(["-n", pattern, "--glob", "*.ts", "--glob", "*.tsx",
                          "--glob", "*.js", "--glob", "*.jsx", repo_path]):
        fpath = match["path"]["text"]
        lno   = match["line_number"]
        col   = match["submatches"][0]["start"] if match.get("submatches") else 0
        text  = match["lines"]["text"] if match.get("lines") else ""
        key   = next((k for k in _ID_MAP if k in text), "auth-helpers-nextjs")
        findings.append(_make_finding(
            check_id=_ID_MAP[key],
            path=fpath,
            start_line=lno, start_col=col,
            end_line=lno, end_col=col + len(key),
            message=_MSG_MAP[key],
            severity="ERROR",
            fix="@supabase/ssr",
            category="AUTH",
        ))
    return findings


# ── Rule 3 (middleware-wrong-location): SKIP — chain_walker handles ───────────


# ── Rule 4: Stripe webhook request.json() ────────────────────────────────────

def scan_stripe_webhook(repo_path: str) -> List[Dict[str, Any]]:
    """await request.json() in webhook files → rg with path globs."""
    findings: List[Dict] = []
    globs = ["*webhook*", "*stripe*", "*/webhooks/*", "*/webhook/*"]
    glob_args: List[str] = []
    for g in globs:
        glob_args += ["--glob", g]

    pattern = r"await\s+\w+\.json\(\)"
    for match in _run_rg(["-n", pattern] + glob_args + [repo_path]):
        fpath = match["path"]["text"]
        lno   = match["line_number"]
        col   = match["submatches"][0]["start"] if match.get("submatches") else 0
        findings.append(_make_finding(
            check_id="stripe-webhook-request-json",
            path=fpath,
            start_line=lno, start_col=col,
            end_line=lno, end_col=col + 20,
            message=(
                "Stripe webhook body must be raw text. request.json() destroys raw bytes "
                "→ constructEvent() always fails with 400. Use request.text(). (ROCKET RULE 2)"
            ),
            severity="ERROR",
            fix="await request.text()",
            category="STRIPE",
        ))
    return findings


# ── Rule 5: @supabase/supabase-js in server files ────────────────────────────

def scan_supabase_wrong_import(repo_path: str) -> List[Dict[str, Any]]:
    """@supabase/supabase-js in server-side files → rg with path globs."""
    findings: List[Dict] = []
    globs = [
        "**/server.ts", "**/route.ts", "**/route.tsx",
        "**/page.tsx", "**/layout.tsx", "**/actions.ts",
        "**/lib/supabase/**", "**/utils/supabase/**",
    ]
    glob_args: List[str] = []
    for g in globs:
        glob_args += ["--glob", g]

    for pattern in [r"from '@supabase/supabase-js'", r'from "@supabase/supabase-js"']:
        for match in _run_rg(["-n", pattern] + glob_args + [repo_path]):
            fpath = match["path"]["text"]
            lno   = match["line_number"]
            col   = match["submatches"][0]["start"] if match.get("submatches") else 0
            findings.append(_make_finding(
                check_id="supabase-js-in-server-file",
                path=fpath,
                start_line=lno, start_col=col,
                end_line=lno, end_col=col + 30,
                message=(
                    "In server components/routes/actions, use createServerClient from "
                    "@supabase/ssr, not createClient from @supabase/supabase-js. "
                    "Browser client does not handle cookie-based auth. (ROCKET RULE 4)"
                ),
                severity="WARNING",
                fix="@supabase/ssr",
                category="AUTH",
                confidence="MED",
            ))
    return findings


# ── Rule 13: createBrowserClient without localStorage fallback ───────────────

def scan_client_storage_fallback(repo_path: str) -> List[Dict[str, Any]]:
    """client.ts uses createBrowserClient without localStorage fallback."""
    findings: List[Dict] = []
    seen_files = set()
    matches = _run_rg(
        [
            "-n",
            r"createBrowserClient\s*\(",
            "--glob",
            "lib/supabase/client.ts",
            "--glob",
            "src/lib/supabase/client.ts",
            repo_path,
        ]
    )
    for match in matches:
        fpath = match["path"]["text"]
        if fpath in seen_files:
            continue
        seen_files.add(fpath)
        try:
            with open(fpath, encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except OSError:
            continue
        if "localStorage" in content or "localstorage" in content.lower():
            continue
        lno = match["line_number"]
        col = match["submatches"][0]["start"] if match.get("submatches") else 0
        findings.append(
            _make_finding(
                check_id="supabase-client-no-storage-fallback",
                path=fpath,
                start_line=lno,
                start_col=col,
                end_line=lno,
                end_col=col + 20,
                message=(
                    "createBrowserClient in client.ts has no localStorage fallback; "
                    "refresh token can fail when third-party cookies are blocked."
                ),
                severity="WARNING",
                fix="Add cookies.getAll/setAll with localStorage fallback in createBrowserClient options",
                category="AUTH",
                confidence="MED",
            )
        )
    return findings


# ── Rule 6: cookies() without await ──────────────────────────────────────────

def scan_cookies_without_await(ts_files: List[str]) -> List[Dict[str, Any]]:
    """const/let $STORE = cookies() without await → ast-grep-py; rg fallback."""
    findings: List[Dict] = []

    if _AST_GREP_AVAILABLE:
        patterns = [
            ("const $STORE = cookies()", "cookies-without-await-const"),
            ("let $STORE = cookies()",   "cookies-without-await-let"),
        ]
        for fpath in ts_files:
            try:
                if os.path.getsize(fpath) > 200_000:
                    continue
                with open(fpath, encoding="utf-8", errors="replace") as fh:
                    source = fh.read()
                root = SgRoot(source, "typescript")
                for pat, cid in patterns:
                    for m in root.root().find_all(pattern=pat):
                        text = m.text()
                        if "await" in text:
                            continue
                        r = m.range()
                        line = r.start.line + 1
                        col  = r.start.column
                        fixed = text.replace("= cookies()", "= await cookies()")
                        findings.append(_make_finding(
                            check_id=cid,
                            path=fpath,
                            start_line=line, start_col=col,
                            end_line=r.end.line + 1, end_col=r.end.column,
                            message=(
                                "cookies() must be awaited in Next.js 15. Without await you get "
                                "a Promise, not the cookie store — silent auth failure. (ROCKET RULE 5)"
                            ),
                            severity="ERROR",
                            fix=fixed,
                            category="AUTH",
                        ))
            except Exception:
                pass
        return findings

    # rg fallback — match unawaited cookies() assignment
    pattern = r"(?:const|let)\s+\w+\s*=\s*cookies\(\)"
    for match in _run_rg(["-n", pattern] + ts_files):
        fpath = match["path"]["text"]
        lno   = match["line_number"]
        col   = match["submatches"][0]["start"] if match.get("submatches") else 0
        text  = match["lines"]["text"] if match.get("lines") else ""
        if "await" in text:
            continue
        cid = "cookies-without-await-let" if text.lstrip().startswith("let") else "cookies-without-await-const"
        findings.append(_make_finding(
            check_id=cid,
            path=fpath,
            start_line=lno, start_col=col,
            end_line=lno, end_col=col + 20,
            message="cookies() must be awaited in Next.js 15. (ROCKET RULE 5)",
            severity="ERROR",
            fix=text.replace("= cookies()", "= await cookies()").strip(),
            category="AUTH",
        ))
    return findings


# ── Rule 9: headers() without await ──────────────────────────────────────────

def scan_headers_without_await(ts_files: List[str]) -> List[Dict[str, Any]]:
    """const/let $H = headers() without await → ast-grep-py; rg fallback."""
    findings: List[Dict] = []

    if _AST_GREP_AVAILABLE:
        patterns = [
            ("const $H = headers()", "headers-without-await-const"),
            ("let $H = headers()",   "headers-without-await-let"),
        ]
        for fpath in ts_files:
            try:
                if os.path.getsize(fpath) > 200_000:
                    continue
                with open(fpath, encoding="utf-8", errors="replace") as fh:
                    source = fh.read()
                root = SgRoot(source, "typescript")
                for pat, cid in patterns:
                    for m in root.root().find_all(pattern=pat):
                        text = m.text()
                        if "await" in text:
                            continue
                        r = m.range()
                        line = r.start.line + 1
                        col  = r.start.column
                        fixed = text.replace("= headers()", "= await headers()")
                        findings.append(_make_finding(
                            check_id="headers-without-await",
                            path=fpath,
                            start_line=line, start_col=col,
                            end_line=r.end.line + 1, end_col=r.end.column,
                            message=(
                                "headers() must be awaited in Next.js 15. Without await you get "
                                "a Promise, not the headers object — silent failure. (ROCKET RULE 5)"
                            ),
                            severity="ERROR",
                            fix=fixed,
                            category="AUTH",
                        ))
            except Exception:
                pass
        return findings

    # rg fallback
    pattern = r"(?:const|let)\s+\w+\s*=\s*headers\(\)"
    for match in _run_rg(["-n", pattern] + ts_files):
        fpath = match["path"]["text"]
        lno   = match["line_number"]
        col   = match["submatches"][0]["start"] if match.get("submatches") else 0
        text  = match["lines"]["text"] if match.get("lines") else ""
        if "await" in text:
            continue
        findings.append(_make_finding(
            check_id="headers-without-await",
            path=fpath,
            start_line=lno, start_col=col,
            end_line=lno, end_col=col + 20,
            message="headers() must be awaited in Next.js 15. (ROCKET RULE 5)",
            severity="ERROR",
            fix=text.replace("= headers()", "= await headers()").strip(),
            category="AUTH",
        ))
    return findings


# ── Rule 7: NEXT_PUBLIC_ on secret keys ──────────────────────────────────────

def scan_env_secrets(repo_path: str) -> List[Dict[str, Any]]:
    """NEXT_PUBLIC_ prefix on secret env vars in .env files → rg."""
    findings: List[Dict] = []
    env_globs = [".env", ".env.local", ".env.production", ".env.development", ".env.example"]
    glob_args: List[str] = []
    for g in env_globs:
        glob_args += ["--glob", g]

    pattern = r"NEXT_PUBLIC_[A-Z_]*(SERVICE_ROLE|SECRET|PRIVATE_KEY|WEBHOOK_SECRET|JWT_SECRET|STRIPE_SECRET)[A-Z_]*\s*="
    for match in _run_rg(["-n", pattern, "--pcre2"] + glob_args + [repo_path]):
        fpath = match["path"]["text"]
        lno   = match["line_number"]
        col   = match["submatches"][0]["start"] if match.get("submatches") else 0
        line_text = match["lines"]["text"].strip() if match.get("lines") else ""
        key = line_text.split("=")[0].strip()
        findings.append(_make_finding(
            check_id="next-public-service-role-key",
            path=fpath,
            start_line=lno, start_col=col,
            end_line=lno, end_col=col + len(key),
            message=(
                f"{key} must NOT have NEXT_PUBLIC_ prefix — exposed in browser bundle. "
                "Leaked service_role key bypasses Row Level Security. (ROCKET RULE 6)"
            ),
            severity="ERROR",
            fix=key.replace("NEXT_PUBLIC_", ""),
            category="ENV",
        ))
    return findings


# ── Rule 8: Missing force-dynamic on authenticated pages ────────────────────

def scan_missing_dynamic_export(repo_path: str) -> List[Dict[str, Any]]:
    """page.tsx/layout.tsx calling getUser() without force-dynamic export → rg."""
    findings: List[Dict] = []
    globs = ["**/page.tsx", "**/page.ts", "**/layout.tsx"]
    glob_args: List[str] = []
    for g in globs:
        glob_args += ["--glob", g]

    for match in _run_rg(["-n", r"auth\.getUser\(\)"] + glob_args + [repo_path]):
        fpath = match["path"]["text"]
        lno   = match["line_number"]
        col   = match["submatches"][0]["start"] if match.get("submatches") else 0
        # Check if the file already has force-dynamic
        try:
            with open(fpath, encoding="utf-8", errors="replace") as fh:
                content = fh.read()
            if "force-dynamic" in content:
                continue
        except OSError:
            continue
        findings.append(_make_finding(
            check_id="supabase-missing-dynamic-export",
            path=fpath,
            start_line=lno, start_col=col,
            end_line=lno, end_col=col + 20,
            message=(
                "ROCKET RULE 8: Authenticated pages must export const dynamic = 'force-dynamic'. "
                "Without it Next.js may cache the page and serve stale auth state."
            ),
            severity="WARNING",
            fix="export const dynamic = 'force-dynamic'",
            category="AUTH",
            confidence="HIGH",
        ))
    return findings


# ── Rule 10: New Supabase anon key format ─────────────────────────────────────

def scan_anon_key_format(repo_path: str) -> List[Dict[str, Any]]:
    """NEXT_PUBLIC_SUPABASE_ANON_KEY starting with eyJ (old JWT format) in .env files → rg."""
    findings: List[Dict] = []
    env_globs = [".env", ".env.local", ".env.production", ".env.development"]
    glob_args: List[str] = []
    for g in env_globs:
        glob_args += ["--glob", g]

    pattern = r"NEXT_PUBLIC_SUPABASE_ANON_KEY\s*=\s*eyJ"
    for match in _run_rg(["-n", pattern] + glob_args + [repo_path]):
        fpath = match["path"]["text"]
        lno   = match["line_number"]
        col   = match["submatches"][0]["start"] if match.get("submatches") else 0
        findings.append(_make_finding(
            check_id="supabase-new-project-anon-key-name",
            path=fpath,
            start_line=lno, start_col=col,
            end_line=lno, end_col=col + 30,
            message=(
                "ROCKET RULE 10: Post-Nov 2025 Supabase projects use sb_publishable_ key format, not eyJ JWT. "
                "Check Supabase Dashboard → Settings → API → Project API keys."
            ),
            severity="INFO",
            fix="",
            category="SUPABASE",
            confidence="HIGH",
        ))
    return findings


# ── Rule 11: 'use client' + server-only import ───────────────────────────────

def scan_use_client_server_import(repo_path: str) -> List[Dict[str, Any]]:
    """'use client' files that import server-only supabase/ssr exports → rg."""
    findings: List[Dict] = []
    server_only_imports = [
        "createServerClient",
        "createRouteHandlerClient",
    ]
    pattern = "|".join(server_only_imports)
    globs = ["**/page.tsx", "**/page.ts", "**/layout.tsx",
             "**/components/**/*.tsx", "**/components/**/*.ts"]
    glob_args: List[str] = []
    for g in globs:
        glob_args += ["--glob", g]

    for match in _run_rg(["-n", pattern] + glob_args + [repo_path]):
        fpath = match["path"]["text"]
        lno   = match["line_number"]
        try:
            with open(fpath, encoding="utf-8", errors="replace") as fh:
                first_500 = fh.read(500)
            if "use client" not in first_500:
                continue
        except OSError:
            continue
        col = match["submatches"][0]["start"] if match.get("submatches") else 0
        matched_text = match["lines"]["text"].strip() if match.get("lines") else ""
        findings.append(_make_finding(
            check_id="use-client-server-import",
            path=fpath,
            start_line=lno, start_col=col,
            end_line=lno, end_col=col + 25,
            message=(
                f"'use client' file imports server-only function ({matched_text}). "
                "This causes a build failure. Use createBrowserClient for client components."
            ),
            severity="ERROR",
            fix="Replace with createBrowserClient from '@supabase/ssr'",
            category="AUTH",
        ))
    return findings


# ── Rule 12: Server Action missing revalidatePath ─────────────────────────────

def scan_missing_revalidate(ts_files: List[str]) -> List[Dict[str, Any]]:
    """'use server' files with .update()/.insert()/.delete() but no revalidatePath."""
    findings: List[Dict] = []
    import re as _re
    mutation_pattern = r"\.(?:update|insert|delete|upsert)\s*\("

    for fpath in ts_files:
        try:
            with open(fpath, encoding="utf-8", errors="replace") as fh:
                first_300 = fh.read(300)
            if "use server" not in first_300:
                continue
        except OSError:
            continue

        try:
            with open(fpath, encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except OSError:
            continue

        has_mutation  = bool(_re.search(mutation_pattern, content))
        has_revalidate = "revalidatePath" in content or "revalidateTag" in content
        if has_mutation and not has_revalidate:
            lno = next(
                (i + 1 for i, line in enumerate(content.splitlines())
                 if _re.search(mutation_pattern, line)),
                1,
            )
            findings.append(_make_finding(
                check_id="server-action-missing-revalidate",
                path=fpath,
                start_line=lno, start_col=0,
                end_line=lno, end_col=0,
                message=(
                    "Server Action mutates data but has no revalidatePath() or revalidateTag(). "
                    "Next.js will serve stale cached data after the mutation."
                ),
                severity="WARNING",
                fix="import { revalidatePath } from 'next/cache'; revalidatePath('/your-path')",
                category="BUILD",
            ))
    return findings


# ── Main entry point ──────────────────────────────────────────────────────────

def run_probe_scanner(repo_path: str) -> Dict[str, Any]:
    """
    Run all probe scanners. Returns semgrep-compatible result dict.
    All exceptions are caught per scanner — one failing scanner
    never aborts the others.
    """
    ts_files = _collect_ts_files(repo_path)
    findings: List[Dict] = []
    errors:   List[str]  = []

    # AST-based scanners (need ts_files list)
    for fn in (scan_getsession, scan_cookies_without_await, scan_headers_without_await,
               scan_missing_revalidate):
        try:
            findings.extend(fn(ts_files))
        except Exception as exc:
            errors.append(f"{fn.__name__}: {exc}")

    # rg-based scanners (need repo_path)
    for fn in (scan_auth_helpers, scan_stripe_webhook, scan_supabase_wrong_import,
               scan_client_storage_fallback, scan_env_secrets, scan_missing_dynamic_export, scan_anon_key_format,
               scan_use_client_server_import):
        try:
            findings.extend(fn(repo_path))
        except Exception as exc:
            errors.append(f"{fn.__name__}: {exc}")

    return {
        "available": True,
        "findings": findings,
        "errors": errors,
        "autofix_applied": False,
        "scanner": "probe",
    }
