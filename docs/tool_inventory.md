# rkt System — Complete Tool Inventory (Execution Order)

This document maps every tool, script, and module used in the rkt-diagnose pipeline from start to finish.

---

## PHASE 0 — CLAUDE CODE HOOKS (fire on session start, before any command)

These hooks fire automatically when Claude Code starts a new session.

| Hook Type | File | Fires When | What It Does | Exit Code | Working? |
|-----------|------|------------|--------------|-----------|----------|
| SessionStart | `~/.claude/hooks/ruflo-daemon.sh` | New Claude session | Starts RuFlo V3 MCP daemon in background if not running | 0 | WORKING |
| SessionStart | `~/.claude/hooks/brain-inject.sh` | New Claude session | Injects brain.db top 5 patterns + project fingerprint into Claude context | 0 | WORKING |
| PreToolUse | `~/.claude/hooks/graphify.sh` | Grep/Glob/Read tools | Extracts pattern from tool input and displays context scope | 0 | WORKING |
| PreToolUse | `~/.claude/hooks/ux-detector.sh` | Any prompt with UI keywords | Injects "UI/UX Pro Max mode active" when UI terms detected | 0 | WORKING |
| PostToolUse | `~/.claude/hooks/chain-walker-check.sh` | Write/Edit/MultiEdit on .ts/.tsx | Runs chain_walker.py to verify no structural breaks after edit | 0/2 | PARTIAL |
| Stop | `~/.claude/hooks/tsc-check.sh` | Claude tries to stop | Runs `tsc --noEmit` — blocks stop if errors found (exit 2) | 0/2 | WORKING |

---

## PHASE 1 — PROJECT INIT

Everything from `rkt-diagnose <threadId>` start through rsync completing.

### STEP 1: bin/rkt-diagnose (entry point)
─────────────────────────────────────────
Type:      Bash script
File:      ~/rocket-support/bin/rkt-diagnose
Called by: User CLI: `rkt-diagnose DC-MAY-12 "hint"`
Calls:     rocket CLI → rsync → diagnose_output.py
Input:     threadId, optional hint, --shadow flag
Output:    Terminal progress + diff display, exit code
Purpose:   SSH init + full engine diagnosis + automatic fix application
Status:    WORKING
Tokens:    no

**Sub-steps within rkt-diagnose:**
1. **SSH init** (lines 66-90): `rocket clean` → `rocket init $THREAD_ID` → detect project folder
2. **Cursor rules** (line 88): `rkt-rules-add` — install v34 cursor rules
3. **rsync remote → local** (lines 92-102): `rsync -az --exclude node_modules` to `/tmp/rkt-diagnose-$THREAD_ID`
4. **Engine call** (lines 104-114): Run `diagnose_output.py` with all params
5. **rsync local → remote** (lines 118-131): If fixes applied, rsync back to container
6. **npm install** (lines 134-137): `npm install --prefer-offline --quiet` on remote
7. **Open Cursor** (lines 139-143): Prompt "Open in Cursor?" → `cursor --remote ssh-remote+$SSH_HOST`

### STEP 2: bin/rkt-rules-add (implicit)
─────────────────────────────────────────
Type:      Bash script
File:      ~/rocket-support/bin/rkt-rules-add
Called by: rkt-diagnose line 88
Calls:     cp of .cursor/rules from v34 template
Input:     None (implicit during init)
Output:    Installed rules count
Purpose:   Install v34 Cursor rules to project
Status:    WORKING
Tokens:    no

---

## PHASE 2 — PERCEPTION LAYER (finding bugs)

All tools that read the project and find issues, in the exact order triage_graph.py calls them.

The pipeline in triage_graph.py runs sequentially:

### STEP 3: engine/triage_graph.py → node_fingerprint
─────────────────────────────────────────
Type:      Python module
File:      ~/rocket-support/engine/triage_graph.py:136-142
Called by: `run_triage()` entry point at line 464
Calls:     `fingerprint.fingerprint()` (engine/fingerprint.py)
Input:     workspace_path (repo root)
Output:    dict: {project_type, confidence, all_scores, common_failure, category, framework, next_version, has_supabase, has_stripe, env_vars, sql_files_found}
Purpose:   Detect project type from package.json + file structure
Status:    WORKING
Tokens:    no

### STEP 4: engine/fingerprint.py
─────────────────────────────────────────
Type:      Python module
File:      ~/rocket-support/engine/fingerprint.py:205-281
Called by: triage_graph.node_fingerprint()
Calls:     _load_package_json, _score_project_type, _detect_framework, _detect_has_supabase, _detect_has_stripe, _check_env_vars
Input:     repo_path
Output:    Dict with project_type (SaaS|E-Commerce|AI|Booking|Landing|Blog), confidence score, common_failure
Purpose:   Score 0.0-1.0 for each project type based on deps + SQL keywords + file patterns
Status:    WORKING
Tokens:    no

