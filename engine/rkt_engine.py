"""
rkt_engine.py — Main orchestrator for the Rocket.new intelligent fix engine.

Pipeline — ALL layers always run, no early exits:
  Layer 0: chain_walker   → structural break check (< 1s, no subprocess)
  Layer 1: Semgrep        → AST-level autofix scan + file-system checks
  Layer 2: Fix database   → vector similarity search for known patterns
  Layer 3: Combined report → all findings from all layers shown together

Output order:
  1. Chain walker findings  → ROOT CAUSE (shown first)
  2. Semgrep violations     → ADDITIONAL ISSUES
  3. DB match               → KNOWN FIX

Every fix path saves results to brain.db.
"""

import os
import sys
import json
import subprocess
import shutil
import tempfile
import datetime
import time
import re
from typing import Dict, Any, List, Optional, Tuple

# Add engine dir to path
ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ENGINE_DIR)

import db as fix_db
import fingerprint as fp
import chain_walker
import schema_checker
import context_extractor

RULES_DIR = os.path.join(ENGINE_DIR, "rules")
RKT_HOME = os.path.expanduser("~/rocket-support")
CLAUDE_MD = os.path.join(RKT_HOME, "CLAUDE.md")


# ── ANSI colours ─────────────────────────────────────────────────────────────

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m"

OK   = lambda t: _c("0;32", f"OK  {t}")
INFO = lambda t: _c("0;34", f">>  {t}")
WARN = lambda t: _c("0;33", f"!   {t}")
ERR  = lambda t: _c("0;31", f"ERR {t}")
STEP = lambda t: _c("1;36", f"\n── {t} ──")


_SENSITIVE_ENV_KEY_RE = re.compile(
    r"^([A-Za-z_][A-Za-z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD|PRIVATE|WEBHOOK|SERVICE_ROLE|JWT)[A-Za-z0-9_]*)=(.*)$",
    re.IGNORECASE,
)
_JWT_LIKE_RE = re.compile(r"\beyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\b")
_BEARER_RE = re.compile(r"(Bearer\s+)([A-Za-z0-9\-._~+/]+=*)", re.IGNORECASE)
_KNOWN_SECRET_PREFIX_RE = re.compile(
    r"\b(?:sk|rk|pk|sbp|sbr|xox[baprs]|ghp|github_pat)_[A-Za-z0-9_\-]{12,}\b",
    re.IGNORECASE,
)


def _redact_sensitive_text(text: str) -> str:
    if not text:
        return text
    out_lines: List[str] = []
    for line in text.splitlines(keepends=True):
        line_no_nl = line.rstrip("\n")
        m = _SENSITIVE_ENV_KEY_RE.match(line_no_nl.strip())
        if m:
            key = m.group(1)
            redacted = f"{key}=***REDACTED***"
            out_lines.append(redacted + ("\n" if line.endswith("\n") else ""))
            continue
        redacted = _JWT_LIKE_RE.sub("***REDACTED_JWT***", line_no_nl)
        redacted = _BEARER_RE.sub(r"\1***REDACTED***", redacted)
        # Redact known token/key prefixes while preserving normal identifiers.
        redacted = _KNOWN_SECRET_PREFIX_RE.sub("***REDACTED***", redacted)
        out_lines.append(redacted + ("\n" if line.endswith("\n") else ""))
    return "".join(out_lines)


# ── Semgrep runner ────────────────────────────────────────────────────────────

def run_semgrep(repo_path: str, autofix: bool = False) -> Dict[str, Any]:
    """
    Run semgrep with all Rocket.new rules.
    Returns dict with findings and any applied autofixes.
    """
    if not shutil.which("semgrep"):
        return {"available": False, "findings": [], "error": "semgrep not installed"}

    cmd = [
        "semgrep",
        "--config", RULES_DIR,
        "--json",
        "--quiet",
        "--no-git-ignore",
    ]
    if autofix:
        cmd.append("--autofix")

    semgrepignore_path = os.path.join(repo_path, ".semgrepignore")
    try:
        with open(semgrepignore_path, "w") as f:
            f.write(".rkt_snapshot/\nnode_modules/\n.next/\n__pycache__/\n")
    except OSError:
        semgrepignore_path = None

    try:
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=60,
        )
        output = result.stdout.strip()
        if not output:
            return {"available": True, "findings": [], "autofix_applied": autofix}

        data = json.loads(output)
        findings = data.get("results", [])
        errors = data.get("errors", [])

        return {
            "available": True,
            "findings": findings,
            "errors": errors,
            "autofix_applied": autofix,
            "raw": data,
        }
    except subprocess.TimeoutExpired:
        return {"available": True, "findings": [], "error": "semgrep timeout"}
    except json.JSONDecodeError as e:
        return {"available": True, "findings": [], "error": f"semgrep JSON parse error: {e}"}
    except Exception as e:
        return {"available": True, "findings": [], "error": str(e)}
    finally:
        if semgrepignore_path and os.path.exists(semgrepignore_path):
            try:
                os.remove(semgrepignore_path)
            except OSError:
                pass


