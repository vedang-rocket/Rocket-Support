# Agent Failure Log

Every entry = one real failure + permanent fix applied to harness.
This is a ratchet. System never makes the same mistake twice.

## How to add an entry
When a fix goes wrong:
1. Document what Claude did wrong (exactly)
2. Document what rule prevents it next time
3. Document where that rule now lives
4. Apply the rule immediately — do not wait

## Entry format
---
Date: YYYY-MM-DD
Ticket: <threadId or DC-XXX>
Confidence: HIGH/MED/LOW
Category: AUTH/STRIPE/SUPABASE/BUILD/ENV

What Claude did wrong:
<exact description — be specific, not vague>

Example of bad output:
<paste the actual bad code Claude generated>

What it should have done:
<paste what correct output looks like>

Root cause of failure:
<why did Claude make this mistake — context too wide / prompt too loose / wrong file / etc>

Permanent fix applied:
<what was changed in harness to prevent this>

Where rule now lives:
[ ] claude_agent.py prompt
[ ] probe_scanner.py new rule
[ ] chain_walker.py new chain
[ ] CLAUDE.md hard rule
[ ] agent_loop.py constraint
[ ] Other: ___

Verified: does system no longer make this mistake? YES/NO
---

## Known failures so far

---
Date: 2026-05-11
Ticket: general observation
Confidence: ALL
Category: ALL

What Claude did wrong:
Applied multi-line changes when only one line needed changing.
Reformatted surrounding code. Changed variable names. Added comments.
Fix looked correct but broke other parts of file.

What it should have done:
Changed exactly one line. Left everything else identical.

Root cause of failure:
Prompt said "change only broken lines" but Claude interprets
"broken" loosely and makes additional "helpful" changes.

Permanent fix applied:
- Added 7-line minimal context window (_extract_minimal_context)
- Added _verify_change_safe() pre-apply check
- Prompt now says "old field must be EXACT content of broken line"
- Maximum 3 changes total enforced in prompt

Where rule now lives:
[x] claude_agent.py prompt
[x] claude_agent.py _verify_change_safe()
[x] claude_agent.py _extract_minimal_context()

Verified: YES — implemented in current codebase
---

---
Date: 2026-05-11
Ticket: system-self-audit
Confidence: HIGH
Category: AUTH

What Claude did wrong:
Called Claude API for MANUAL-mode middleware findings, then overrode the result
with the deterministic Python rewriter — validation shown to engineer was for
Claude's version, not the version written to disk.

Example of bad output:
Engineer sees "[4/4] validating... oxc clean · tsc clean · chain_walker clean"
but middleware.ts was rewritten after that validation ran.

What it should have done:
Route MANUAL mode directly to _invoke_claude_manual_fixes(), skip run_fix_loop().

Root cause of failure:
_invoke_claude_manual_fixes() was called AFTER run_fix_loop() succeeded.
Code comment at diagnose_output.py:918 acknowledged Claude was unreliable here
but the call was never removed.

Permanent fix applied:
Added elif state.get("fix_mode") == "MANUAL": branch in diagnose_output.py
before the run_fix_loop() else block. MANUAL mode routes directly to deterministic
rewriter. Removed _invoke_claude_manual_fixes() call from agent success path.

Where rule now lives:
[x] Other: diagnose_output.py fix_mode routing logic (line ~882)

Verified: YES
---

---
Date: 2026-05-11
Ticket: system-self-audit
Confidence: HIGH
Category: ALL

What Claude did wrong:
N/A — hybrid_lookup() returned _score=0.75 (hardcoded sentinel) for every match
regardless of actual relevance. "dashboard blank after signup" matched "Redirect
loop" pattern with identical confidence as correct matches. Callers had no signal
to reject bad matches.

Example of bad output:
HIT [AUTH] score=0.750 "Redirect loop after login" ← query: "dashboard blank after signup"
HIT [AUTH] score=0.750 "createBrowserClient in client.ts" ← query: "cookies not refreshing"

What it should have done:
Return actual RRF score so callers can distinguish strong from weak matches.

Root cause of failure:
_rrf_merge() discarded the computed scores dict, returning only IDs.
hybrid_lookup() replaced the real score with the hardcoded 0.75 sentinel.

Permanent fix applied:
_rrf_merge() now returns (sorted_ids, scores) tuple.
hybrid_lookup() uses real score with 0.012 minimum RRF threshold.
Score capped at 0.74 so it never triggers AUTO mode alone.

Where rule now lives:
[x] Other: db.py _rrf_merge() and hybrid_lookup() (lines ~605, ~663)

Verified: YES
---

---
Date: 2026-05-11
Ticket: system-self-audit
Confidence: HIGH
Category: ALL

What Claude did wrong:
N/A — infrastructure safety bug, not a Claude generation error.
_invoke_claude_manual_fixes() wrote middleware.ts with plain open(abs_path, "w").
Power loss or Ctrl+C during write leaves a truncated (empty or partial) file.

What it should have done:
Use atomic write: mkstemp + write + os.replace() so the file is either fully
written or unchanged — never partial.

