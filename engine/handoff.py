"""
handoff.py — Post-fix handoff report and AI-ready prompt generator.

Reads /tmp/rkt_triage_result.json and produces:
  1. A terminal summary of open (unresolved) issues grouped by file
  2. A .rkt_handoff_prompt.md in the workspace — paste into Cursor / Claude / ChatGPT

CLI:
    python3 handoff.py <workspace_path> <issue_description>
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from typing import Any, Dict, List, Optional

GREEN  = "\033[0;32m"
YELLOW = "\033[0;33m"
BLUE   = "\033[0;34m"
CYAN   = "\033[0;36m"
BOLD   = "\033[1m"
RED    = "\033[0;31m"
NC     = "\033[0m"

RESULT_FILE = "/tmp/rkt_triage_result.json"

# Findings with these fix_modes are still open after AUTO run
_OPEN_MODES = {"MANUAL", "GUIDED", "PREVIEW_ONLY"}

# Canonical fix templates for known rule ids
_MIDDLEWARE_TEMPLATE = """\
```typescript
// middleware.ts — PROJECT ROOT (never inside /app)
import { type NextRequest } from 'next/server'
import { updateSession } from '@/lib/supabase/middleware'

export async function middleware(request: NextRequest) {
  return await updateSession(request)
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico|.*\\\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)'],
}
```

Also create `lib/supabase/middleware.ts` if it does not exist:

```typescript
import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'

export async function updateSession(request: NextRequest) {
  let supabaseResponse = NextResponse.next({ request })
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() { return request.cookies.getAll() },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value))
          supabaseResponse = NextResponse.next({ request })
          cookiesToSet.forEach(({ name, value, options }) =>
            supabaseResponse.cookies.set(name, value, options)
          )
        },
      },
    }
  )
  await supabase.auth.getUser()
  return supabaseResponse
}
```"""

_HARD_RULES = """\
## Hard Rules (never violate)
1. `getUser()` not `getSession()` in server code — getSession() does not validate JWT
2. `request.text()` not `request.json()` in Stripe webhook handlers
3. `middleware.ts` at project root — never inside `/app`
4. `@supabase/ssr` only — never `@supabase/auth-helpers-nextjs` (deprecated)
5. `await cookies()` required in Next.js 15 — not optional
6. Never `NEXT_PUBLIC_` prefix on service role / secret keys
7. Always `export const dynamic = 'force-dynamic'` on authenticated pages
8. Post-Nov 2025 Supabase projects: use `sb_publishable_` key, not `anon_key`"""


def _load_result() -> Optional[Dict[str, Any]]:
    try:
        with open(RESULT_FILE) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _open_findings(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Return findings that are still open (not AUTO-applied)."""
    return [f for f in findings if f.get("fix_mode") in _OPEN_MODES or f.get("fix_mode") == "MANUAL"]


