# rkt System — Dead Code and Disconnected Components Audit

## FINDING 1: cleanup_db.py
─────────────────────────────────────────────────
Type:       NEVER IMPORTED
File:       engine/cleanup_db.py
What it is: Database cleanup utility script
Why unused: Never imported anywhere in bin/ or engine/ — standalone maintenance script
Impact:     LOW — could be useful for maintenance but not part of main pipeline
Effort:     HOURS: 1 — add to bin/rkt-maintenance or delete
Action:     DELETE IT — unused maintenance script

## FINDING 2: flutter_chain_walker.py
─────────────────────────────────────────────────
Type:       NEVER IMPORTED
File:       engine/flutter_chain_walker.py
What it is: Flutter-specific chain walker for mobile projects
Why unused: Never imported — rkt-app (Flutter) uses flutter_rkt_engine.py directly
Impact:     LOW — dead Flutter support code
Effort:     HOURS: 2 — wire into rkt-app or delete
Action:     DELETE IT — duplicate of Flutter functionality in flutter_rkt_engine

## FINDING 3: flutter_dart_scanner.py
─────────────────────────────────────────────────
Type:       NEVER IMPORTED
File:       engine/flutter_dart_scanner.py
What it is: Dart/Flutter-specific probe scanner
Why unused: Never imported — Flutter scanning handled by flutter_rkt_engine
Impact:     LOW — dead Flutter code
Effort:     HOURS: 2 — wire into flutter_rkt_engine or delete
Action:     DELETE IT — unused Flutter scanner

## FINDING 4: migrate_embeddings.py
─────────────────────────────────────────────────
Type:       NEVER IMPORTED
File:       engine/migrate_embeddings.py
What it is: Embedding migration utility
Why unused: Never imported — one-time migration script
Impact:     LOW — could be useful but not in active use
Effort:     HOURS: 1 — add to docs or delete
Action:     DELETE IT — one-time use script

## FINDING 5: seed_real_patterns.py
─────────────────────────────────────────────────
Type:       NEVER IMPORTED
File:       engine/seed_real_patterns.py
What it is: Seeds database with real-world fix patterns
Why unused: Never imported — runs manually
Impact:     MEDIUM — seeds important fix patterns but could be auto-run
Effort:     HOURS: 1 — wire into init or delete
Action:     DELETE IT — manually-run seed script

## FINDING 6: report_findings()
─────────────────────────────────────────────────
Type:       NEVER CALLED
File:       engine/rkt_engine.py:384
What it is: Prints summary of findings
Why unused: Defined but never called — _print_all_findings() is used instead
Impact:     LOW — dead print function
Effort:     HOURS: 0.5 — delete or wire into main flow
Action:     DELETE IT — duplicate of _print_all_findings

## FINDING 7: top_suspicious_files()
─────────────────────────────────────────────────
Type:       NEVER CALLED
File:       engine/context_filter.py:82
What it is: Identifies suspicious files in findings
Why unused: Defined but never called
Impact:     LOW — dead utility function
Effort:     HOURS: 1 — wire into triage or delete
Action:     INVESTIGATE FIRST — purpose unclear

## FINDING 8: resolve_companions()
─────────────────────────────────────────────────
Type:       NEVER CALLED
File:       engine/finding_resolver.py:277
What it is: Resolves companion findings
Why unused: Defined but never called
Impact:     LOW — unused resolver
Effort:     HOURS: 1 — wire into finding flow or delete
Action:     INVESTIGATE FIRST — purpose unclear

## FINDING 9: slice_repo()
─────────────────────────────────────────────────
Type:       NEVER CALLED
File:       engine/slicer.py:169
What it is: Slices repository for targeted analysis
Why unused: Defined but never called
Impact:     MEDIUM — could be useful for targeted fixes
Effort:     HOURS: 2 — wire into rkt_smart or delete
Action:     DELETE IT — unused slicing functionality

## FINDING 10: format_slices_for_prompt()
─────────────────────────────────────────────────
Type:       NEVER CALLED
File:       engine/slicer.py:201
What it is: Formats slices for Claude prompt
Why unused: Defined but never called — sibling to unused slice_repo()
Impact:     LOW — dead formatting function
Effort:     HOURS: 1 — wire into slice_repo or delete
Action:     DELETE IT — unused with sibling