Root cause of failure:
The function was written without the atomic write pattern used elsewhere
(claude_agent.py, fix_writer.py both use mkstemp + os.replace correctly).

Permanent fix applied:
Replaced plain open() with mkstemp + os.fdopen + os.replace + unlink-on-exception
in diagnose_output.py _invoke_claude_manual_fixes().

Where rule now lives:
[x] Other: diagnose_output.py _invoke_claude_manual_fixes() (line ~498)

Verified: YES
---

---
Date: 2026-05-11
Ticket: system-self-audit
Confidence: ALL
Category: ALL

What Claude did wrong:
N/A — dead code issue in triage pipeline.
node_validate_fix was listed in _PIPELINE but always returned {} because
fix_plan is never set during run_triage(). Pipeline appeared to have 12 nodes;
actually ran 11 meaningful nodes.

What it should have done:
Only include nodes that do real work in _PIPELINE.

Root cause of failure:
node_validate_fix was added with the intention of wiring fix_plan into triage,
but that wiring was never implemented. The node was left in _PIPELINE as dead code.

Permanent fix applied:
Removed node_validate_fix from _PIPELINE in triage_graph.py.
Function kept with comment for future use when fix_plan is populated at triage time.

Where rule now lives:
[x] Other: triage_graph.py _PIPELINE list (line ~497)

Verified: YES
---

---
Date: 2026-05-11
Ticket: system-self-audit
Confidence: HIGH
Category: ALL

What Claude did wrong:
Copied the >>> visual marker into the "old" field of its JSON response.
_verify_change_safe() then searched for ">>>  getSession()" in the file, found
nothing, and the fix was rejected. Retry attempt consumed.

Example of bad output:
{"old": ">>>  await supabase.auth.getSession()", "new": "  await supabase.auth.getUser()"}

What it should have done:
{"old": "  await supabase.auth.getSession()", "new": "  await supabase.auth.getUser()"}

Root cause of failure:
Prompt marked the broken line with >>> prefix to help Claude identify it,
but gave no instruction to exclude >>> from the "old" field value.

Permanent fix applied:
Added Rule 9 to RULES section in claude_agent.py _claude_api_fix() prompt:
"The >>> prefix in the context above is a visual marker only. Do NOT include
>>> in the 'old' field. Copy the exact line content without any prefix."

Where rule now lives:
[x] claude_agent.py prompt (Rule 9, line ~410)

Verified: YES
---

---
Date: 2026-05-12
Ticket: gap-analysis-gap5
Confidence: HIGH
Category: ALL

What Claude did wrong:
N/A — latent crash bug in probe_scanner, not a Claude generation error.
scan_getsession(), scan_cookies_without_await(), scan_headers_without_await()
passed all TypeScript file paths as positional argv to rg. On repos with 500+
files this silently hits ARG_MAX (macOS: 256KB) — rg exits with E2BIG and
returns zero matches. AUTH and Next.js 15 findings are silently missed.

Permanent fix applied:
Changed all three function signatures from ts_files: List[str] to repo_path: str.
rg now receives --glob *.ts --glob *.tsx --glob *.js --glob *.jsx + repo_path.
rg handles file traversal internally — no argv length constraint.
run_probe_scanner() updated to pass repo_path to these three functions.

Where rule now lives:
[x] Other: probe_scanner.py scan_getsession/scan_cookies_without_await/scan_headers_without_await

Verified: YES
---

---
Date: 2026-05-12
Ticket: gap-analysis-gap6
Confidence: MED
Category: ALL

What Claude did wrong:
N/A — inefficiency bug in probe_scanner, not a Claude generation error.
scan_missing_revalidate() opened each file twice — once to read 300 bytes for the
"use server" check, then again to read full content. On a 200-file repo this
doubled file-handle churn for every server action file.

Permanent fix applied:
Merged into single read: read full content, then check content[:300] for "use server".
One open() per file instead of two.

Where rule now lives:
[x] Other: probe_scanner.py scan_missing_revalidate()

Verified: YES
---

---
Date: 2026-05-12
Ticket: gap-analysis-gap7
Confidence: HIGH
Category: ALL

What Claude did wrong:
N/A — wrong category passed to hybrid_lookup when fingerprint confidence is low.
node_db_lookup() always passed fingerprint.category to hybrid_lookup regardless of
fingerprint confidence. When confidence < 0.50 the category is an unreliable guess —
passing it caused hybrid_lookup to filter out correct brain.db patterns.
E.g., a STRIPE ticket fingerprinted as BUILD at 0.38 confidence never matched
verified Stripe webhook patterns.

What it should have done:
Prefer chain_walker category (authoritative, derived from actual code inspection).
Fall back to fingerprint category only when confidence >= 0.50.
Pass None (no filter) when fingerprint is low-confidence and chain_walker found nothing.

Permanent fix applied:
node_db_lookup() now extracts cw_category from cw_findings[0]["chain"] when available.
Uses cw_category if set, else fp_result["category"] only when fp_conf >= 0.50, else None.

Where rule now lives:
[x] Other: triage_graph.py node_db_lookup()

Verified: YES
---
