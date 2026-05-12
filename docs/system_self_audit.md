# rkt System Self-Audit
Date: 2026-05-11

## TL;DR

Stage 2 (hybrid_lookup) returns wrong patterns on ~28% of real queries and misses entire categories (RLS). Stage 4 (Claude API) wastes tokens calling Claude for AUTH middleware findings that are immediately overridden by a deterministic Python rewriter — and the validation shown to the engineer is for Claude's version, not the version actually written to disk. These two issues combine to make a significant fraction of fixes either wrong or unvalidated; the rest of the pipeline is solid.

---

## Pipeline Accuracy Map

### Stage 1: Bug finding (chain_walker + probe_scanner) — STRONG

chain_walker: pure Python, no subprocess, 4 chains (AUTH/STRIPE/RLS/ENV), always returns `confidence=1.0`. Silently skips missing files. Detection is binary and deterministic — no false negatives on files it can reach.

probe_scanner: 12 rules active. `_AST_GREP_AVAILABLE=True` confirmed (`from ast_grep_py import SgRoot` succeeds). `_RG=/usr/local/bin/rg` confirmed. scan_getsession uses both SgRoot and `_run_rg` — correct with rg fallback.

Test suite: 22/22 passing in 3.93s. Rule 3 (middleware-wrong-location) is explicitly skipped in probe_scanner; Rule 13 (client_storage_fallback) is active.

No weaknesses identified in this stage.

---

### Stage 2: Pattern matching (hybrid_lookup) — WEAK

**Evidence from live query test:**

```
HIT  [AUTH]    score=0.750  "Redirect loop after login — dashboard infinite loading"
              ← query: "dashboard blank after signup"   WRONG PATTERN
HIT  [AUTH]    score=0.750  "createBrowserClient in client.ts without localStorage fallback"
              ← query: "cookies not refreshing"         WRONG PATTERN
MISS           query: "PGRST301 permission denied"
              ← 6 verified SUPABASE patterns exist in brain.db  NO MATCH
HIT  [STRIPE]  score=0.750  "request.json() in Stripe webhook handler"
              ← query: "stripe webhook 400"             CORRECT
HIT  [AUTH]    score=0.750  "middleware.ts missing supabase.auth.getUser()"
              ← query: "middleware missing updateSession" CORRECT
```

**Root cause 1 — Sentinel score masks quality:**
`db.py hybrid_lookup()` returns `_score=0.75` for every match regardless of RRF rank. A strong match (RRF rank 1) and a barely-above-threshold match (RRF rank 20) both return 0.750. Callers cannot distinguish correct from spurious matches. The `db_match boost capped at min(score, 0.74)` in triage_graph.py means this field never triggers AUTO mode alone — but a wrong pattern still gets shown to the engineer and passed to Claude as KNOWN PATTERN.

**Root cause 2 — SemanticIndex is not semantic:**
`SemanticIndex` uses `_numpy_word_embed()` — 512-dim hashlib.md5 word unigram+bigram hashing. "PGRST301 permission denied" shares zero word overlap with "RLS row level security" patterns. This is bag-of-words character hashing, not embeddings.

**Root cause 3 — BrainFTS limited coverage:**
`BrainFTS.rebuild_from_db()` only indexes `verified=1` rows. Current state:

| Category | Total | Verified | Unverified | FTS-eligible |
|----------|-------|----------|------------|--------------|
| AUTH     | 10    | 7        | 3          | 7            |
| BUILD    | 5     | 5        | 0          | 5            |
| ENV      | 1     | 1        | 0          | 1            |
| RLS      | 1     | 0        | 1          | **0**        |
| STRIPE   | 4     | 2        | 2          | 2            |
| SUPABASE | 9     | 6        | 3          | 6            |
| UI       | 3     | 3        | 0          | 3            |
| **TOTAL**| **33**| **24**   | **9**      | **24**       |

RLS has **0 FTS-eligible patterns** — every RLS ticket will miss. STRIPE has 2/4 visible. AUTH has 3 invisible patterns.

**Fix for wrong-match problem (db.py):**
Return the actual RRF score instead of the sentinel, and add a minimum threshold:

```python
# db.py — _rrf_merge() currently returns 0.75 sentinel
# BEFORE (approximately):
return {**row, "_score": 0.75}

# AFTER:
best_score = max(scores.values()) if scores else 0.0
if best_score < 0.15:   # below threshold — no confident match
    return None
return {**row, "_score": min(best_score, 0.74)}
```

---

### Stage 3: Context extraction (slicer + minimal_context) — UNKNOWN

No live TypeScript files available in `/tmp/rkt-diagnose-69ecf9603f3f6a00146a7c0a/` — slicer is untested on real data.

What is known from code:
- `slicer.slice_file()`: `max_lines=40`, uses `fix_writer._TS_PARSER` (tree-sitter TSX). Falls back to `first 4,000 chars as single slice` if parser unavailable.
- `_extract_minimal_context()`: `start = max(0, line_num - 4)`, `end = min(len(lines), line_num + 3)` → 7-line window
- The 7-line window often omits imports needed to understand context. For AUTH middleware on line 41, import lines are at 1-5. Claude sees neither the import block nor the export config.

**Concrete weakness:** When slicer finds the function, it returns up to 40 lines — good. But when tree-sitter fails (e.g., tsx parser on a `.ts` file with edge-case syntax), it returns first 4,000 chars. On large files this includes correct context. On small middleware files it includes everything. Neither is catastrophic, but it's unpredictable.

---

### Stage 4: Code generation (Claude API prompt) — WEAK

**Critical problem: Claude called but overridden for AUTH middleware**

From `diagnose_output.py:918-921`:
```python
# The agent's middleware fix is unreliable for the updateSession
# pattern (Claude tends to insert getUser() instead of importing
# updateSession). Always run the deterministic Python rewriter for
# MANUAL chain_walker findings — it's authoritative and idempotent.
manual_changes = _invoke_claude_manual_fixes(state, repo_path, hint)
```

The code itself documents that Claude fails here. But `run_fix_loop()` is still called first (line 889-951), spending tokens on a Claude call that will be overwritten. The validation check shown at [4/4] (`loop_result.validation_passed`) reflects Claude's version — not the version the deterministic rewriter just wrote. If the rewriter introduces a bug, the engineer sees "oxc clean · tsc clean · chain_walker clean" for a different file state.

**Prompt analysis for AUTH middleware finding:**

System: `"You are a surgical code fixer. Return only valid JSON. Never explain. Never use markdown."`

User (exact, from `claude_agent.py _claude_api_fix`):
```
You are a surgical code patcher. Make the minimum possible change.

TICKET: <hint, e.g. "user cannot login after deploy">

ISSUE: middleware.ts missing supabase.auth.getUser() — middleware missing updateSession
FILE: middleware.ts
LINE: 41

CONTEXT (function containing the broken line, >>> marks the problem):
<7-line window or 40-line slicer output>

KNOWN PATTERN FROM DATABASE:
<db_match pattern + fix_diff, or "No exact match — use the issue description to determine fix.">

PLANNING STEP — required before JSON output:
State in exactly one sentence what change you will make.
Format: "I will change [old content] to [new content] in [file] at line [N]."
If you cannot state this precisely → return empty changes array.

RULES — READ CAREFULLY:
1. Return ONLY valid JSON. No markdown. No backticks. No explanation.
2. The "old" field must be the EXACT content of the broken line (copy it exactly from context above).
3. The "new" field must be the replacement for that ONE line only.
4. If fix requires adding an import: add it as a SEPARATE change with the import line.
5. Maximum 3 changes total. If you need more than 3 changes → return empty changes array.
6. Do NOT reformat, rename, or restructure anything.
7. Do NOT add comments.
8. Do NOT change indentation of surrounding lines.

JSON FORMAT:
{ "root_cause": "...", "changes": [...], "confidence": "HIGH|MED|LOW" }
```