## FINDING 11: scan_getsession (untested)
─────────────────────────────────────────────────
Type:       UNTESTED
File:       engine/probe_scanner.py:116
What it is: Detects getSession() → getUser() issues
Why unused: No test file covers this rule
Impact:     MEDIUM — critical AUTH rule, untested
Effort:     HOURS: 2 — write test in tests/engine/test_probe_scanner.py
Action:     WIRE IT — add test coverage

## FINDING 12: scan_auth_helpers (untested)
─────────────────────────────────────────────────
Type:       UNTESTED
File:       engine/probe_scanner.py:168
What it is: Detects deprecated auth-helpers-nextjs imports
Why unused: No test file covers this rule
Impact:     MEDIUM — important deprecation rule
Effort:     HOURS: 2 — write test
Action:     WIRE IT — add test coverage

## FINDING 13: scan_stripe_webhook (untested)
─────────────────────────────────────────────────
Type:       UNTESTED
File:       engine/probe_scanner.py:212
What it is: Detects request.json() in webhooks
Why unused: No test file covers this rule
Impact:     HIGH — critical STRIPE rule (causes 400 errors)
Effort:     HOURS: 2 — write test
Action:     WIRE IT — add test coverage

## FINDING 14: scan_supabase_wrong_import (untested)
─────────────────────────────────────────────────
Type:       UNTESTED
File:       engine/probe_scanner.py:243
What it is: Detects @supabase/supabase-js in server files
Why unused: No test file covers this rule
Impact:     HIGH — critical SUPABASE rule
Effort:     HOURS: 2 — write test
Action:     WIRE IT — add test coverage

## FINDING 15: scan_client_storage_fallback (untested)
─────────────────────────────────────────────────
Type:       UNTESTED
File:       engine/probe_scanner.py:280
What it is: Detects missing localStorage fallback
Why unused: No test file covers this rule
Impact:     MEDIUM — auth refresh issue
Effort:     HOURS: 2 — write test
Action:     WIRE IT — add test coverage

## FINDING 16: scan_cookies_without_await (untested)
─────────────────────────────────────────────────
Type:       UNTESTED
File:       engine/probe_scanner.py:332
What it is: Detects cookies() without await in Next.js 15
Why unused: No test file covers this rule
Impact:     HIGH — critical AUTH rule
Effort:     HOURS: 2 — write test
Action:     WIRE IT — add test coverage

## FINDING 17: scan_env_secrets (untested)
─────────────────────────────────────────────────
Type:       UNTESTED
File:       engine/probe_scanner.py:461
What it is: Detects NEXT_PUBLIC_ on secret keys
Why unused: No test file covers this rule
Impact:     HIGH — critical ENV security rule
Effort:     HOURS: 2 — write test
Action:     WIRE IT — add test coverage

## FINDING 18: scan_missing_dynamic_export (untested)
─────────────────────────────────────────────────
Type:       UNTESTED
File:       engine/probe_scanner.py:494
What it is: Detects missing force-dynamic on auth pages
Why unused: No test file covers this rule
Impact:     MEDIUM — auth caching issue
Effort:     HOURS: 2 — write test
Action:     WIRE IT — add test coverage

## FINDING 19: scan_anon_key_format (untested)
─────────────────────────────────────────────────
Type:       UNTESTED
File:       engine/probe_scanner.py:533
What it is: Detects old sb_publishable_ format
Why unused: No test file covers this rule
Impact:     MEDIUM — Supabase key format issue
Effort:     HOURS: 2 — write test
Action:     WIRE IT — add test coverage

## FINDING 20: format_files_table()
─────────────────────────────────────────────────
Type:       NOT WIRED
File:       engine/format_output.py:102
What it is: Formats files as Rich Table
Why unused: Called in print_ready_panel but output goes to /dev/tty, never visible
Impact:     LOW — formatting exists but output captured incorrectly
Effort:     HOURS: 1 — fix output routing
Action:     INVESTIGATE FIRST — unclear if actually broken

## FINDING 21: format_code_fix()
─────────────────────────────────────────────────
Type:       NOT WIRED
File:       engine/format_output.py:117
What it is: Formats code diff as Rich Panel
Why unused: Defined but appears unused in main flow
Impact:     LOW — exists but not connected
Effort:     HOURS: 1 — find where it should be used
Action:     INVESTIGATE FIRST — purpose unclear

## FINDING 22: print_cw_finding()
─────────────────────────────────────────────────
Type:       NOT WIRED
File:       engine/format_output.py:214
What it is: Prints chain walker finding with context
Why unused: Called but output may not render properly (Rich to /dev/tty)
Impact:     MEDIUM — key output function possibly broken
Effort:     HOURS: 1 — verify output works
Action:     INVESTIGATE FIRST — critical output may be broken

