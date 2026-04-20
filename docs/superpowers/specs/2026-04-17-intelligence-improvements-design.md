# rkt Engine Intelligence Improvements — Design Spec
Date: 2026-04-17
Status: Approved

## Overview

Four targeted improvements to the rkt triage engine, all focused on speed and intelligence:
- A: AST-aware context filter (cut false positives)
- B: Symptom-driven re-ranking (surface right findings first)
- C: Cross-layer deduplication (each bug shown once, with stronger evidence)
- D: Incremental re-triage after AUTO fix (catch second-order bugs)

All changes are additive. No existing layer is removed or replaced.

---

## A — AST-Aware Context Filter

### Purpose
Eliminate false positives from test files, intentional overrides, and dev-only code paths by reading surrounding context before recording a finding.

### New file: `engine/context_filter.py`

**Input:** list of raw findings from chain_walker + semgrep (each has `file`, `line`, `rule_id`, `category`)

**Logic:**
1. For each finding, read ±15 lines around the violation line
2. Check for suppression signals:
   - `// @rkt-ignore` on the violation line or the line above
   - `// intentional`, `// expected`, `// override` in the same block
   - `process.env.NODE_ENV === 'test'` or `if (process.env.NODE_ENV` wrapping the violation
   - File path contains `/__tests__/`, `/test/`, `.test.ts`, `.spec.ts`, `.test.tsx`, `.spec.tsx`
3. If suppression found: set `confidence = "SUPPRESSED"`, add `suppression_reason: str`
4. Return findings split into `active: list` and `suppressed: list`

**Output schema per finding:**
```python
{
  "source": str,         # "chain_walker" | "semgrep"
  "file": str,
  "line": int,
  "rule_id": str,
  "category": str,
  "confidence": str,     # "HIGH" | "MED" | "LOW" | "SUPPRESSED"
  "suppression_reason": str | None,
  "context_lines": list[str],   # ±15 lines, stored for dedup step
}
```

### Integration point
`triage_graph.py`: new node `context_filter` inserted after `semgrep` node, before `deduplicate`.

### Display
Suppressed findings shown at bottom of report: `Suppressed (1): getSession in tests/auth.test.ts — @rkt-ignore`

---

## B — Symptom-Driven Re-ranking

### Purpose
When the engineer describes the symptom ("auth broken after login"), findings matching that category surface first — even before higher-confidence findings from other categories.

### New file: `engine/symptom_ranker.py`

**Input:** `issue_description: str`, `findings: list`

**Keyword → category map:**
```python
SYMPTOM_MAP = {
    "AUTH":     ["auth", "login", "logout", "session", "token", "jwt", "oauth", "redirect", "not authenticated", "unauthorized"],
    "STRIPE":   ["stripe", "webhook", "payment", "checkout", "subscription", "400", "billing"],
    "SUPABASE": ["supabase", "rls", "row level", "policy", "trigger", "profile", "dashboard blank", "empty array"],
    "BUILD":    ["build", "deploy", "netlify", "vercel", "typescript", "tsc", "type error", "compile"],
    "ENV":      ["env", "api key", "secret", "environment variable", "invalid key", "anon key"],
}
```

**Logic:**
1. Lowercase the issue description
2. Score each category: count keyword hits
3. Primary symptom category = highest-scoring category (min 1 hit to qualify)
4. Re-rank findings: symptom-matched category findings move to top, within their existing confidence order
5. Add `symptom_match: bool` flag to each finding

**Output:** re-ranked findings list, `primary_symptom_category: str | None`

### Integration point
`triage_graph.py`: new node `symptom_rank` inserted after `score_and_route`, before `build_summary`.

### Display
Report header gains one line: `Symptom category: AUTH (matched "auth broken after login")`

---

## C — Cross-Layer Deduplication

### Purpose
When two layers flag the same bug in the same file+line range, merge them into one finding with combined evidence and auto-promoted confidence.

### New file: `engine/dedup.py`

**Input:** findings list after context_filter (each has `source`, `file`, `line`, `category`, `confidence`)