def _group_by_file(findings: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    groups: Dict[str, List] = defaultdict(list)
    for f in findings:
        file_path = f.get("file") or "(unknown file)"
        groups[file_path].append(f)
    return dict(groups)


def _conf_label(conf: float) -> str:
    if conf >= 0.90: return "HIGH"
    if conf >= 0.70: return "MED"
    return "LOW"


def _fix_block(finding: Dict[str, Any]) -> str:
    """Return a markdown fix block for a finding."""
    category = (finding.get("category") or "").lower()
    desc     = finding.get("description", "")
    hint     = finding.get("fix_hint", "")
    file_    = finding.get("file", "")

    # Middleware — provide full canonical template
    if "middleware" in category or "updatesession" in category or "middleware" in file_.lower():
        return _MIDDLEWARE_TEMPLATE

    # getSession → getUser — explain the pattern
    if "getsession" in category or "getuser" in category:
        return """\
```typescript
// Replace:
const { data: { session } } = await supabase.auth.getSession()

// With:
const { data: { user } } = await supabase.auth.getUser()
// Note: getUser() returns the user directly — session?.user becomes user
```"""

    # anon key naming
    if "anon-key" in category or "publishable" in category:
        return """\
```
# .env — rename the key variable:
# Old:  NEXT_PUBLIC_SUPABASE_ANON_KEY=...
# New:  NEXT_PUBLIC_SUPABASE_ANON_KEY=<value of sb_publishable_ key from Supabase dashboard>
# The sb_publishable_ prefix is the new format for Supabase projects created after Nov 2025.
```"""

    # Stripe webhook
    if "stripe" in category or "webhook" in category:
        return """\
```typescript
// Replace:
const body = await request.json()

// With:
const body = await request.text()
const sig = headers().get('stripe-signature')!
const event = stripe.webhooks.constructEvent(body, sig, process.env.STRIPE_WEBHOOK_SECRET!)
```"""

    # Generic: use the hint from semgrep if available
    if hint:
        return f"```typescript\n{hint}\n```"

    return f"> {desc}"


def _build_prompt(result: Dict[str, Any], open_findings: List[Dict[str, Any]]) -> str:
    fp          = result.get("fingerprint") or {}
    issue       = result.get("issue_description", "")
    project_type = fp.get("project_type", "Unknown")
    next_ver    = fp.get("next_version") or "unknown"
    has_sb      = fp.get("has_supabase", False)
    has_stripe  = fp.get("has_stripe", False)
    conf        = result.get("overall_confidence", 0)
    workspace   = result.get("workspace_path", "")

    stack_parts = [f"Next.js {next_ver} · App Router"]
    if has_sb:   stack_parts.append("Supabase (@supabase/ssr)")
    if has_stripe: stack_parts.append("Stripe")
    stack = " · ".join(stack_parts)

    lines = []
    lines.append(f"# Fix Request — {os.path.basename(workspace)} ({stack})")
    lines.append("")
    lines.append("## Context")
    lines.append(f"- **Project type:** {project_type}")
    lines.append(f"- **Stack:** {stack}")
    lines.append(f"- **Issue reported:** \"{issue}\"")
    lines.append(f"- **Triage confidence:** {conf:.0%}")
    lines.append(f"- **Workspace:** `{workspace}`")
    lines.append("")

    if not open_findings:
        lines.append("## Status")
        lines.append("All issues were resolved automatically. Run `bun run build` to verify.")
        lines.append("")
        lines.append(_HARD_RULES)
        return "\n".join(lines)

    lines.append(f"## Files to Fix ({len(open_findings)} open issue(s))")
    lines.append("")

    grouped = _group_by_file(open_findings)
    for idx, (file_path, file_findings) in enumerate(grouped.items(), 1):
        for finding in file_findings:
            line    = finding.get("line", 0)
            mode    = finding.get("fix_mode", "?")
            conf_f  = finding.get("confidence", 0.0)
            source  = finding.get("source", "")
            desc    = finding.get("description", "")
            loc     = f"`{file_path}`" + (f" (line {line})" if line else "")

            lines.append(f"### {idx}. {loc}")
            lines.append(f"**Detected by:** {source} | **Action required:** {mode} | **Confidence:** {_conf_label(conf_f)}")
            lines.append("")
            lines.append(f"**Problem:** {desc}")
            lines.append("")
            lines.append("**Required fix:**")
            lines.append("")
            lines.append(_fix_block(finding))
            lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(_HARD_RULES)
    lines.append("")
    lines.append("## Verify")
    lines.append("```bash")
    lines.append("bun run build   # must complete with zero errors")
    lines.append("```")
    lines.append("")
    lines.append("> Generated by rkt — Rocket.new Support Engine")

    return "\n".join(lines)


def _print_open_issues(open_findings: List[Dict[str, Any]]) -> None:
    if not open_findings:
        print(f"  {GREEN}✓{NC}  All issues resolved — nothing left open")
        return

    grouped = _group_by_file(open_findings)
    print(f"  {YELLOW}!{NC}  {len(open_findings)} open issue(s) need attention:\n")
    for file_path, file_findings in grouped.items():
        print(f"  {BOLD}{file_path}{NC}")
        for f in file_findings:
            line  = f.get("line", 0)
            mode  = f.get("fix_mode", "?")
            conf  = f.get("confidence", 0.0)
            desc  = f.get("description", "")[:80]
            loc   = f":{line}" if line else ""
            label = _conf_label(conf)
            print(f"  {BLUE}└─{NC} [{mode}:{label}] {file_path}{loc}")
            print(f"     {desc}")
        print()


def run(workspace_path: str, issue_description: str) -> None:
    result = _load_result()
    if not result:
        return

    findings     = result.get("findings_scored", [])
    open_findings = _open_findings(findings)

    # Terminal report
    print(f"\n{BOLD}{CYAN}── OPEN ISSUES ──{NC}")
    _print_open_issues(open_findings)

    # Write AI prompt
    prompt_path = os.path.join(workspace_path, ".rkt_handoff_prompt.md")
    prompt_text = _build_prompt(result, open_findings)

    try:
        with open(prompt_path, "w", encoding="utf-8") as f:
            f.write(prompt_text)

        print(f"{BOLD}{CYAN}── AI PROMPT ──{NC}")
        if open_findings:
            print(f"  {GREEN}✓{NC}  Prompt saved → {CYAN}.rkt_handoff_prompt.md{NC}")
            print(f"  {BLUE}▸{NC}  Open the file and paste into Cursor / Claude / ChatGPT")
            print(f"  {BLUE}▸{NC}  open {CYAN}{prompt_path}{NC}")
        else:
            print(f"  {GREEN}✓{NC}  Prompt saved (clean handoff) → {CYAN}.rkt_handoff_prompt.md{NC}")
        print()
    except OSError as e:
        print(f"  {YELLOW}!{NC}  Could not write handoff prompt: {e}")


if __name__ == "__main__":
    ws    = sys.argv[1] if len(sys.argv) > 1 else ""
    issue = sys.argv[2] if len(sys.argv) > 2 else ""
    run(ws, issue)