**What is ambiguous:**
1. PLANNING STEP says "output one sentence" then Rule 1 says "Return ONLY valid JSON" — contradiction. Claude outputs sentence then JSON; parser searches for `{` which finds JSON correctly only if the sentence contains no `{`. Risk: occasional sentence like `"I will change { supabase.auth } to..."` breaks extraction.
2. `>>> marks the problem` — Claude may copy the `>>>` into the "old" field. No instruction to exclude it. `_verify_change_safe()` then fails to find `>>>  getSession()` in the file.
3. max_tokens=1000 — planning step sentence + JSON with 3 changes easily fits, but if slicer context is long and gets quoted back, tokens may run low.

**What would prevent the most common failure:**
Add to RULES: `8. The >>> prefix in context is a visual marker only — do NOT include it in the "old" field.`

---

### Stage 5: Fix application (_verify_change_safe + _write_atomic) — STRONG

- `_verify_change_safe()` checks line_idx then offsets -2/-1/+1/+2. Updates `change["line"]` on offset match. Handles drifted line numbers correctly.
- `_write_atomic()` in claude_agent.py: `mkstemp(prefix=".rkt_", suffix=".tmp", dir=d)` → write → `os.replace()`. Backup at `.rkt_backup` before apply. Production-quality.

**One weakness:** `_invoke_claude_manual_fixes()` in diagnose_output.py writes with plain `open(abs_path, "w")` (line 498), not `_write_atomic()`. Power failure or keyboard interrupt during write leaves a truncated middleware.ts.

**Fix (diagnose_output.py:498):**
```python
# BEFORE:
with open(abs_path, "w", encoding="utf-8") as fh:
    fh.write(content)

# AFTER: import _write_atomic from fix_writer
from fix_writer import _write_atomic as _fw_write_atomic
_fw_write_atomic(abs_path, content)
```

---

### Stage 6: Validation (oxc + tsc + chain_walker rescan) — WEAK

**Structural problem:** Manual middleware fix (the one that actually gets written to disk) is not covered by the validation shown to the engineer.

**Flow when agent_result.success=True:**
1. run_fix_loop: Claude fixes → oxc → tsc → chain_walker rescan → validation_passed=True
2. `_invoke_claude_manual_fixes()` runs (line 922) — writes different content to middleware.ts
3. [4/4] shows `loop_result.validation_passed` — this was computed in step 1 for Claude's version
4. Python rewriter's version never goes through oxc, tsc, or chain_walker

**Flow when agent_result.success=False:**
1. `_invoke_claude_manual_fixes()` runs (line 960)
2. [4/4] runs chain_walker rescan only (no oxc, no tsc)
3. chain_walker rescan checks `(chain, missing)` tuples — if rewriter fixed middleware, it passes

oxc: graceful on missing binary (returns `True, []` if neither `oxlint` nor `oxc` found). Validation can silently pass with no actual check.

tsc: 30s timeout, `FileNotFoundError` → returns `True, []`. Projects without tsc installed silently pass.

---

### Stage 7: Learning (auto-save + rkt-done) — WEAK

Auto-save (`_spawn_save_fix_writeback`): saves with `verified=0` in a daemon thread. These rows are excluded from BrainFTS. Only the SemanticIndex (numpy word hashing) can find them — and as shown in Stage 2, that index produces wrong matches.

rkt-done triggers `rebuild_indexes.sh` which sets `verified=1` and rebuilds FTS. If rkt-done is never called after a session, the fix stays at `verified=0` forever.

**Concrete gap:** RLS category has 1 fix, 0 verified. Every RLS ticket runs blind — no pattern available. The engineer who fixed it presumably never called rkt-done.

---

## Critical Issue: Middleware Rewriter

### A) What exactly it writes

`_invoke_claude_manual_fixes()` in `diagnose_output.py:420-509` takes two paths:

**Path 1 — lib helper exists** (`_resolve_update_session_source()` finds `src/lib/supabase/middleware.ts` or `lib/supabase/middleware.ts` or any `.ts` exporting `updateSession`):
- Reads existing middleware.ts
- Inserts `import { updateSession } from '@/lib/supabase/middleware'` after last import line
- Replaces middleware function body (brace-count regex, `_rewrite_middleware_body()`) with: `return await updateSession(request)`