### STEP 5: engine/triage_graph.py → node_chain_walker
─────────────────────────────────────────
Type:      Python module
File:      ~/rocket-support/engine/triage_graph.py:145-151
Called by: run_triage() pipeline
Calls:     `chain_walker.walk()` (engine/chain_walker.py)
Input:     workspace_path
Output:    list of {chain, broken_at, missing, issue, fix_hint, confidence}
Purpose:   Walk 4 dependency chains (AUTH, STRIPE, RLS, ENV) for structural breaks
Status:    WORKING
Tokens:    no

### STEP 6: engine/chain_walker.py
─────────────────────────────────────────
Type:      Python module
File:      ~/rocket-support/engine/chain_walker.py:275-317
Called by: triage_graph.node_chain_walker()
Calls:     detect_layout, build_chains, _walk_chain for each active chain
Input:     repo_path
Output:    List of breaks (one per chain max): [{chain: STRIPE, broken_at: "...", missing: "request.text()", issue: "...", fix_hint: "..."}]
Purpose:   Pure Python structural check — no subprocess, no Claude, <1s
Status:    WORKING
Tokens:    no

**Precondition guards:** AUTH only if @supabase in package.json; STRIPE only if stripe in package.json; RLS only if supabase/migrations/ exists; ENV if @supabase OR stripe.