## FINDING 23: 18 stub functions (early return)
─────────────────────────────────────────────────
Type:       STUB
File:       Multiple files
What it is: Helper functions that return immediately
Why unused: Many are decorator-style helpers used inline, not standalone calls
Impact:     LOW — most are actually used as inline helpers, not dead code
Effort:     N/A — review individually
Action:     INVESTIGATE FIRST — most are actually used inline

## FINDING 24: ruflo MCP server
─────────────────────────────────────────────────
Type:       MCP UNUSED (but registered)
File:       ~/.claude/settings.json
What it is: RuFlo V3 agent swarm + memory
Why unused: Registered but unclear if actively used in diagnosis flow
Impact:     MEDIUM — powerful capability not leveraged
Effort:     HOURS: 2 — integrate into rkt_smart workflow
Action:     WIRE IT — integrate into main engine

## FINDING 25: code-review-graph MCP
─────────────────────────────────────────────────
Type:       MCP UNUSED (but registered)
File:       ~/.claude/settings.json
What it is: Structural code analysis
Why unused: Registered but not called in engine pipeline
Impact:     MEDIUM — could enhance triage
Effort:     HOURS: 3 — integrate into triage_graph
Action:     WIRE IT — add to triage pipeline

---

## GROUP A — HIGH IMPACT, LOW EFFORT (wire these first)

| Finding | Effort | Impact | Action |
|---------|--------|--------|--------|
| scan_stripe_webhook test | 2h | HIGH | Add test |
| scan_supabase_wrong_import test | 2h | HIGH | Add test |
| scan_cookies_without_await test | 2h | HIGH | Add test |
| scan_env_secrets test | 2h | HIGH | Add test |
| ruflo MCP integration | 2h | MEDIUM | Wire into engine |
| code-review-graph integration | 3h | MEDIUM | Add to triage |

## GROUP B — HIGH IMPACT, HIGH EFFORT

| Finding | Effort | Impact | Action |
|---------|--------|--------|--------|
| print_cw_finding output fix | 1h | MEDIUM | Investigate |
| slice_repo() wire in | 2h | MEDIUM | Wire or delete |

## GROUP C — LOW IMPACT (cleanup)

| Finding | File | Action |
|---------|------|--------|
| cleanup_db.py | engine/cleanup_db.py | DELETE |
| flutter_chain_walker.py | engine/flutter_chain_walker.py | DELETE |
| flutter_dart_scanner.py | engine/flutter_dart_scanner.py | DELETE |
| migrate_embeddings.py | engine/migrate_embeddings.py | DELETE |
| seed_real_patterns.py | engine/seed_real_patterns.py | DELETE |
| report_findings() | rkt_engine.py:384 | DELETE |
| slice_repo() | slicer.py:169 | DELETE |
| format_slices_for_prompt() | slicer.py:201 | DELETE |

## GROUP D — INVESTIGATE FIRST

| Finding | File | Notes |
|---------|------|-------|
| top_suspicious_files() | context_filter.py:82 | Unclear purpose |
| resolve_companions() | finding_resolver.py:277 | Unclear purpose |
| format_files_table() | format_output.py:102 | Output may not render |
| format_code_fix() | format_output.py:117 | Unused formatter |
| 18 stub functions | Multiple | Most are inline helpers |

---

## SUMMARY TABLE