def format_semgrep_findings(findings: List[Dict]) -> str:
    """Format semgrep findings as readable output."""
    if not findings:
        return ""
    lines = []
    for f in findings:
        rule_id = f.get("check_id", "unknown").split(".")[-1]
        path = f.get("path", "unknown")
        start = f.get("start", {})
        line = start.get("line", "?")
        msg = _redact_sensitive_text(
            f.get("extra", {}).get("message", "").split("\n")[0][:100]
        )
        lines.append(f"  [{rule_id}] {path}:{line} — {msg}")
    return "\n".join(lines)


def semgrep_to_diff(findings: List[Dict], repo_path: str) -> str:
    """Generate a diff-style summary from semgrep findings."""
    if not findings:
        return ""
    lines = ["```diff"]
    for f in findings:
        path = f.get("path", "")
        start_line = f.get("start", {}).get("line", 1)
        end_line = f.get("end", {}).get("line", start_line)
        msg = _redact_sensitive_text(
            f.get("extra", {}).get("message", "").split("\n")[0][:80]
        )
        fix = _redact_sensitive_text(f.get("extra", {}).get("fix", ""))
        original = _redact_sensitive_text(f.get("extra", {}).get("lines", "").strip())

        lines.append(f"--- a/{path}")
        lines.append(f"+++ b/{path}")
        lines.append(f"@@ -{start_line} +{start_line} @@  # {msg}")
        if original:
            lines.append(f"-{original}")
        if fix:
            lines.append(f"+{fix}")
    lines.append("```")
    return "\n".join(lines)


# ── Database lookup ───────────────────────────────────────────────────────────