### STEP 7: engine/triage_graph.py → node_schema
─────────────────────────────────────────
Type:      Python module
File:      ~/rocket-support/engine/triage_graph.py:154-160
Called by: run_triage() pipeline
Calls:     `schema_checker.check()` (engine/schema_checker.py)
Input:     workspace_path
Output:    list of {check, found, file, fix_hint}
Purpose:   Audit supabase/migrations/*.sql for required patterns
Status:    WORKING
Tokens:    no

### STEP 8: engine/schema_checker.py
─────────────────────────────────────────
Type:      Python module
File:      ~/rocket-support/engine/schema_checker.py:64-121
Called by: triage_graph.node_schema()
Calls:     glob.glob for *.sql files, regex search for patterns
Input:     repo_path
Output:    List: [{check: "trigger:on_auth_user_created", found: True/False, fix_hint: "..."}]
Purpose:   Check for on_auth_user_created trigger, RLS enable, INSERT policy, TIMESTAMPTZ
Status:    WORKING
Tokens:    no

### STEP 9: engine/triage_graph.py → node_semgrep
─────────────────────────────────────────
Type:      Python module
File:      ~/rocket-support/engine/triage_graph.py:163-194
Called by: run_triage() pipeline
Calls:     `probe_scanner.run_probe_scanner()` OR `rkt_engine.run_semgrep()` (fallback)
Input:     workspace_path
Output:    dict: {findings: [...], errors: [...], available: bool}
Purpose:   AST-level scan for code patterns (getSession→getUser, request.json→text, cookies without await)
Status:    WORKING
Tokens:    no

### STEP 10: engine/probe_scanner.py (preferred over semgrep)
─────────────────────────────────────────
Type:      Python module
File:      ~/rocket-support/engine/probe_scanner.py:656-688
Called by: triage_graph.node_semgrep() when _PROBE_AVAILABLE = True
Calls:    scan_getsession, scan_cookies_without_await, scan_stripe_webhook, scan_auth_helpers, scan_supabase_wrong_import, scan_client_storage_fallback, scan_env_secrets, scan_missing_dynamic_export (all functions)
Input:     repo_path
Output:    dict with semgrep-compatible findings: [{check_id, path, start: {line, col}, extra: {message, severity, fix, metadata}}]
Purpose:   Fast AST + rg scanner for 13 Rocket rules (replaces semgrep in most cases)
Status:    WORKING
Tokens:    no

**Scanner functions called:**
- `scan_getsession()` — ast-grep-py for $CLIENT.auth.getSession()
- `scan_cookies_without_await()` — ast-grep-py for unawaited cookies()
- `scan_headers_without_await()` — ast-grep-py for unawaited headers()
- `scan_missing_revalidate()` — regex for Server Actions without revalidatePath
- `scan_auth_helpers()` — rg for deprecated @supabase/auth-helpers-nextjs
- `scan_stripe_webhook()` — rg for request.json() in webhook files
- `scan_supabase_wrong_import()` — rg for @supabase/supabase-js in server files
- `scan_client_storage_fallback()` — rg for createBrowserClient without localStorage
- `scan_env_secrets()` — rg for NEXT_PUBLIC_ on secret keys
- `scan_missing_dynamic_export()` — rg for authenticated pages without force-dynamic
- `scan_anon_key_format()` — rg for old JWT-format anon key in .env
- `scan_use_client_server_import()` — rg for 'use client' + server-only imports

### STEP 11: engine/rkt_engine.py (fallback for semgrep)
─────────────────────────────────────────
Type:      Python module
File:      ~/rocket-support/engine/rkt_engine.py:98-168
Called by: triage_graph.node_semgrep() when probe_scanner unavailable
Calls:     subprocess.run for semgrep CLI
Input:     repo_path, autofix flag
Output:    dict: {available, findings, errors, autofix_applied}
Purpose:   Run semgrep with Rocket.new rules as fallback
Status:    WORKING (if semgrep installed)
Tokens:    no

### STEP 12: engine/triage_graph.py → node_fs_checks
─────────────────────────────────────────
Type:      Python module
File:      ~/rocket-support/engine/triage_graph.py:197-203
Called by: run_triage() pipeline
Calls:     `rkt_engine.fs_checks()` (engine/rkt_engine.py:224-286)
Input:     workspace_path
Output:    list of {rule, severity, message, fix}
Purpose:   File-system level checks (middleware location, NEXT_PUBLIC_ on secrets)
Status:    WORKING
Tokens:    no

### STEP 13: engine/triage_graph.py → node_context_filter
─────────────────────────────────────────
Type:      Python module
File:      ~/rocket-support/engine/triage_graph.py:206-232
Called by: run_triage() pipeline
Calls:     `context_filter.filter_findings()` (engine/context_filter.py)
Input:     wrapped findings with source tags
Output:    dict: {active: [...], suppressed: [...]} — suppresses test files, @rkt-ignore comments
Purpose:   Filter false positives before scoring
Status:    WORKING
Tokens:    no

### STEP 14: engine/context_filter.py
─────────────────────────────────────────
Type:      Python module
File:      ~/rocket-support/engine/context_filter.py:112-152
Called by: triage_graph.node_context_filter()
Calls:     _is_test_file, _read_lines, _check_suppression
Input:     findings list, workspace_path
Output:    Active vs suppressed findings with reasons
Purpose:   Suppress findings in test files, with @rkt-ignore, or NODE_ENV test guards
Status:    WORKING
Tokens:    no

### STEP 15: engine/triage_graph.py → node_deduplicate
─────────────────────────────────────────
Type:      Python module
File:      ~/rocket-support/engine/triage_graph.py:235-241
Called by: run_triage() pipeline
Calls:     `dedup.deduplicate()` (engine/dedup.py)
Input:     filtered_findings
Output:    cross-layer merged findings
Purpose:   Deduplicate across chain_walker, semgrep, fs_checks, schema sources
Status:    WORKING
Tokens:    no

### STEP 16: engine/dedup.py (imported, quick check)
─────────────────────────────────────────
Type:      Python module
File:      ~/rocket-support/engine/dedup.py
Called by: triage_graph.node_deduplicate()
Calls:    (not fully read but imported)
Input:    findings list
Output:   deduplicated findings
Purpose:  Merge duplicate findings across sources
Status:   WORKING
Tokens:   no

---

## PHASE 3 — PLANNING (deciding what to do)

Confidence scoring, routing decision, fix_mode selection.

### STEP 17: engine/triage_graph.py → node_db_lookup
─────────────────────────────────────────
Type:      Python module
File:      ~/rocket-support/engine/triage_graph.py:260-269
Called by: run_triage() pipeline
Calls:     `rkt_engine.db_lookup()` → `db.hybrid_lookup()`
Input:     query (hint or common_failure), category from fingerprint
Output:    dict: {pattern, error_signature, category, fix_diff, _score, uses}
Purpose:   Look up similar past fixes from brain.db
Status:    WORKING
Tokens:    no

### STEP 18: engine/triage_graph.py → node_score_and_route
─────────────────────────────────────────
Type:      Python module
File:      ~/rocket-support/engine/triage_graph.py:272-330
Called by: run_triage() pipeline
Calls:     _score_cw_finding, _score_semgrep_finding, _score_schema_finding, _overall_fix_mode
Input:     deduped_findings, db_match
Output:    dict: {findings_scored, overall_confidence, primary_category, fix_mode, auto_fixable_count}
Purpose:   Assign fix_mode (AUTO|GUIDED|CLAUDE|MANUAL) and confidence per finding
Status:    WORKING
Tokens:    no

### STEP 19: engine/triage_graph.py → node_symptom_rank
─────────────────────────────────────────
Type:      Python module
File:      ~/rocket-support/engine/triage_graph.py:244-257
Called by: run_triage() pipeline
Calls:     `symptom_ranker.rank_findings()` (engine/symptom_ranker.py)
Input:     scored findings, issue_description (hint)
Output:    ranked findings, symptom_category
Purpose:   Rank by symptom match to user-reported issue
Status:    WORKING
Tokens:    no

---

## PHASE 4 — RETRIEVAL (RAG — finding past fixes)

brain.db lookup, hybrid_lookup, usearch, tantivy, RRF merge.

### STEP 20: engine/db.py → hybrid_lookup
─────────────────────────────────────────
Type:      Python module
File:      ~/rocket-support/engine/db.py:624-673
Called by: rkt_engine.db_lookup() → triage_graph.node_db_lookup()
Calls:     get_semantic_index().search() + brain_fts.search() + _rrf_merge() + find_similar fallback
Input:     query string, optional category
Output:    top matching fix dict or None
Purpose:   Hybrid search: semantic (usearch/numpy) + FTS (tantivy) + RRF merge + keyword fallback
Status:    WORKING
Tokens:    no

### STEP 21: engine/db.py → SemanticIndex
─────────────────────────────────────────
Type:      Python class (inside db.py)
File:      ~/rocket-support/engine/db.py:111-255
Called by: hybrid_lookup() → get_semantic_index().search()
Calls:     _numpy_word_embed for vectors, usearch.Index fallback to in-memory numpy
Input:     query string, top_k
Output:    list of {id, score}
Purpose:   Vector similarity search using 512-dim word n-gram embeddings
Status:    WORKING (degrades gracefully without usearch)
Tokens:    no

### STEP 22: engine/brain_fts.py → BrainFTS.search
─────────────────────────────────────────
Type:      Python module
File:      ~/rocket-support/engine/brain_fts.py:144-171
Called by: hybrid_lookup() → get_brain_fts().search()
Calls:     tantivy.Index.search() with BM25
Input:     query string, top_k
Output:    list of {id, category, score}
Purpose:   Full-text search via tantivy BM25 over fix patterns
Status:    WORKING (graceful fail if tantivy unavailable)
Tokens:    no

### STEP 23: engine/db.py → find_similar (fallback)
─────────────────────────────────────────
Type:      Python module
File:      ~/rocket-support/engine/db.py:554-597
Called by: hybrid_lookup() fallback when both semantic + FTS fail
Calls:     _embed() → _cosine() OR keyword overlap scoring
Input:     query, top_k, category
Output:    list of fixes sorted by score
Purpose:   Fallback: vector cosine similarity or keyword overlap
Status:    WORKING
Tokens:    no

---

## PHASE 5 — CONTEXT BUILDING (assembling what Claude gets)

slicer.py, minimal context window, surgical context assembly.

### STEP 24: engine/slicer.py → slice_repo
─────────────────────────────────────────
Type:      Python module
File:      ~/rocket-support/engine/slicer.py:169-198
Called by: Not called in current pipeline (imported but not wired in main flow)
Calls:     slice_file for each .ts/.tsx, walks repo
Input:     repo_path, keywords list (AUTH_KEYWORDS | STRIPE_KEYWORDS)
Output:    list of {file, function_name, start_line, end_line, source, keywords_found}
Purpose:   tree-sitter surgical extraction of auth/stripe-touching functions
Status:    NOT WIRED (imported but not called in triage_graph or diagnose_output)
Tokens:    no

### STEP 25: engine/format_output.py (not called in diagnose flow)
─────────────────────────────────────────
Type:      Python module
File:      ~/rocket-support/engine/format_output.py
Called by: rkt_engine._print_all_findings(), format_output.print_fingerprint()
Calls:    Rich console output
Input:    findings, fingerprint result
Output:   Rich-formatted terminal output
Purpose:   Format findings with colors and tables
Status:    PARTIAL (used by rkt_smart.py but not diagnose_output.py which uses Rich directly)
Tokens:    no

---

## PHASE 6 — FIX GENERATION (calling Claude API)

claude_agent.py PATH A (brain.db diff) and PATH B (Claude API). Show exact prompt structure.

### STEP 26: engine/agent_loop.py → run_fix_loop
─────────────────────────────────────────
Type:      Python module
File:      ~/rocket-support/engine/agent_loop.py:82-166
Called by: diagnose_output.py line 852 or 887
Calls:     ClaudeAgent.fix() → if fail, retry up to max_attempts (3)
Input:     findings, repo_path, db_match, hint, shadow, max_attempts
Output:    LoopResult: {success, attempts, final_result, validation_passed, tsc_errors, chain_errors}
Purpose:   Retry loop: apply fix → validate with tsc + chain_walker → retry on failure
Status:    WORKING
Tokens:    yes (if Claude API called)

### STEP 27: engine/claude_agent.py → ClaudeAgent.fix
─────────────────────────────────────────
Type:      Python module
File:      ~/rocket-support/engine/claude_agent.py:73-104
Called by: run_fix_loop()
Calls:     PATH A: _apply_known_diff() if db_match has fix_diff; else PATH B: _claude_api_fix()
Input:     findings list, repo_path, db_match, hint, shadow
Output:    AgentResult: {success, changes_applied, root_cause, confidence, tokens_used, path_used}
Purpose:   Two-path fix agent: brain.db diff (PATH A) or Claude API (PATH B)
Status:    WORKING
Tokens:    yes (PATH B only)

### STEP 28: engine/claude_agent.py → PATH A: _apply_known_diff
─────────────────────────────────────────
Type:      Python method
File:      ~/rocket-support/engine/claude_agent.py:157-218
Called by: ClaudeAgent.fix() when db_match has fix_diff
Calls:     _parse_diff, _resolve_file, _diff_is_applicable, _line_replace, _write_atomic
Input:     db_match (with fix_diff), repo_path, shadow flag
Output:    AgentResult with changes_applied, path_used="brain_db_diff", tokens_used=0
Purpose:   Apply verified unified diff from brain.db — zero tokens, <1ms
Status:    WORKING
Tokens:    no

### STEP 29: engine/claude_agent.py → PATH B: _claude_api_fix
─────────────────────────────────────────
Type:      Python method
File:      ~/rocket-support/engine/claude_agent.py:295-489
Called by: ClaudeAgent.fix() when no db_match or PATH A failed
Calls:     _norm_finding, _extract_minimal_context, anthropic SDK
Input:     findings, repo_path, db_match, hint, shadow
Output:    AgentResult with changes_applied, path_used="claude_api", tokens_used > 0
Purpose:   Call Claude Sonnet 4-5 API with surgical context
Status:    WORKING
Tokens:    yes

**Prompt structure sent to Claude (lines 327-371):**
```
You are a surgical code patcher. Make the minimum possible change.

TICKET: {hint or "(no hint)"}

ISSUE: {primary_finding_message}
FILE: {primary_file_relative}
LINE: {primary_line_number}

CONTEXT (7 lines around the broken line, >>> marks the problem):
{minimal_context}

KNOWN PATTERN FROM DATABASE:
{db_section or "No exact match — use the issue description to determine fix."}

PLANNING STEP — required before JSON output:
State in exactly one sentence what change you will make.
Format: "I will change [old content] to [new content] in [file] at line [N]."

RULES:
1. Return ONLY valid JSON. No markdown.
2. The "old" field must be the EXACT content of the broken line.
3. Maximum 3 changes total.

JSON FORMAT:
{"root_cause": "...", "changes": [{"file": "...", "line": N, "old": "...", "new": "..."}], "confidence": "HIGH|MED|LOW"}
```

**Token count estimation:**
- minimal_context: ~200 tokens (7 lines around issue)
- prompt structure: ~300 tokens (fixed)
- **Total per call: ~500 tokens (input only)**

---

## PHASE 7 — APPLICATION (writing changes to files)

fix_writer, atomic write, pre-apply verification.

### STEP 30: engine/fix_writer.py → plan_fixes
─────────────────────────────────────────
Type:      Python module
File:      ~/rocket-support/engine/fix_writer.py:501-707
Called by: diagnose_output.py:825 OR rkt_smart.py:404
Calls:     dedupe_findings, _apply_ts_transforms, _apply_sql_timestamptz
Input:     findings, db_match, kb_hits
Output:    FixPlan with FileProposal list
Purpose:   Build fix proposals from normalized findings — regex/transform-based
Status:    WORKING
Tokens:    no

### STEP 31: engine/fix_writer.py → apply_fix_plan
─────────────────────────────────────────
Type:      Python module
File:      ~/rocket-support/engine/fix_writer.py:710-737
Called by: diagnose_output.py:968 OR rkt_smart.py:447
Calls:     _backup_once, _write_atomic
Input:     FixPlan, selected_paths, write_changes flag
Output:    FixResult: {files_modified, fixes_applied, fixes_skipped, diffs, audit_log}
Purpose:   Apply selected fix proposals atomically (temp file + os.replace)
Status:    WORKING
Tokens:    no

### STEP 32: engine/fix_writer.py → _apply_ts_transforms
─────────────────────────────────────────
Type:      Python function
File:      ~/rocket-support/engine/fix_writer.py:340-441
Called by: plan_fixes()
Calls:     tree-sitter parser (if available), regex replacements
Input:     file path, original content, rules set
Output:    (new_text, applied_rule_ids, audit_entries)
Purpose:   Apply regex transforms for: getSession→getUser, request.json→text, force-dynamic injection
Status:    WORKING
Tokens:    no

### STEP 33: engine/fix_writer.py → _write_atomic
─────────────────────────────────────────
Type:      Python method
File:      ~/rocket-support/engine/fix_writer.py:182-194
Called by: apply_fix_plan() for each file
Calls:     tempfile.mkstemp, os.fdopen, os.replace
Input:    file path, new content
Output:   Atomic write (temp + replace)
Purpose:   Safe file write — prevents corruption on failure
Status:    WORKING
Tokens:    no

---

## PHASE 8 — VALIDATION (checking if fix worked)

tsc --noEmit, chain_walker rescan, fix_validator/oxc.

### STEP 34: engine/agent_loop.py → run_tsc
─────────────────────────────────────────
Type:      Python function
File:      ~/rocket-support/engine/agent_loop.py:24-52
Called by: run_fix_loop() after each attempt
Calls:     subprocess.run for `npx tsc --noEmit`
Input:     repo_path, timeout (30s default)
Output:    (passed: bool, errors: List[str])
Purpose:   TypeScript compilation check
Status:    WORKING
Tokens:    no

### STEP 35: engine/agent_loop.py → run_chain_validation
─────────────────────────────────────────
Type:      Python function
File:      ~/rocket-support/engine/agent_loop.py:55-79
Called by: run_fix_loop() after each attempt
Calls:     `chain_walker.walk()` re-run
Input:     repo_path, original_findings
Output:    (passed: bool, remaining_violations: List[str])
Purpose:   Re-run chain_walker to confirm original violations are fixed
Status:    WORKING
Tokens:    no

### STEP 36: engine/fix_validator.py → validate_fix_plan
─────────────────────────────────────────
Type:      Python module
File:      ~/rocket-support/engine/fix_validator.py:74-135
Called by: triage_graph.node_validate_fix() (called but likely not wired in diagnose flow)
Calls:     _oxc_available, _run_oxc, _apply_unified_diff
Input:     fix_plan, repo_path
Output:    validation_errors list
Purpose:   Run oxlint/oxc on patched files — non-blocking
Status:    NOT WIRED (imported but not called in current flow)
Tokens:    no

---

## PHASE 9 — RETRY LOOP (if validation failed)

agent_loop.py, error feedback injection, max 3 attempts.

### STEP 37: engine/agent_loop.py retry logic
─────────────────────────────────────────
Type:      Python loop
File:      ~/rocket-support/engine/agent_loop.py:105-156
Called by: run_fix_loop()
Calls:     ClaudeAgent.fix() → run_tsc() → run_chain_validation() → inject error feedback
Input:    findings, repo_path, db_match, original_hint, max_attempts=3
Output:    LoopResult with attempt count and errors
Purpose:   On validation failure, inject error context into hint and retry
Status:    WORKING
Tokens:    yes (on retry attempts)

**Retry injection (lines 116-120, 149-156):**
```python
hint = f"{original_hint}\n\n[Attempt {attempt} failed: {result.error}]\nTry a different approach. Be more surgical."
```

---

## PHASE 10 — LEARNING (saving what worked)

auto-save to brain.db, learn_fix.py, rkt-done.

### STEP 38: engine/diagnose_output.py → _spawn_save_fix_writeback
─────────────────────────────────────────
Type:      Python function (non-blocking thread)
File:      ~/rocket-support/engine/diagnose_output.py:744-769
Called by: After successful fix (lines 936, 1000)
Calls:     `db.save_fix()` (engine/db.py)
Input:     pattern, error_signature, category, fix_diff, project_type
Output:    daemon thread — non-blocking
Purpose:   Best-effort save to brain.db after successful fix
Status:    WORKING
Tokens:    no

### STEP 39: engine/db.py → save_fix
─────────────────────────────────────────
Type:      Python function
File:      ~/rocket-support/engine/db.py:490-551
Called by: _spawn_save_fix_writeback OR rkt-done via learn_fix.py
Calls:     init_db, _embed for vector, insert/update, rebuild semantic index
Input:     pattern, error_signature, category, fix_diff, project_type, verified flag
Output:    fix_id (hash)
Purpose:   Persist fix pattern to brain.db with embedding
Status:    WORKING
Tokens:    no

### STEP 40: bin/rkt-done → learn_fix.py
─────────────────────────────────────────
Type:      Python module
File:      ~/rocket-support/engine/learn_fix.py
Called by: rkt-done (bin/rkt-done:96-101)
Calls:     db.save_fix with interactive prompts
Input:     --project flag, --thread flag
Output:    Console prompts for pattern, category, diff
Purpose:   Interactive save to brain.db after session ends
Status:    WORKING
Tokens:    no

---

## PHASE 11 — DELIVERY (showing result to engineer)

rsync back to remote, Rich terminal output, diff display, Open in Cursor prompt.

### STEP 41: diagnose_output.py → _print_finding_block
─────────────────────────────────────────
Type:      Python function using Rich
File:      ~/rocket-support/engine/diagnose_output.py:238-267
Called by: main() after triage run
Calls:     Rich Table, console.print
Input:     root_cause, category, confidence, files list
Output:    Formatted terminal block
Purpose:   Display ROOT CAUSE, CATEGORY, CONFIDENCE, FILES in Rich table
Status:    WORKING
Tokens:    no

### STEP 42: diagnose_output.py → _print_agent_changes_panel
─────────────────────────────────────────
Type:      Python function using Rich
File:      ~/rocket-support/engine/diagnose_output.py:542-593
Called by: main() after successful fix
Calls:     Rich console.print for each change
Input:     agent_result.changes_applied, repo_path, extra_manual
Output:    Formatted diff summary with path labels
Purpose:   Show "CHANGES APPLIED" panel with old→new per line
Status:    WORKING
Tokens:    no (shows tokens used)

### STEP 43: bin/rkt-diagnose → rsync local → remote (lines 118-131)
─────────────────────────────────────────
Type:      Bash command
File:      ~/rocket-support/bin/rkt-diagnose
Called by: rkt-diagnose after Python engine success
Calls:    rsync -az with excludes
Input:    LOCAL_TMP (local temp), REMOTE_PROJECT_PATH (remote)
Output:   Files synced back to container
Purpose:   Push applied fixes back to remote container
Status:    WORKING
Tokens:    no

### STEP 44: bin/rkt-diagnose → cursor --remote (line 143)
─────────────────────────────────────────
Type:      Bash command
File:      ~/rocket-support/bin/rkt-diagnose
Called by: rkt-diagnose user confirmation
Calls:    cursor --remote with SSH host
Input:    SSH host + remote project path
Output:    Opens Cursor IDE with project
Purpose:   Open project in Cursor for review
Status:    WORKING
Tokens:    no

---

# TABLE 1 — External binaries and libraries

| Name | What it does | Why chosen | Python package or binary | Used in which phase |
|------|--------------|------------|--------------------------|---------------------|
| ripgrep (rg) | Fast text search, JSON output mode | Replacement for semgrep in probe_scanner | binary: `/usr/local/bin/rg` | Phase 2 (probe_scanner) |
| ast-grep-py | AST-based code pattern matching | Fast, pure Python, no subprocess | `pip install ast-grep-py` | Phase 2 (probe_scanner) |
| tree-sitter | Parser for TypeScript/TSX structural edits | Used in fix_writer for surgical transforms | `pip install tree-sitter` | Phase 7 (fix_writer) |
| tree-sitter-typescript | TypeScript language for tree-sitter | Parser for .ts/.tsx files | `pip install tree-sitter-typescript` | Phase 7 (fix_writer) |
| usearch | ANN vector search (optional) | Fast similarity search on embeddings | `pip install usearch` | Phase 4 (db.py SemanticIndex) |
| tantivy | Full-text search engine | BM25 search over fix patterns | `pip install tantivy` | Phase 4 (brain_fts.py) |
| numpy | Array operations for word embeddings | Word n-gram hashing fallback | `pip install numpy` | Phase 4 (db.py) |
| scikit-learn | ML utilities (TF-IDF vectorizer) | Embedding fallback | `pip install scikit-learn` | Phase 4 (db.py fallback) |
| anthropic SDK | Claude API client | Call Claude for fix generation | `pip install anthropic` | Phase 6 (claude_agent.py) |
| Rich | Terminal formatting | Rich tables and color output | `pip install rich` | Phase 11 (diagnose_output.py) |
| npx tsc | TypeScript compiler | Type checking | npm package | Phase 8 (agent_loop.py) |
| oxlint / oxc | Oxc linter (optional) | Post-fix validation | binary: `oxlint` | Phase 8 (fix_validator.py) — NOT WIRED |
| sqlite3 | Local fix database | Store patterns, embeddings | Python stdlib | All phases (db.py) |
| rsync | Remote file sync | Sync local/remote project | binary: system | Phase 1, Phase 11 |
| rocket CLI | Container init/push/clean | Initialize support session | binary: `rocket` | Phase 1 (rkt-diagnose) |
| fd | Fast file finder (optional) | Collect .ts/.tsx files | binary: `fd` | Phase 2 (probe_scanner) |
| graphify | Context graph builder | PreToolUse hook for file context | pip install graphifyy | Phase 0 (hook) |
| npx ruflo | Agent swarm + memory daemon | MCP server for vector memory | npm global | Phase 0 (hook) |
| npx cursor | IDE remote open | Open project in Cursor | npm global | Phase 11 (rkt-diagnose) |

---

# TABLE 2 — All Claude Code hooks

| Hook type | File | Fires when | What it does | Exit code | Working? |
|-----------|------|------------|--------------|-----------|----------|
| SessionStart | `~/.claude/hooks/ruflo-daemon.sh` | Claude session starts | Start ruflo MCP daemon if not running | 0 | WORKING |
| SessionStart | `~/.claude/hooks/brain-inject.sh` | Claude session starts | Inject brain.db top patterns + project fingerprint | 0 | WORKING |
| PreToolUse | `~/.claude/hooks/graphify.sh` | Grep/Glob/Read tools | Extract pattern from tool input, show context | 0 | WORKING |
| PreToolUse | `~/.claude/hooks/ux-detector.sh` | Any user prompt | Detect UI/UX keywords, inject "Pro Max mode" | 0 | WORKING |
| PostToolUse | `~/.claude/hooks/chain-walker-check.sh` | Write/Edit/MultiEdit on .ts/.tsx | Run chain_walker.py to verify no breaks | 0/2 | PARTIAL |
| Stop | `~/.claude/hooks/tsc-check.sh` | Claude tries to stop | Run `tsc --noEmit`, block if errors | 0/2 | WORKING |

---

# TABLE 3 — What is NOT wired (imported but not called)

| Tool/Module | File | What it does | Why not wired | Impact if wired |
|-------------|------|--------------|---------------|-----------------|
| slicer.py | engine/slicer.py | tree-sitter surgical extraction of auth/stripe functions | Not called in triage_graph or diagnose_output | Would reduce tokens from ~500 to ~200 per Claude call |
| fix_validator.py | engine/fix_validator.py | oxc/oxlint validation of fixes | Not called in diagnose_output flow | Would add post-fix linting gate |
| format_output.py | engine/format_output.py | Rich formatting utilities | diagnose_output.py uses Rich directly | Minimal — duplicate functionality |
| codegen_analyzer.py | engine/codegen_analyzer.py | Graph-sitter for code violations | Called in rkt_smart but not diagnose_output | Would add graph-sitter violations |
| deliverer.py | engine/deliverer.py | (not read) | Not imported anywhere | Unknown |
| handoff.py | engine/handoff.py | (not read) | Not imported anywhere | Unknown |
| workspace.py | engine/workspace.py | (not read) | Not imported anywhere | Unknown |
| gen_claude_md.py | engine/gen_claude_md.py | Generate CLAUDE.md | Used by rkt-main only | Used in rkt-main not diagnose |
| run_triage.py | engine/run_triage.py | CLI wrapper for triage_graph | Not imported — triage_graph.run_triage used directly | Duplicate entry point |

---

## EXECUTION ORDER SUMMARY

```
rkt-diagnose <threadId>
    │
    ├─ Phase 1: PROJECT INIT
    │  └─ rocket init → rsync → diagnose_output.py
    │
    ├─ Phase 2: PERCEPTION (triage_graph pipeline)
    │  ├─ node_fingerprint → fingerprint.py
    │  ├─ node_chain_walker → chain_walker.py (4 chains)
    │  ├─ node_schema → schema_checker.py
    │  ├─ node_semgrep → probe_scanner.py (13 rules)
    │  ├─ node_fs_checks → rkt_engine.fs_checks()
    │  ├─ node_context_filter → context_filter.py
    │  └─ node_deduplicate → dedup.py
    │
    ├─ Phase 3: PLANNING
    │  ├─ node_db_lookup → db.hybrid_lookup()
    │  │   ├─ SemanticIndex.search() (usearch/numpy)
    │  │   ├─ brain_fts.search() (tantivy)
    │  │   └─ _rrf_merge() → find_similar fallback
    │  ├─ node_score_and_route → confidence + fix_mode
    │  └─ node_symptom_rank → symptom_ranker
    │
    ├─ Phase 4-5: (context building not wired)
    │
    ├─ Phase 6: FIX GENERATION
    │  └─ agent_loop.run_fix_loop() → claude_agent.fix()
    │      ├─ PATH A: _apply_known_diff() (brain.db diff, 0 tokens)
    │      └─ PATH B: _claude_api_fix() (anthropic SDK, ~500 tokens)
    │
    ├─ Phase 7: APPLICATION
    │  └─ fix_writer.plan_fixes() → apply_fix_plan()
    │      └─ _write_atomic() (temp + replace)
    │
    ├─ Phase 8: VALIDATION
    │  ├─ agent_loop.run_tsc() → npx tsc --noEmit
    │  └─ agent_loop.run_chain_validation() → chain_walker.walk()
    │
    ├─ Phase 9: RETRY (up to 3 attempts)
    │  └─ inject error feedback → retry
    │
    ├─ Phase 10: LEARNING
    │  └─ _spawn_save_fix_writeback() → db.save_fix()
    │
    └─ Phase 11: DELIVERY
       ├─ Rich terminal output
       └─ rsync → cursor --remote
```

---

*Document generated: 2026-05-11*
*Source: ~/rocket-support/*