**Match criteria (all must be true):**
- Same `file`
- Line numbers within 5 lines of each other
- Same `category`

**Merge logic:**
1. Group findings by `(file, category)` bucket
2. Within each bucket, cluster by line proximity (±5 lines)
3. For clusters with 2+ findings from different sources:
   - Merge into one finding
   - `evidence: list` = all contributing sources (e.g. `["chain_walker", "semgrep"]`)
   - `confidence` = auto-promoted one tier up from highest member (MED → HIGH, LOW → MED)
   - `message` = combined: primary source message + "Confirmed by: semgrep"
4. Single-source findings pass through unchanged with `evidence: [source]`

**Output:** deduplicated findings list

### Integration point
`triage_graph.py`: new node `deduplicate` between `context_filter` and `score_and_route`.

### Display
Merged finding shows: `[chain_walker + semgrep] ✓ Confirmed — HIGH confidence`

---

## D — Incremental Re-triage After AUTO Fix

### Purpose
After AUTO mode writes fixes, re-scan only the changed files. Surface secondary issues that the fix exposed, without re-running the full 13-second pipeline.

### New file: `engine/retriage.py`

**Input:** `workspace_path: str`, `fixed_files: list[str]`, `issue_description: str`

**Logic:**
1. Scope chain_walker to `fixed_files` only (pass as `target_files` filter)
2. Run semgrep with `--include` scoped to `fixed_files`
3. Run context_filter + dedup on results
4. Return delta findings (exclude any finding already in the original report)

**Output:**
```python
{
  "delta_findings": list,     # new issues not in original report
  "files_scanned": int,
  "scan_time_ms": int,
}
```

**Fixed file tracking:** `fix_writer.apply_fixes()` already returns a list of written paths. Pass this directly to `retriage.run()`.

### Integration point
`bin/rkt-crazy` and `bin/rkt-triage`: after the AUTO fix block, call:
```bash
python3 "$ENGINE_DIR/retriage.py" "$WORKSPACE" "$FIXED_FILES_JSON" "$ISSUE"
```

### Display
After AUTO fix completes:
```
── RE-TRIAGE (changed files only) ──
  ✓  2 files re-scanned in 1.2s
  !  1 secondary issue found:
     [semgrep] Missing force-dynamic on app/dashboard/page.tsx (MED)
     → Run rkt-triage to fix, or select [4] MANUAL
```

If no secondary issues: `✓  Re-triage clean — no secondary issues found`

---

## Updated triage_graph.py node order

```
Before:
  fingerprint → chain_walker → schema → semgrep → fs_checks
              → db_lookup → score_and_route → build_summary

After:
  fingerprint → chain_walker → schema → semgrep → fs_checks
              → context_filter → deduplicate → db_lookup
              → score_and_route → symptom_rank → build_summary
```

## Updated bin/rkt-crazy and bin/rkt-triage AUTO block

```
Before:
  AUTO apply fixes → rkt-deliver prompt

After:
  AUTO apply fixes → retriage (changed files) → delta report → rkt-deliver prompt
```

---

## Files touched

| File | Change |
|------|--------|
| `engine/context_filter.py` | NEW |
| `engine/symptom_ranker.py` | NEW |
| `engine/dedup.py` | NEW |
| `engine/retriage.py` | NEW |
| `engine/triage_graph.py` | Add 3 new nodes: context_filter, deduplicate, symptom_rank |
| `engine/rkt_engine.py` | Import and call context_filter after findings collected |
| `bin/rkt-crazy` | Call retriage after AUTO fix block |
| `bin/rkt-triage` | Call retriage after AUTO fix block |

---

## Success criteria

- [ ] No finding from a `.test.ts` / `.spec.ts` file appears in active findings
- [ ] `// @rkt-ignore` above a violation suppresses it
- [ ] Symptom "auth broken" causes AUTH findings to appear first in report
- [ ] Same bug flagged by chain_walker + semgrep shows as one merged finding
- [ ] After AUTO fix, re-triage runs in under 3 seconds on a 50-file project
- [ ] Re-triage delta report is shown before the rkt-deliver prompt