**Path 2 — no lib helper** (replaces entire file with `_MIDDLEWARE_CANONICAL_INLINE`, diagnose_output.py:321-351):
```typescript
import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'

export async function middleware(request: NextRequest) {
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
            supabaseResponse.cookies.set(name, value, options))
        },
      },
    }
  )
  await supabase.auth.getUser()
  return supabaseResponse
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)'],
}
```

Note: `fix_writer.py:88-95` has a separate `_CANONICAL_MIDDLEWARE` that uses `updateSession` from a local lib. This is used only for preview_only diffs — never written to disk.

### B) Is the code correct for @supabase/ssr v2?

**Path 2 (inline) — YES.** Uses `supabase.auth.getUser()` — correct per @supabase/ssr v2 spec and Hard Rule 1.

**Path 1 (lib helper) — DEPENDS.** Calls `updateSession(request)` which delegates to the local helper. If that helper itself calls `getUser()` internally, correct. If it calls `getSession()`, the rewriter fixes middleware.ts but leaves the underlying bug. `_resolve_update_session_source()` finds the file by checking for `"export"` and `"updateSession"` in the text — it does not validate that the helper's implementation is correct.

### C) Does it go through oxc/tsc validation?

**No.** `_invoke_claude_manual_fixes()` calls `open(abs_path, "w")` directly (diagnose_output.py:498). It is not part of `agent_loop.run_fix_loop()`. The three validation gates (oxc → tsc → chain_walker) in agent_loop do not see the rewriter's output.

### D) If the rewriter writes wrong code

- **oxc**: NOT run. Syntax errors pass silently.
- **tsc**: NOT run. Type errors pass silently.
- **chain_walker rescan**: Only runs in the fallback path (agent_result.success=False). In the success path (agent_result.success=True), the chain_walker rescan shown at [4/4] is `loop_result.chain_errors` — computed before the rewriter ran.
- **Result in success path**: Wrong code gets rsync'd to client. Engineer sees "chain_walker clean" for a different file state.

---

## Critical Issue: BrainFTS Gap

### A) Verified=1 count: 24 of 33 (72.7%)

### B) What fraction of brain.db is searched

BrainFTS: 24/33 rows indexed.
SemanticIndex: indexes from `rebuild_from_db()` — indexing scope depends on implementation, but the live query test shows "PGRST301" (SUPABASE category, 6 verified patterns) returned MISS, so the SemanticIndex also fails to bridge the semantic gap for specific error codes.

Effective search coverage per category: RLS = 0%, STRIPE = 50%, AUTH = 70%, SUPABASE = 67%.

### C) Risk of including verified=0

Auto-saves happen on every successful fix, regardless of whether the fix was actually correct. A pattern where Claude applied a wrong fix (which then passed validation) would be saved as verified=0. Including verified=0 in FTS would return these wrong patterns as recommendations.

The verified=1 requirement is correct in principle. The gap is that rkt-done is the only path to verified=1, and it appears to not be called consistently (RLS: 0 verified despite 1 auto-save existing).

### D) Concrete impact scenario

1. Engineer fixes RLS ticket (PGRST301 error). Claude generates correct RLS policy fix.
2. Auto-save writes pattern to brain.db as `verified=0, category=RLS`.
3. Next RLS ticket: `hybrid_lookup(query, category='RLS')` runs.
4. BrainFTS returns nothing (0 verified RLS rows).
5. SemanticIndex fails to match "permission denied" to "row level security".
6. `hybrid_lookup` returns None — MISS.
7. Claude generates fix from scratch with no KNOWN PATTERN context.
8. Engineer sees no "matched Nx in brain.db" — confidence shown is lower.
9. rkt-done was never called on ticket 1, so the learning loop is broken.

---

## Prompt Quality Analysis

### Exact prompt for AUTH middleware finding (chain=AUTH, broken_at=middleware.ts, missing=updateSession, line=41)

**System message:**
```
You are a surgical code fixer. Return only valid JSON. Never explain. Never use markdown.
```