def db_lookup(query: str, category: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Look up similar fixes in the database. Returns best match or None."""
    fix_db.init_db()
    results = fix_db.find_similar(query, top_k=3, category=category)
    if not results:
        return None
    best = results[0]
    # Only return if score is meaningful
    if best.get("_score", 0) < 0.15:
        return None
    return best


# ── File-system checks (supplementing semgrep) ───────────────────────────────

def fs_checks(repo_path: str) -> List[Dict[str, str]]:
    """
    File-system level checks that can't be done with semgrep AST patterns.
    Returns list of issues: [{rule, severity, message, fix}]
    """
    issues = []

    # Rule 3: middleware.ts location
    middleware_in_app = any(
        os.path.exists(os.path.join(repo_path, p))
        for p in ["app/middleware.ts", "app/middleware.js", "src/app/middleware.ts"]
    )
    middleware_at_root = any(
        os.path.exists(os.path.join(repo_path, p))
        for p in ["middleware.ts", "middleware.js", "src/middleware.ts"]
    )
    if middleware_in_app:
        issues.append({
            "rule": "ROCKET-3",
            "severity": "ERROR",
            "message": "middleware.ts found inside /app — must be at project root",
            "fix": "Move app/middleware.ts → middleware.ts (or src/middleware.ts if using src dir)",
        })
    elif not middleware_at_root:
        # Check if there's any auth in the project that needs middleware
        has_auth = any(
            os.path.exists(os.path.join(repo_path, p))
            for p in ["lib/supabase/server.ts", "lib/supabase/middleware.ts", "utils/supabase.ts"]
        )
        if has_auth:
            issues.append({
                "rule": "ROCKET-3",
                "severity": "WARNING",
                "message": "middleware.ts not found at project root — auth redirects won't work",
                "fix": "Create middleware.ts at project root with updateSession pattern",
            })

    # Rule 6: NEXT_PUBLIC_ on secrets in .env files
    for env_file in [".env", ".env.local", ".env.production", ".env.development"]:
        env_path = os.path.join(repo_path, env_file)
        if not os.path.exists(env_path):
            continue
        try:
            with open(env_path) as f:
                for i, line in enumerate(f, 1):
                    line = line.strip()
                    if line.startswith("#") or "=" not in line:
                        continue
                    key = line.split("=")[0]
                    if key.startswith("NEXT_PUBLIC_") and any(
                        bad in key.upper()
                        for bad in ["SERVICE_ROLE", "SECRET", "PRIVATE", "WEBHOOK_SECRET", "JWT"]
                    ):
                        issues.append({
                            "rule": "ROCKET-6",
                            "severity": "ERROR",
                            "message": f"{env_file}:{i} — {key} has NEXT_PUBLIC_ prefix on a secret key",
                            "fix": f"Rename {key} → {key.replace('NEXT_PUBLIC_', '')} (remove browser exposure)",
                        })
        except Exception:
            pass

    return issues


# ── Claude Code headless fallback ─────────────────────────────────────────────

def build_claude_prompt(
    repo_path: str,
    hint: str,
    fingerprint_result: Dict[str, Any],
    semgrep_findings: List[Dict],
    db_match: Optional[Dict],
) -> str:
    """Build an enhanced prompt for Claude Code with all context pre-loaded."""

    project_type = fingerprint_result.get("project_type", "Unknown")
    common_failure = fingerprint_result.get("common_failure", "")
    has_supabase = fingerprint_result.get("has_supabase", False)
    has_stripe = fingerprint_result.get("has_stripe", False)
    next_ver = fingerprint_result.get("next_version", "")
    env_vars = fingerprint_result.get("env_vars", {})

    # Build env var status
    env_status = "\n".join(
        f"  {'✓' if ok else '✗'} {var}"
        for var, ok in env_vars.items()
    )

    # Build pre-context from engine findings
    engine_context = f"""
ENGINE PRE-ANALYSIS (already done — use this, don't re-run):
  Project type:    {project_type}
  Next.js version: {next_ver}
  Has Supabase:    {has_supabase}
  Has Stripe:      {has_stripe}
  Most likely bug: {common_failure}

ENV VAR STATUS:
{env_status}
"""
    if semgrep_findings:
        engine_context += f"\nSEMGREP FINDINGS ({len(semgrep_findings)} issues):\n"
        engine_context += format_semgrep_findings(semgrep_findings) + "\n"

    if db_match:
        engine_context += f"\nDB MATCH (similar past fix, {db_match.get('uses', 0)} uses):\n"
        engine_context += f"  Pattern: {_redact_sensitive_text(db_match.get('pattern', ''))}\n"
        engine_context += f"  Signature: {_redact_sensitive_text(db_match.get('error_signature', ''))}\n"

    prompt = f"""{engine_context}
You are a Rocket.new support engineer. Complete the diagnosis and output the fix.

STEP 1 - Run these targeted checks:
  grep -rn "getSession()" ./app ./lib ./middleware.ts 2>/dev/null | head -5
  ls middleware.ts 2>/dev/null && echo "middleware: ROOT OK" || echo "middleware: MISSING FROM ROOT"
  ls app/middleware.ts 2>/dev/null && echo "middleware: WRONG in /app" || true
  grep -rn "request.json()" ./app/api/webhooks 2>/dev/null | head -3
  grep -rn "auth-helpers-nextjs" ./package.json 2>/dev/null
  npx tsc --noEmit 2>&1 | head -10

STEP 2 - Read relevant files (based on project type {project_type}):
  - lib/supabase/server.ts or utils/supabase/server.ts
  - middleware.ts (if exists)
  - app/api/webhooks/*/route.ts (if {has_stripe})

STEP 3 - Output EXACTLY this format:

## ROOT CAUSE
[One sentence — specific, not vague]

## CATEGORY
[AUTH | SUPABASE | STRIPE | BUILD | ENV | OTHER]

## FIX
[2-3 sentences on what changed and why]

## FILES CHANGED
- filename: what changed

## DIFF
```diff
[complete unified diff — no ellipsis, full file content if changed]
```

## VERIFY
```bash
[command to confirm fix works]
```

## IF STILL BROKEN
[One specific fallback]
"""

    if hint:
        prompt += f"\nCLIENT HINT: {hint}"

    return prompt


def report_findings(
    repo_path: str,
    semgrep_findings: List[Dict],
    fs_issues: List[Dict],
    db_match: Optional[Dict],
) -> bool:
    """
    Print a clear summary of what semgrep + DB found.
    Returns True if anything was found, False if nothing detected.
    Claude diagnosis is always done via `rkt`, never via subprocess here.
    """
    all_issues = semgrep_findings + fs_issues
    repo_name = os.path.basename(repo_path)

    if all_issues or db_match:
        print(f"\n{_c('1;32', '── Findings Summary ──')}", flush=True)

        if semgrep_findings:
            print(INFO(f"Semgrep: {len(semgrep_findings)} violation(s) detected:"), flush=True)
            for f in semgrep_findings:
                rule = f.get("check_id", "").split(".")[-1]
                path = f.get("path", "")
                line = f.get("start", {}).get("line", "?")
                fix  = f.get("extra", {}).get("fix", "")
                msg  = f.get("extra", {}).get("message", "").split("\n")[0][:80]
                print(f"  [{rule}] {path}:{line}", flush=True)
                print(f"    {_redact_sensitive_text(msg)}", flush=True)
                if fix:
                    print(f"    autofix: {_redact_sensitive_text(fix[:60])}", flush=True)

        if fs_issues:
            print(INFO(f"File-system: {len(fs_issues)} issue(s):"), flush=True)
            for issue in fs_issues:
                print(f"  [{issue['rule']}] {issue['message']}", flush=True)
                print(f"    fix: {_redact_sensitive_text(issue['fix'])}", flush=True)

        if db_match:
            score = db_match.get("_score", 0)
            print(INFO(f"DB match ({score:.0%} similarity): {db_match.get('pattern', '')[:70]}"), flush=True)
            print(
                f"  Signature: {_redact_sensitive_text(db_match.get('error_signature', '')[:80])}",
                flush=True,
            )
            diff = db_match.get("fix_diff", "")
            if diff:
                print(f"\n{_redact_sensitive_text(diff[:500])}", flush=True)

        print(f"\n{_c('1;33', f'Run:  rkt {repo_name}  for full Claude diagnosis')}", flush=True)
        return True
    else:
        print(INFO("No patterns detected by semgrep or fix database."), flush=True)
        print(f"{_c('1;33', f'Run:  rkt {repo_name}  for full Claude diagnosis')}", flush=True)
        return False


# ── Chain walker helpers ──────────────────────────────────────────────────────

def _save_chain_to_db(repo_path: str, findings: List[Dict[str, Any]]):
    """Persist chain_walker findings to brain.db."""
    if not findings:
        return
    fix_db.init_db()
    for finding in findings:
        fix_db.save_fix(
            pattern=finding["issue"],
            error_signature=f"{finding['missing']} not found in {finding['broken_at']}",
            category=finding["chain"],
            fix_diff=finding["fix_hint"],
            project_type="Unknown",
            verified=0,
        )


# ── Combined findings report ──────────────────────────────────────────────────

_CONF_LABEL = {
    "HIGH": _c("0;32", "[HIGH]") + " autofix applied ✓",
    "MED":  _c("1;33", "[MED] ") + " autofix applied — verify manually",
    "LOW":  _c("0;31", "[LOW] ") + " diff shown — apply manually",
}


def _classify_confidence(finding: Dict, source: str) -> str:
    """Return 'HIGH', 'MED', or 'LOW' for a finding.

    source: 'chain_walker' | 'semgrep' | 'fs' | 'schema'
    """
    if source == "semgrep":
        rule = finding.get("check_id", "").lower()
        if any(k in rule for k in ("webhook-body", "auth-helpers", "cookies-await")):
            return "HIGH"
        return "MED"

    if source == "chain_walker":
        chain = finding.get("chain", "")
        broken_at = finding.get("broken_at", "").lower()
        if chain == "STRIPE":
            return "HIGH"   # request.text() — single string swap
        if chain == "AUTH":
            # Import swap in server.ts = HIGH; middleware restructure = LOW
            if "server" in broken_at:
                return "HIGH"
            if "middleware" in broken_at:
                return "LOW"
            return "MED"
        # RLS, ENV
        return "MED"

    if source == "fs":
        rule = finding.get("rule", "")
        msg  = finding.get("message", "").lower()
        if rule == "ROCKET-6":
            return "HIGH"   # env var rename only
        if "middleware" in msg:
            return "LOW"    # file move required
        return "MED"

    # schema findings
    return "MED"


def _print_all_findings(
    repo_path: str,
    cw_findings: List[Dict[str, Any]],
    semgrep_findings: List[Dict],
    fs_issues: List[Dict],
    db_match: Optional[Dict],
    kb_hits: Optional[List[Dict]] = None,
    schema_findings: Optional[List[Dict]] = None,
):
    """
    Print all findings from all layers in one structured report.
    Order: ROOT CAUSE (chain walker) → ADDITIONAL ISSUES (semgrep) → KNOWN FIX (db).
    """
    schema_findings = schema_findings or []
    repo_name = os.path.basename(repo_path)
    schema_failures = [f for f in schema_findings if not f["found"]]
    has_any = bool(cw_findings or semgrep_findings or fs_issues or db_match or schema_failures)

    if not has_any:
        print(INFO("No issues detected across all layers."), flush=True)
        print(f"{_c('1;33', f'Run:  rkt {repo_name}  for full Claude diagnosis')}", flush=True)
        return

    print(f"\n{_c('1;32', '── Findings Summary ──')}", flush=True)

    # 1. ROOT CAUSE — chain walker breaks (highest confidence, shown first)
    if cw_findings:
        print(f"\n{_c('1;31', 'ROOT CAUSE (chain_walker — confidence 1.0):')}", flush=True)
        for cw in cw_findings:
            conf = _classify_confidence(cw, "chain_walker")
            print(f"\n  {_CONF_LABEL[conf]}", flush=True)
            print(f"  [{cw['chain']}] {cw['broken_at']}", flush=True)
            print(f"  Issue:    {_redact_sensitive_text(cw['issue'])}", flush=True)
            print(f"  Missing:  {cw['missing']}", flush=True)
            print(f"  Fix:      {_redact_sensitive_text(cw['fix_hint'])}", flush=True)
            # Context window around the break location
            abs_path = os.path.join(repo_path, cw["broken_at"])
            anchor = context_extractor.find_anchor_line(abs_path, cw["missing"])
            ctx = context_extractor.extract_context(abs_path, anchor, window=15)
            block = context_extractor.format_context_block(ctx)
            if block:
                print(_redact_sensitive_text(block), flush=True)

    # 1b. SCHEMA ISSUES — SQL migration checks
    if schema_failures:
        print(f"\n{_c('1;33', f'SCHEMA ISSUES ({len(schema_failures)} missing pattern(s)):')}", flush=True)
        for sf in schema_failures:
            print(f"  [MED ] [SCHEMA] {sf['check']}", flush=True)
            print(f"    {_redact_sensitive_text(sf['fix_hint'])}", flush=True)

    # 2. ADDITIONAL ISSUES — semgrep violations
    if semgrep_findings:
        print(f"\n{_c('1;33', f'ADDITIONAL ISSUES (semgrep — {len(semgrep_findings)} violation(s)):')}", flush=True)
        for f in semgrep_findings:
            conf  = _classify_confidence(f, "semgrep")
            rule  = f.get("check_id", "").split(".")[-1]
            path  = f.get("path", "")
            line  = f.get("start", {}).get("line", "?")
            msg   = f.get("extra", {}).get("message", "").split("\n")[0][:90]
            fix   = f.get("extra", {}).get("fix", "")
            print(f"\n  {_CONF_LABEL[conf]}", flush=True)
            print(f"  [{rule}] {path}:{line}", flush=True)
            print(f"    {_redact_sensitive_text(msg)}", flush=True)
            if fix:
                print(f"    autofix: {_redact_sensitive_text(fix[:70])}", flush=True)
            # Context window around the violation line
            if isinstance(line, int):
                ctx = context_extractor.extract_context(path, line, window=10)
                block = context_extractor.format_context_block(ctx)
                if block:
                    print(_redact_sensitive_text(block), flush=True)

    if fs_issues:
        print(f"\n{_c('1;33', f'FILE-SYSTEM ISSUES ({len(fs_issues)}):')}", flush=True)
        for issue in fs_issues:
            conf = _classify_confidence(issue, "fs")
            print(f"\n  {_CONF_LABEL[conf]}", flush=True)
            print(f"  [{issue['rule']}] {issue['message']}", flush=True)
            print(f"    fix: {_redact_sensitive_text(issue['fix'])}", flush=True)

    # 3. KNOWN FIX — database match
    if db_match:
        score = db_match.get("_score", 0)
        uses_count = db_match.get("uses", 0)
        print(f"\n{_c('1;34', f'KNOWN FIX (database — {score:.0%} similarity, used {uses_count}x):')}", flush=True)
        print(f"  Pattern:   {db_match.get('pattern', '')[:80]}", flush=True)
        print(
            f"  Signature: {_redact_sensitive_text(db_match.get('error_signature', '')[:80])}",
            flush=True,
        )
        diff = db_match.get("fix_diff", "")
        if diff:
            print(f"\n{_redact_sensitive_text(diff[:400])}", flush=True)

    # 4. RELEVANT DOCS — KB search hits
    if kb_hits:
        print(f"\n{_c('1;36', 'RELEVANT DOCS (kb_search):')}", flush=True)
        for hit in kb_hits:
            print(f"  [{hit['source']}]  score={hit['score']:.3f}", flush=True)
            print(f"  {_redact_sensitive_text(hit['chunk'][:400])}", flush=True)

    print(f"\n{_c('1;33', f'Run:  rkt {repo_name}  for full Claude diagnosis')}", flush=True)


# ── Main orchestrator ─────────────────────────────────────────────────────────

def diagnose(repo_path: str, hint: str = "") -> Dict[str, Any]:
    """
    Full diagnosis pipeline.
    Returns dict with all findings and the diagnosis output.
    """
    repo_path = os.path.abspath(repo_path)
    if not os.path.isdir(repo_path):
        print(ERR(f"Repo path not found: {repo_path}"))
        sys.exit(1)

    result = {
        "repo_path": repo_path,
        "repo_name": os.path.basename(repo_path),
        "hint": hint,
        "semgrep": {},
        "fs_issues": [],
        "fingerprint": {},
        "db_match": None,
        "chain_walker": None,
        "method": None,  # "chain_walker" | "semgrep" | "db" | "claude"
        "output": "",
        "timestamp": datetime.datetime.utcnow().isoformat(),
    }

    # ── Layer 0: Chain walker ─────────────────────────────────────────────────
    print(STEP("Layer 0: chain_walker (structural breaks)"), flush=True)
    t0 = time.perf_counter()
    cw_findings = chain_walker.walk(repo_path)
    elapsed_cw = (time.perf_counter() - t0) * 1000

    result["chain_walker"] = cw_findings
    if cw_findings:
        print(INFO(f"chain_walker: {elapsed_cw:.1f}ms — {len(cw_findings)} break(s) found:"), flush=True)
        for cw in cw_findings:
            print(f"  [{cw['chain']}] {cw['broken_at']}: {cw['missing']}", flush=True)
            print(f"    {cw['issue']}", flush=True)
    else:
        print(OK(f"chain_walker: {elapsed_cw:.1f}ms — all chains pass"), flush=True)

    # ── Layer 0b: Schema checker ──────────────────────────────────────────────
    print(STEP("Layer 0b: schema_checker (SQL migration audit)"), flush=True)
    t_sc = time.perf_counter()
    schema_findings = schema_checker.check(repo_path)
    elapsed_sc = (time.perf_counter() - t_sc) * 1000
    result["schema"] = schema_findings

    if not schema_findings:
        print(INFO(f"schema_checker: {elapsed_sc:.1f}ms — no migrations dir (skipped)"), flush=True)
    else:
        schema_failures = schema_checker.failures(schema_findings)
        if schema_failures:
            print(WARN(f"schema_checker: {elapsed_sc:.1f}ms — {len(schema_failures)} issue(s):"), flush=True)
            for sf in schema_failures:
                print(f"  [SCHEMA] {sf['check']}: {sf['fix_hint']}", flush=True)
            # Persist each failure to brain.db
            fix_db.init_db()
            for sf in schema_failures:
                try:
                    fix_db.save_fix(
                        pattern=f"missing {sf['check']}",
                        error_sig=sf["check"],
                        category="SCHEMA",
                        fix_diff=sf["fix_hint"],
                        project_type=None,
                        verified=1,
                    )
                except Exception:
                    pass
        else:
            print(OK(f"schema_checker: {elapsed_sc:.1f}ms — all patterns present"), flush=True)

    # ── Layer 1: Fingerprint ──────────────────────────────────────────────────
    print(STEP("1/3 Fingerprinting project"), flush=True)
    t1 = time.perf_counter()
    fingerprint_result = fp.fingerprint(repo_path)
    result["fingerprint"] = fingerprint_result

    ptype = fingerprint_result["project_type"]
    confidence = fingerprint_result["confidence"]
    elapsed_fp = (time.perf_counter() - t1) * 1000
    print(INFO(f"fingerprint: {elapsed_fp:.1f}ms | Type: {ptype} ({confidence:.0%}) | "
               f"Next.js {fingerprint_result.get('next_version', '?')} | "
               f"Supabase: {fingerprint_result['has_supabase']} | "
               f"Stripe: {fingerprint_result['has_stripe']}"), flush=True)
    if fingerprint_result.get("used_fallback"):
        print(
            WARN(
                "fingerprint used heuristic fallback "
                f"({fingerprint_result.get('fallback_reason', 'low signal')})"
            ),
            flush=True,
        )
    print(INFO(f"Most likely failure: {fingerprint_result['common_failure']}"), flush=True)

    # ── Layer 1: Semgrep ──────────────────────────────────────────────────────
    print(STEP("2/3 Running Semgrep autofix scan"), flush=True)
    t2 = time.perf_counter()
    semgrep_result = run_semgrep(repo_path, autofix=False)
    result["semgrep"] = semgrep_result

    elapsed_sg = (time.perf_counter() - t2) * 1000
    if not semgrep_result.get("available"):
        print(WARN(f"semgrep not available — skipping (install: pip install semgrep)"), flush=True)
    else:
        findings = semgrep_result.get("findings", [])
        if findings:
            print(INFO(f"Found {len(findings)} issue(s) via semgrep:"), flush=True)
            print(format_semgrep_findings(findings), flush=True)

            # Apply autofixes
            print(INFO("Applying semgrep autofixes..."), flush=True)
            autofix_result = run_semgrep(repo_path, autofix=True)
            if autofix_result.get("findings") is not None:
                fixed_count = len(autofix_result.get("findings", []))
                print(OK(f"Semgrep applied {len(findings) - fixed_count} autofix(es)"), flush=True)
        else:
            errors = semgrep_result.get("errors", [])
            if errors:
                print(WARN(f"Semgrep ran with {len(errors)} parse error(s) (non-fatal)"), flush=True)
            else:
                print(OK(f"Semgrep: no violations ({elapsed_sg:.0f}ms)"), flush=True)

    # ── Step 2b: File-system checks ──────────────────────────────────────────
    fs_issues = fs_checks(repo_path)
    result["fs_issues"] = fs_issues
    if fs_issues:
        print(INFO(f"File-system checks: {len(fs_issues)} issue(s):"), flush=True)
        for issue in fs_issues:
            print(f"  [{issue['severity']}] [{issue['rule']}] {issue['message']}", flush=True)

    # ── Layer 2: Database lookup ──────────────────────────────────────────────
    print(STEP("3/3 Checking fix database"), flush=True)
    t3 = time.perf_counter()
    fix_db.init_db()

    query_terms = f"{hint} {ptype} {fingerprint_result['common_failure']}"
    if hint:
        query_terms = f"{hint} {query_terms}"

    db_match = db_lookup(query_terms, category=fingerprint_result.get("category"))
    result["db_match"] = db_match

    elapsed_db = (time.perf_counter() - t3) * 1000
    if db_match:
        score = db_match.get("_score", 0)
        print(OK(f"DB: {elapsed_db:.0f}ms — match (similarity: {score:.0%}, used {db_match.get('uses', 0)}x)"), flush=True)
        print(INFO(f"  Pattern:   {db_match.get('pattern', '')[:80]}"), flush=True)
    else:
        print(INFO(f"DB: {elapsed_db:.0f}ms — no strong match"), flush=True)

    # ── Layer 3: KB search + Combined findings report ────────────────────────
    print(STEP("Layer 3: Combined findings report"), flush=True)

    # KB search — query from primary issue category + project type
    kb_hits = []
    try:
        # Lazy import so missing KB dir doesn't break the engine
        import sys as _sys
        _kb_path = os.path.join(ENGINE_DIR, "kb")
        if _kb_path not in _sys.path:
            _sys.path.insert(0, _kb_path)
        from kb_search import search as _kb_search
        issue_category = (cw_findings[0]["chain"] if cw_findings else
                          _infer_category(semgrep_result.get("findings", [{}])[0].get("check_id", "") if semgrep_result.get("findings") else ""))
        kb_query = f"{issue_category} {fingerprint_result.get('project_type', '')} {hint}".strip()
        t_kb = time.perf_counter()
        kb_hits = _kb_search(kb_query, top_k=2)
        elapsed_kb = (time.perf_counter() - t_kb) * 1000
        if kb_hits:
            print(INFO(f"KB: {elapsed_kb:.0f}ms — {len(kb_hits)} relevant chunk(s)"), flush=True)
        else:
            print(INFO(f"KB: {elapsed_kb:.0f}ms — no matches"), flush=True)
    except Exception as _e:
        pass  # KB search is non-critical

    semgrep_findings = semgrep_result.get("findings", [])
    _print_all_findings(
        repo_path=repo_path,
        cw_findings=cw_findings,
        semgrep_findings=semgrep_findings,
        fs_issues=fs_issues,
        db_match=db_match,
        kb_hits=kb_hits,
        schema_findings=schema_findings,
    )

    schema_failures = schema_checker.failures(schema_findings)
    has_any = bool(cw_findings or semgrep_findings or fs_issues or db_match or schema_failures)
    result["method"] = "all-layers" if has_any else "none"

    _save_chain_to_db(repo_path, cw_findings)
    _save_to_db(repo_path, fingerprint_result, semgrep_result, fs_issues, db_match, hint)
    return result


def _print_combined_diagnosis(
    fingerprint_result: Dict,
    semgrep_result: Dict,
    fs_issues: List[Dict],
    db_match: Optional[Dict],
    hint: str,
):
    """Print a structured diagnosis from semgrep + db findings (no Claude needed)."""
    findings = semgrep_result.get("findings", [])
    all_issues = findings + fs_issues

    if not all_issues and not db_match:
        return

    # Pick the primary issue
    if findings:
        primary = findings[0]
        rule_id = primary.get("check_id", "").split(".")[-1]
        msg = primary.get("extra", {}).get("message", "").split("\n")[0]
        category = _infer_category(rule_id)
    elif fs_issues:
        primary_fs = fs_issues[0]
        msg = primary_fs["message"]
        category = _rule_to_category(primary_fs["rule"])
    elif db_match:
        msg = db_match.get("pattern", "")
        category = db_match.get("category", "OTHER")

    print(f"""
## ROOT CAUSE
{msg}

## CATEGORY
{category}

## FIX
{_build_fix_summary(findings, fs_issues, db_match)}

## FILES CHANGED
{_build_files_changed(findings, fs_issues)}

## DIFF
{semgrep_to_diff(findings, "")}

## VERIFY
```bash
npx tsc --noEmit && echo "TypeScript OK"
```

## IF STILL BROKEN
{db_match.get('error_signature', 'Check Supabase Dashboard logs for more details') if db_match else 'Run: npx tsc --noEmit to check for TypeScript errors'}
""", flush=True)


def _infer_category(rule_id: str) -> str:
    rule_id = rule_id.lower()
    if "stripe" in rule_id or "webhook" in rule_id:
        return "STRIPE"
    if "session" in rule_id or "user" in rule_id or "middleware" in rule_id or "cookie" in rule_id:
        return "AUTH"
    if "supabase" in rule_id or "rls" in rule_id:
        return "SUPABASE"
    if "env" in rule_id or "public" in rule_id:
        return "ENV"
    return "OTHER"


def _rule_to_category(rule: str) -> str:
    if "ROCKET-6" in rule:
        return "ENV"
    if "ROCKET-3" in rule:
        return "AUTH"
    return "OTHER"


def _build_fix_summary(findings: List[Dict], fs_issues: List[Dict], db_match: Optional[Dict]) -> str:
    parts = []
    for f in findings[:3]:
        fix = f.get("extra", {}).get("fix", "")
        if fix:
            parts.append(f"Semgrep autofix applied: {fix[:60]}")
    for issue in fs_issues[:2]:
        parts.append(issue.get("fix", ""))
    if not parts and db_match:
        parts.append(db_match.get("fix_diff", "")[:200])
    return "\n".join(parts) if parts else "See diff below."


def _build_files_changed(findings: List[Dict], fs_issues: List[Dict]) -> str:
    files = {}
    for f in findings:
        path = f.get("path", "")
        rule = f.get("check_id", "").split(".")[-1]
        if path:
            files[path] = files.get(path, []) + [rule]
    lines = [f"- {path}: {', '.join(rules)}" for path, rules in files.items()]
    return "\n".join(lines) if lines else "- (file-system level change required)"


def _save_to_db(
    repo_path: str,
    fingerprint_result: Dict,
    semgrep_result: Dict,
    fs_issues: List[Dict],
    db_match: Optional[Dict],
    hint: str,
):
    """Save any findings to the fix database for future lookups."""
    findings = semgrep_result.get("findings", [])
    for f in findings:
        rule_id = f.get("check_id", "").split(".")[-1]
        msg = f.get("extra", {}).get("message", "").split("\n")[0]
        fix = f.get("extra", {}).get("fix", "")
        if msg and fix:
            fix_db.save_fix(
                pattern=msg[:200],
                error_signature=hint or fingerprint_result.get("common_failure", ""),
                category=_infer_category(rule_id),
                fix_diff=f"Autofix: {fix}",
                project_type=fingerprint_result.get("project_type", "Unknown"),
                verified=0,
            )