| # | Finding | File | Type | Impact | Effort | Action |
|---|---------|------|------|--------|--------|--------|
| 1 | cleanup_db.py | engine/cleanup_db.py | NEVER IMPORTED | LOW | 1h | DELETE |
| 2 | flutter_chain_walker.py | engine/flutter_chain_walker.py | NEVER IMPORTED | LOW | 2h | DELETE |
| 3 | flutter_dart_scanner.py | engine/flutter_dart_scanner.py | NEVER IMPORTED | LOW | 2h | DELETE |
| 4 | migrate_embeddings.py | engine/migrate_embeddings.py | NEVER IMPORTED | LOW | 1h | DELETE |
| 5 | seed_real_patterns.py | engine/seed_real_patterns.py | NEVER IMPORTED | LOW | 1h | DELETE |
| 6 | report_findings() | rkt_engine.py:384 | NEVER CALLED | LOW | 0.5h | DELETE |
| 7 | top_suspicious_files() | context_filter.py:82 | NEVER CALLED | LOW | 1h | INVESTIGATE |
| 8 | resolve_companions() | finding_resolver.py:277 | NEVER CALLED | LOW | 1h | INVESTIGATE |
| 9 | slice_repo() | slicer.py:169 | NEVER CALLED | MEDIUM | 2h | DELETE |
| 10 | format_slices_for_prompt() | slicer.py:201 | NEVER CALLED | LOW | 1h | DELETE |
| 11 | scan_getsession | probe_scanner.py:116 | UNTESTED | MEDIUM | 2h | WIRE |
| 12 | scan_auth_helpers | probe_scanner.py:168 | UNTESTED | MEDIUM | 2h | WIRE |
| 13 | scan_stripe_webhook | probe_scanner.py:212 | UNTESTED | HIGH | 2h | WIRE |
| 14 | scan_supabase_wrong_import | probe_scanner.py:243 | UNTESTED | HIGH | 2h | WIRE |
| 15 | scan_client_storage_fallback | probe_scanner.py:280 | UNTESTED | MEDIUM | 2h | WIRE |
| 16 | scan_cookies_without_await | probe_scanner.py:332 | UNTESTED | HIGH | 2h | WIRE |
| 17 | scan_env_secrets | probe_scanner.py:461 | UNTESTED | HIGH | 2h | WIRE |
| 18 | scan_missing_dynamic_export | probe_scanner.py:494 | UNTESTED | MEDIUM | 2h | WIRE |
| 19 | scan_anon_key_format | probe_scanner.py:533 | UNTESTED | MEDIUM | 2h | WIRE |
| 20 | format_files_table() | format_output.py:102 | NOT WIRED | LOW | 1h | INVESTIGATE |
| 21 | format_code_fix() | format_output.py:117 | NOT WIRED | LOW | 1h | INVESTIGATE |
| 22 | print_cw_finding() | format_output.py:214 | NOT WIRED | MEDIUM | 1h | INVESTIGATE |
| 23 | 18 stub functions | Multiple | STUB | LOW | varies | INVESTIGATE |
| 24 | ruflo MCP | settings.json | MCP UNUSED | MEDIUM | 2h | WIRE |
| 25 | code-review-graph MCP | settings.json | MCP UNUSED | MEDIUM | 3h | WIRE |

---

## PRIORITY ORDER (Top 5 to wire)

1. **scan_stripe_webhook test** (2h, HIGH impact) — critical STRIPE rule causing 400 errors
2. **scan_cookies_without_await test** (2h, HIGH impact) — Next.js 15 breaking change
3. **scan_env_secrets test** (2h, HIGH impact) — security vulnerability detection
4. **scan_supabase_wrong_import test** (2h, HIGH impact) — deprecated import detection
5. **ruflo MCP integration** (2h, MEDIUM impact) — powerful agent swarm capability

---

## DELETION LIST (Safe to delete immediately)

1. `engine/cleanup_db.py` — never imported, maintenance script
2. `engine/flutter_chain_walker.py` — duplicate Flutter code
3. `engine/flutter_dart_scanner.py` — unused Flutter scanner
4. `engine/migrate_embeddings.py` — one-time migration
5. `engine/seed_real_patterns.py` — manual seed script
6. `engine/rkt_engine.py:report_findings()` — duplicate of _print_all_findings
7. `engine/slicer.py:slice_repo()` — never called
8. `engine/slicer.py:format_slices_for_prompt()` — unused with slice_repo

---

## STATISTICS

- **Total findings**: 25
- **Group A (wire first)**: 6
- **Group B (high effort)**: 2
- **Group C (delete)**: 8
- **Group D (investigate)**: 9
- **Never imported files**: 5
- **Never called functions**: 5
- **Untested probe_scanner rules**: 9 of 12 (75%)
- **MCP servers unused**: 2 of 7 (ruflo, code-review-graph)

---

## RECOMMENDATIONS

### Immediate Actions
1. Add tests for the 9 untested probe_scanner rules (highest ROI)
2. Delete the 8 safe-to-delete files/functions
3. Investigate print_cw_finding() output issue — critical for diagnosis output

### Short-term
1. Integrate ruflo MCP into main engine workflow
2. Add code-review-graph to triage pipeline
3. Clean up 18 stub functions — most are inline helpers, some can be deleted

### Long-term
1. Consider consolidating Flutter engines (flutter_chain_walker + flutter_dart_scanner + flutter_rkt_engine)
2. Audit remaining unused imports in Command 1 output