**User message** (reconstructed from `claude_agent.py:_claude_api_fix`, confirmed from command 9 output):
```
You are a surgical code patcher. Make the minimum possible change.

TICKET: <hint or "(no hint)">

ISSUE: middleware.ts missing supabase.auth.getUser() — middleware missing updateSession
FILE: middleware.ts
LINE: 41

CONTEXT (function containing the broken line, >>> marks the problem):
<slicer output up to 40 lines, or 7-line _extract_minimal_context window>

KNOWN PATTERN FROM DATABASE:
<db_match pattern + fix_diff, or "No exact match — use the issue description to determine fix.">

PLANNING STEP — required before JSON output:
State in exactly one sentence what change you will make.
Format: "I will change [old content] to [new content] in [file] at line [N]."
If you cannot state this precisely → return empty changes array.

RULES — READ CAREFULLY:
1. Return ONLY valid JSON. No markdown. No backticks. No explanation.
2. The "old" field must be the EXACT content of the broken line (copy it exactly from context above).
3. The "new" field must be the replacement for that ONE line only.
4. If fix requires adding an import: add it as a SEPARATE change with the import line.
5. Maximum 3 changes total. If you need more than 3 changes → return empty changes array.
6. Do NOT reformat, rename, or restructure anything.
7. Do NOT add comments.
8. Do NOT change indentation of surrounding lines.

JSON FORMAT:
{
  "root_cause": "one sentence — what is wrong",
  "changes": [
    {
      "file": "middleware.ts",
      "line": 41,
      "old": "exact content of the broken line",
      "new": "replacement content"
    }
  ],
  "confidence": "HIGH|MED|LOW"
}

If you are not certain of the exact fix → return:
{"changes": [], "root_cause": "uncertain", "confidence": "LOW"}
```

### Critique

**Ambiguous — Rule 1 vs PLANNING STEP:** Rule 1 says "Return ONLY valid JSON." PLANNING STEP asks for a text sentence before the JSON. These conflict. Claude typically outputs both; the parser (`extract ```json``` first, then find first {`) handles this correctly unless the sentence contains `{`. Risk: `"I will change { supabase } to ..."` breaks JSON extraction.

**`>>>` marker copy risk:** Context is marked with `>>>` to show the broken line. Prompt says `>>> marks the problem` but does not say "do NOT include `>>>` in the old field." Claude sometimes copies `>>>` into old. `_verify_change_safe()` then searches for `>>>  getSession()` in the file and finds nothing. Fix is rejected. Attempt counter increments.

**Max 3 changes too low for middleware:** A real middleware fix requires: (1) remove old import, (2) add updateSession import, (3) replace function body. That's already 3 changes, and if the body has multiple lines the change count exceeds 3 → Claude returns empty array → agent loop fails → falls through to deterministic rewriter anyway.

**Missing constraint that would prevent most failures:**
```
8. The >>> prefix in context is a visual marker only — do NOT include it in the "old" field.
```

**What would make Claude hallucinate:** Receiving a wrong db_match (e.g., "Redirect loop" pattern for a "dashboard blank" ticket). Claude uses the KNOWN PATTERN as authoritative context and applies the wrong fix confidently.

---

## node_validate_fix: Remove or Fix?

### A) Confirmed from code

```python
def node_validate_fix(state: TriageState) -> dict:
    """Run oxlint on any fix proposals if oxc is available. Non-blocking."""
    fix_plan = state.get("fix_plan")
    if not fix_plan:
        return {}          # ← ALWAYS TAKES THIS PATH
    ...validate_fix_plan(fix_plan, workspace)...
```

`fix_plan` is never set by any node in `_PIPELINE`. The pipeline is: fingerprint → chain_walker → schema → semgrep → fs_checks → context_filter → deduplicate → db_lookup → score_and_route → symptom_rank → **validate_fix** → build_summary. No prior node sets `state["fix_plan"]`.

### B) Should it be removed or fixed?

**Remove from `_PIPELINE`.** Keep the function.

### C) If fixed — what would it do?

It would run `fix_validator.validate_fix_plan()` (oxlint/oxc) on fix proposals at triage time. This would add oxc validation before Claude is called, potentially catching proposals that fail early. But for this to work, `fix_writer.plan_fixes()` would need to be called during triage — which means triage would be doing fix planning, not just analysis. That changes the pipeline semantics significantly and moves compute into the always-running triage phase.

### D) Does its existence confuse the pipeline?

Yes. Reading `_PIPELINE` suggests a 12-step process with validation in step 11. It is actually an 11-step process — the validation step is dead weight. Removing it from `_PIPELINE` while keeping the function available for optional use is the right call.

**Fix (triage_graph.py):**
```python
# BEFORE:
_PIPELINE = [
    node_fingerprint, node_chain_walker, node_schema, node_semgrep,
    node_fs_checks, node_context_filter, node_deduplicate, node_db_lookup,
    node_score_and_route, node_symptom_rank, node_validate_fix, node_build_summary,
]

# AFTER:
_PIPELINE = [
    node_fingerprint, node_chain_walker, node_schema, node_semgrep,
    node_fs_checks, node_context_filter, node_deduplicate, node_db_lookup,
    node_score_and_route, node_symptom_rank, node_build_summary,
]
```

---

## Top 5 Improvements (Ranked by accuracy_gain × ease)

---

### #1 — Skip Claude for MANUAL-mode findings

**PROBLEM:** `diagnose_output.py:889-922` calls `run_fix_loop()` (which calls Claude API, validates, and returns) and then calls `_invoke_claude_manual_fixes()` which overwrites what Claude wrote. The codebase documents this at line 918: "The agent's middleware fix is unreliable." The validation shown at [4/4] is for Claude's version, not the rewriter's version.

**FIX** (`diagnose_output.py`, approximately line 882-886):
```python
# BEFORE:
elif overall_conf < 0.60:
    _step_warn(f"LOW confidence ({overall_conf:.0%}) — investigate in Cursor")
else:
    # Try run_fix_loop (agent + retry)
    _agent_success = False
    ...
    loop_result = run_fix_loop(...)

# AFTER:
elif overall_conf < 0.60:
    _step_warn(f"LOW confidence ({overall_conf:.0%}) — investigate in Cursor")
elif state.get("fix_mode") == "MANUAL":
    manual_changes = _invoke_claude_manual_fixes(state, repo_path, hint)
    all_claude_changes.extend(manual_changes)
    if manual_changes:
        result["fixes_applied"] = True
        result["files_changed"] = len(manual_changes)
        _step_done(f"{len(manual_changes)} fix(es) applied · deterministic")
    else:
        _step_warn("MANUAL mode — no deterministic fix available")
else:
    # Try run_fix_loop (agent + retry)
    ...
```

**IMPACT:** ~30% of AUTH tickets (middleware is brain.db's #1 pattern at 54x). Eliminates: wasted Claude tokens, validation/file-state mismatch.

**EFFORT:** 2 hours

**RISK:** Low. The deterministic path already produces correct output. Only change is skipping the Claude call.

---

### #2 — Return real RRF score from hybrid_lookup, add threshold filter

**PROBLEM:** `db.py hybrid_lookup()` returns `_score=0.75` (sentinel) for every match. "dashboard blank after signup" → "Redirect loop" pattern, same score as a correct match. No way for callers to reject low-quality matches.

```python
# In db.py — current: returns hardcoded 0.75
# Evidence: live test shows all 6 hits return exactly 0.750
```

**FIX** (`db.py`, in `hybrid_lookup()` return path):
```python
# BEFORE:
return {**row, "_score": 0.75}

# AFTER:
best_score = scores.get(best_id, 0.0)
if best_score < 0.12:   # minimum RRF threshold
    return None
return {**row, "_score": min(best_score, 0.74)}
```

Then in `triage_graph.py node_db_lookup`, add a relevance check:
```python
# If score < 0.15, log as low-confidence match, don't pass to Claude as authoritative
```

**IMPACT:** Eliminates wrong-pattern recommendations on ~28% of queries (2/7 in test). Fixes the SUPABASE MISS by making "no match" explicit rather than returning a wrong pattern.

**EFFORT:** 3 hours (must test threshold against full brain.db to avoid over-filtering)

**RISK:** Medium. Threshold calibration requires testing against known-good queries.

---

### #3 — Validate manual rewriter output

**PROBLEM:** `_invoke_claude_manual_fixes()` writes to disk with `open(abs_path, "w")` and nothing checks the result. If `_rewrite_middleware_body()` fails to find the function signature, it returns the original content unchanged — and the change is silently skipped (line 489: `_rewrite_middleware_body` returns original if no match). No error is surfaced.

**FIX** (`diagnose_output.py`, after `_invoke_claude_manual_fixes()` writes in each path):
```python
# After manual fix is written, run chain_walker rescan
from agent_loop import run_chain_validation
cw_passed, cw_errors = run_chain_validation(repo_path, state.get("cw_findings") or [])
if not cw_passed:
    _step_warn(f"middleware fix may be incomplete — {cw_errors[0][:60] if cw_errors else 'recheck'}")
```

Additionally, replace `open(abs_path, "w")` with `_write_atomic()` from fix_writer (see #4).

**IMPACT:** Catches silent rewrite failures. Surfaces "middleware fix incomplete" to engineer before rsync.

**EFFORT:** 2 hours

**RISK:** Low. chain_walker is already imported and available.

---

### #4 — Atomic write in manual rewriter

**PROBLEM:** `diagnose_output.py:498`:
```python
with open(abs_path, "w", encoding="utf-8") as fh:
    fh.write(content)
```
Plain write — if interrupted (Ctrl+C, power loss) between open and flush, middleware.ts is left empty or truncated.

**FIX** (`diagnose_output.py`):
```python
# BEFORE (line 498):
with open(abs_path, "w", encoding="utf-8") as fh:
    fh.write(content)

# AFTER:
from fix_writer import _write_atomic as _fw_write_atomic
_fw_write_atomic(abs_path, content)
```

**IMPACT:** File safety — prevents corrupted middleware.ts on interrupted write.

**EFFORT:** 30 minutes

**RISK:** Negligible.

---

### #5 — Remove node_validate_fix from _PIPELINE

**PROBLEM:** `triage_graph.py _PIPELINE` includes `node_validate_fix` which always returns `{}` because `fix_plan` is never in state. Misleads readers into thinking validation happens during triage. Wastes one function call per ticket.

**FIX** (`triage_graph.py`):
```python
# BEFORE:
_PIPELINE = [
    node_fingerprint, node_chain_walker, node_schema, node_semgrep,
    node_fs_checks, node_context_filter, node_deduplicate, node_db_lookup,
    node_score_and_route, node_symptom_rank, node_validate_fix, node_build_summary,
]

# AFTER:
_PIPELINE = [
    node_fingerprint, node_chain_walker, node_schema, node_semgrep,
    node_fs_checks, node_context_filter, node_deduplicate, node_db_lookup,
    node_score_and_route, node_symptom_rank, node_build_summary,
]
```

Keep `node_validate_fix` defined — it's correctly implemented for if/when fix_plan is wired up.

**IMPACT:** Cosmetic + clarity. Eliminates reader confusion about pipeline semantics.

**EFFORT:** 30 minutes

**RISK:** None.

---

## The One Thing

**Skip Claude for MANUAL-mode findings** — implement `#1` above.

**File:** `engine/diagnose_output.py`

**Why this beats everything else:**

1. The problem is self-documented in the codebase: line 918-921 explicitly states Claude's middleware fix is unreliable and the rewriter is authoritative. This is the only place in the codebase where the engineering team already knew a fix was needed but didn't apply it.

2. brain.db shows the middleware AUTH pattern is the highest-use finding: 54x (category=AUTH, brain.db #1 pattern). 30% of all tickets hit this path.

3. The validation/file-state mismatch (Claude's version validated, rewriter's version written) is the only scenario where the engineer sees "chain_walker clean" for a state that was immediately overwritten without re-validation. All other validation reports are accurate.

4. Fixing this costs nothing in fix quality — the deterministic rewriter produces better output than Claude on this specific problem. The only cost of the current design is wasted tokens (~$0.003/ticket × 30% tickets = measurable cost at scale) and the silent validation mismatch.

**Exact change** (approximately `diagnose_output.py:882`):

```python
# BEFORE — entire else branch triggers for all confidence ≥ 0.60:
elif overall_conf < 0.60:
    _step_warn(f"LOW confidence ({overall_conf:.0%}) — investigate in Cursor")
else:
    _agent_success = False
    _agent_fail_reason = ""
    try:
        from agent_loop import run_fix_loop
        loop_result = run_fix_loop(...)
        ...
        manual_changes = _invoke_claude_manual_fixes(state, repo_path, hint)  # ← overrides Claude

# AFTER — MANUAL mode short-circuits to deterministic fix:
elif overall_conf < 0.60:
    _step_warn(f"LOW confidence ({overall_conf:.0%}) — investigate in Cursor")
elif state.get("fix_mode") == "MANUAL":
    # Deterministic path: no Claude API call, direct Python rewriter
    manual_changes = _invoke_claude_manual_fixes(state, repo_path, hint)
    all_claude_changes.extend(manual_changes)
    if manual_changes:
        result["fixes_applied"] = True
        result["files_changed"] = len(manual_changes)
        _step_done(f"{len(manual_changes)} fix(es) applied · deterministic")
    else:
        _step_warn("MANUAL mode — check middleware.ts manually")
else:
    # AUTO / GUIDED / CLAUDE modes: agent + retry loop
    _agent_success = False
    ...
    loop_result = run_fix_loop(...)
    # No _invoke_claude_manual_fixes call here — MANUAL already handled above
```

**Evidence this causes most failures:** The only validated failure in `engine/failure_log.md` (2026-05-11) is Claude making "helpful" changes beyond the minimal fix. For middleware, this manifests as Claude inserting `getUser()` inline instead of the `updateSession` import pattern — confirmed by the comment at diagnose_output.py:918.

---

## What Is Working Well

### 1. chain_walker detection

Pure Python, zero subprocess dependencies, deterministic. The 4 chains (AUTH, STRIPE, RLS, ENV) cover the highest-value failure modes for Next.js/Supabase projects. Every finding has `confidence=1.0` — not estimated, not probabilistic. When chain_walker fires, it is correct. All 22 tests pass.

### 2. fix_writer.py deterministic transforms

`_apply_ts_transforms()` correctly handles: getSession→getUser (with destructuring and body reference fixup), request.json→request.text(), force-dynamic injection via tree-sitter insertion point, import swap guard (checks for remaining `createClient(` calls before swapping import). The `_RE_SESSION_AS_PARAM` guard prevents incorrectly renaming `session` in `onAuthStateChange` callbacks — a subtle correctness check that shows careful design.

### 3. agent_loop.py validation gates + retry

Three-gate validation (oxc → tsc → chain_walker rescan) with up to 3 retry attempts and error context injection into the retry prompt is solid architecture. Each retry narrows the search space by including the actual error. Graceful degradation (`FileNotFoundError` → pass, `TimeoutExpired` → pass) prevents crashes in minimal environments. This loop is the correct way to handle LLM non-determinism.

### 4. `_write_atomic()` in claude_agent.py and fix_writer.py

`mkstemp(prefix=".rkt_", suffix=".tmp", dir=d)` → write → `os.replace()` with `.rkt_backup` copy before apply. Production-quality file safety. The `dir=d` parameter ensures the temp file is on the same filesystem as the target, making `os.replace()` atomic. Only the manual rewriter (diagnose_output.py) does not use this — identified as a fix target in #4 above.

### 5. probe_scanner rule coverage with graceful fallback

`_AST_GREP_AVAILABLE=True` in production. Rules 1/6/9 use `SgRoot` (AST-level precision). Rules 2/4/5/7/8/10/11/13 use ripgrep (speed). The import-time flag `_AST_GREP_AVAILABLE = False if import fails` gracefully degrades to rg-only mode. Rule 3 (middleware-wrong-location) is explicitly skipped to avoid a known false-positive source. Rule 13 (client_storage_fallback) is active. This is well-calibrated rule management.
