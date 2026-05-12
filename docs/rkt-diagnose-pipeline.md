# rkt-diagnose Pipeline

---

## Short Version

### rkt-diagnose Pipeline — Quick Reference

Engineer runs: `rkt-diagnose <threadId> "hint"`

```
[1/11] INIT          rocket clean → rocket init → detect project folder → install cursor-rules
[2/11] RSYNC         remote project → /tmp/rkt-diagnose-<threadId>/ (excl node_modules/.next/.git)
[3/11] FINGERPRINT   score 7 project types from deps + SQL keywords + file patterns
[4/11] PERCEIVE      chain_walker → probe_scanner → schema_checker → context_filter → dedup (sequential)
[5/11] RETRIEVE      hybrid_lookup: SemanticIndex 512-dim + BrainFTS tantivy BM25 → RRF merge
[6/11] PLAN          score_and_route: per-finding confidence → overall fix_mode (AUTO/GUIDED/CLAUDE/MANUAL)
[7/11] SLICE         slicer.py tree-sitter up to 40 lines → 7-line _extract_minimal_context() fallback
[8/11] ACT           PATH A: brain.db diff direct (0 tokens) | PATH B: claude-sonnet-4-5 surgical JSON
[9/11] APPLY         _verify_change_safe() ±2 lines → write .rkt_*.tmp → os.replace() atomic
[10/11] VALIDATE     oxc → tsc --noEmit → chain_walker rescan — if fail → retry (max 3 attempts)
[11/11] DELIVER      rsync fixed files → remote → npm install → open Cursor → rocket push
```

Engineer does: review diff in Cursor → `rocket push`

---

### Confidence Routing

| Confidence | Threshold | fix_mode | What happens |
|---|---|---|---|
| HIGH | avg ≥ 0.85 AND auto_count > 0 | AUTO | Apply, validate, rsync back |
| MED | avg 0.60–0.84 | GUIDED | Apply with "review carefully" warning |
| LOW | avg 0.40–0.59 | CLAUDE | Apply if Claude confident, else skip |
| MANUAL | avg < 0.40 | MANUAL | No auto-apply — investigate in Cursor |
| DB only | capped at 0.74 | never AUTO alone | Informs Claude prompt only |

---

### Typical Cost per Ticket

| Phase | Typical time | Cost |
|---|---|---|
| rsync pull | ~900ms | free |
| perception (all sequential nodes) | ~165ms | free |
| retrieval (hybrid_lookup) | ~67ms | free |
| Claude API (PATH B, claude-sonnet-4-5) | ~2300ms | ~$0.006/ticket |
| tsc --noEmit validation | ~4800ms | free |
| rsync back | ~900ms | free |
| **total** | **~8–10s** | **~$0.006/ticket** |

Cost formula from `tracer.py:trace_claude`: `(input_tokens × $3 + output_tokens × $15) / 1,000,000`

---

---

## Detailed Version

### rkt-diagnose Pipeline — Full Technical Reference

---

### Step 1: SSH Init

**What runs:** `bin/rkt-diagnose` — argument parsing + three SSH commands  
**Input:** `<threadId>` (e.g. `DC-MAY-12`), optional `[hint]`, optional `[--shadow]`  
**Output:** `$PROJECT_FOLDER` detected, `$REMOTE_PROJECT_PATH` set, cursor-rules installed  
**Failure mode:** `fail "rocket init failed"` if response lacks `"code":"OK"`; `fail "Could not detect project folder"` if `ls -t ~/app` is empty  
**Code:** `bin/rkt-diagnose` → lines 66–90

Sub-steps in order:
1. `echo 'y' | rocket clean` on remote — clears existing container project (non-fatal if fails)
2. `printf '1\ny\n' | rocket init $THREAD_ID` — initialises project on remote container
3. `ls -t /home/ubuntu/app | head -1` — detects new project folder name
4. `rkt-rules-add` — installs cursor-rules-v34 to remote (silent, non-fatal)

SSH host is hardcoded: `support-vedang-patel`. Remote app dir: `/home/ubuntu/app`. Cursor is not opened yet.

---

### Step 2: rsync Pull

**What runs:** `bin/rkt-diagnose` — `rsync -az --quiet`  
**Input:** `$SSH_HOST:$REMOTE_PROJECT_PATH/`  
**Output:** local copy at `LOCAL_TMP` = `/tmp/rkt-diagnose-<threadId>/`  
**Failure mode:** `fail "rsync failed — $LOCAL_TMP is empty"` if `ls -A $LOCAL_TMP` returns nothing  
**Code:** `bin/rkt-diagnose` → lines 93–102

Excludes: `node_modules`, `.next`, `.git`, `dist`, `.turbo`, `*.log`

`LOCAL_TMP` is intentionally kept after the session — engineer can inspect files or re-run the engine against it without re-pulling.

---

### Step 3: Fingerprint

**What runs:** `engine/fingerprint.py:fingerprint()` via `triage_graph.node_fingerprint()`  
**Input:** `repo_path` — absolute path to local temp dir  
**Output:** dict with `project_type`, `confidence`, `category`, `common_failure`, `has_supabase`, `has_stripe`, `env_vars`, `sql_files_found`  
**Failure mode:** confidence < 0.05 triggers heuristic fallback (`confidence=0.3`, `used_fallback=True`)  
**Code:** `engine/fingerprint.py` → `fingerprint()`, `_score_project_type()`

Three signal weights per type:

| Signal | Weight | Source |
|---|---|---|
| Dependency matches | 0.40 | `package.json` dependencies + devDependencies |
| SQL table keyword matches | 0.40 | `supabase/migrations/*.sql` |
| File pattern matches | 0.20 | `os.walk` with `fnmatch` |

Tie-break penalty: if a type's identity is dep-driven and zero deps matched, `score *= 0.5`.

Seven types: `SaaS`, `E-Commerce`, `AI`, `Booking`, `Landing`, `Blog`, `Unknown`

---

### Step 4: Perception Layer

All nodes run **sequentially** inside `triage_graph.run_triage()`. No early exit — every node always runs.

---

#### Step 4a: chain_walker

**What runs:** `engine/chain_walker.py:walk()`  
**Input:** `repo_path`  
**Output:** list of `{chain, broken_at, missing, issue, fix_hint, confidence}` — one per chain at most  
**Failure mode:** missing files are silently skipped — never treated as breaks; returns `[]` if all chains pass  
**Code:** `engine/chain_walker.py` → `walk()` → `_walk_chain()`

Preconditions:
- `AUTH` runs only if `@supabase` in `package.json`
- `STRIPE` runs only if `stripe` in `package.json`
- `RLS` runs only if `supabase/migrations/` directory exists
- `ENV` runs if `@supabase` OR `stripe` in `package.json`

**AUTH chain** (`AUTH_CHAIN`):
1. `middleware.ts` — must contain `updateSession`
2. `lib/supabase/server.ts` — must contain `createServerClient`
3. `app/auth/callback/route.ts` — must contain `exchangeCodeForSession`
4. `lib/supabase/client.ts` — if `createBrowserClient` present, must also have `localStorage` fallback
5. `src/lib/supabase/client.ts` — same localStorage check for src/ layout

**STRIPE chain:**
1. `**/webhooks/stripe/route.ts` — must contain `request.text()`
2. `**/webhooks/stripe/route.ts` — must contain `constructEvent`
3. `**/stripe/checkout/route.ts` — must contain `metadata` and `user_id`

**RLS chain:**
1. `supabase/migrations/*.sql` — must contain `on_auth_user_created`
2. `supabase/migrations/*.sql` — must contain `enable row level security`

**ENV chain:**
1. `.env.local` — must contain `SUPABASE_SERVICE_ROLE_KEY`
2. `.env.production` — must contain `SUPABASE_SERVICE_ROLE_KEY`
3. `.env.local` — must contain `STRIPE_WEBHOOK_SECRET`
4. `.env.production` — must contain `STRIPE_WEBHOOK_SECRET`

Confidence is always `1.0` when a finding is produced (exact string match).  
Pure Python, no subprocess — completes in under 1 second.

---

#### Step 4b: probe_scanner

**What runs:** `engine/probe_scanner.py:run_probe_scanner()`  
**Input:** `repo_path`  
**Output:** `{"available": True, "findings": [...], "errors": [...], "scanner": "probe"}`  
**Failure mode:** each scanner is isolated — one exception does not abort others  
**Code:** `engine/probe_scanner.py` → `run_probe_scanner()`

File collection: uses `fd` if on PATH, falls back to `os.walk` skipping `node_modules`, `.next`, `.git`, `dist`, `.turbo`.

**AST-based scanners** (use `ast_grep_py.SgRoot`; fall back to ripgrep if `ast_grep_py` not importable):

| Rule | Function | Pattern |
|---|---|---|
| 1 | `scan_getsession()` | `$CLIENT.auth.getSession()` → getUser |
| 6 | `scan_cookies_without_await()` | `const/let $STORE = cookies()` without `await` |
| 9 | `scan_headers_without_await()` | `const/let $H = headers()` without `await` |
| 12 | `scan_missing_revalidate()` | `use server` file mutates data without `revalidatePath` (plain regex) |

**ripgrep-based scanners:**

| Rule | Function | What it finds | Category |
|---|---|---|---|
| 2 | `scan_auth_helpers()` | `auth-helpers-nextjs` / `createClientComponentClient` imports | AUTH |
| 4 | `scan_stripe_webhook()` | `await *.json()` in webhook/stripe files | STRIPE |
| 5 | `scan_supabase_wrong_import()` | `@supabase/supabase-js` in server files | AUTH |
| 7 | `scan_env_secrets()` | `NEXT_PUBLIC_*SERVICE_ROLE*` in `.env*` files | ENV |
| 8 | `scan_missing_dynamic_export()` | `auth.getUser()` in page.tsx without `force-dynamic` | AUTH |
| 10 | `scan_anon_key_format()` | `ANON_KEY=eyJ` (old JWT format) in `.env*` | SUPABASE |
| 11 | `scan_use_client_server_import()` | `createServerClient` in `'use client'` file | AUTH |
| 13 | `scan_client_storage_fallback()` | `createBrowserClient` in client.ts without `localStorage` | AUTH |

Rule 3 (middleware-wrong-location) is explicitly skipped — chain_walker handles it.

---

#### Step 4c: schema_checker

**What runs:** `engine/schema_checker.py:check()`  
**Input:** `repo_path`  
**Output:** list of `{check, found, file, fix_hint}` — `found=False` means the required pattern is missing  
**Failure mode:** returns `[]` immediately if `supabase/migrations/` does not exist  
**Code:** `engine/schema_checker.py` → `check()`

Reads all `supabase/migrations/*.sql` in sorted order, concatenates, checks:

| Check ID | Method | Needle |
|---|---|---|
| `trigger:on_auth_user_created` | string | `on_auth_user_created` |
| `rls:enable_row_level_security` | string | `enable row level security` |
| `foreign_key:on_delete_cascade` | string | `on delete cascade` |
| `rls:insert_policy` | string | `for insert` |
| `schema:timestamptz` | regex | bare `TIMESTAMP` not followed by `WITH TIME ZONE` or `TZ` |

`found=True` is good; `found=False` flows into scoring and the Claude prompt.

---

#### Step 4d: context_filter → dedup → symptom_rank

Three sequential pipeline nodes that post-process all raw findings:

**`node_context_filter`** (`engine/context_filter.py:filter_findings()`): wraps each raw finding in a source-tagged envelope `{source, finding, fix_mode, confidence}`, filters suppressed findings. Produces `filtered_findings` and `suppressed_findings`.

**`node_deduplicate`** (`engine/dedup.py:deduplicate()`): merges overlapping findings from different sources pointing to the same location. Promotes confidence on merged entries.

**`node_symptom_rank`** (`engine/symptom_ranker.py:rank_findings()`): re-ranks `findings_scored` by relevance to the issue description hint; sets `symptom_category`.

**Code:** `engine/triage_graph.py` → `node_context_filter()`, `node_deduplicate()`, `node_symptom_rank()`

---

### Step 5: Hybrid Retrieval

**What runs:** `engine/db.py:hybrid_lookup()` called via `triage_graph.node_db_lookup()` → `rkt_engine.db_lookup()`  
**Input:** query string (hint or fingerprint `common_failure`), optional `category`  
**Output:** top-1 brain.db fix dict with `_score=0.75`, or `None`  
**Failure mode:** if both semantic and FTS fail → falls back to `find_similar()` (numpy cosine); returns `None` if best score < 0.15  
**Code:** `engine/db.py` → `hybrid_lookup()` → `SemanticIndex.search()` + `BrainFTS.search()` → `_rrf_merge()`

**SemanticIndex** (usearch or numpy fallback):
- Embeddings: numpy word unigram + bigram hashing into 512-dim buckets via `hashlib.md5` (deterministic, `_numpy_word_embed()`)
- ANN search: usearch index (cosine) if `usearch` installed; falls back to numpy dot product against dense matrix
- Index stored at `~/.rocket-support/brain.usearch` + `brain.idmap.pkl`
- Rebuilt in background thread on every `save_fix()` call
- `sentence-transformers` is tried first via `_embed()` for stored embeddings in fixes table, but SemanticIndex query path always uses `_numpy_word_embed` directly

**BrainFTS** (tantivy):
- Index stored at `~/.rocket-support/brain_fts/`
- Schema: `fix_id` (raw), `category` (raw), `symptom` (en_stem), `error_msg` (en_stem), `fix_summary` (en_stem)
- Only indexes `verified=1` fixes — engineer confirmation is the quality gate
- Query searches `symptom`, `error_msg`, `fix_summary`
- **Code:** `engine/brain_fts.py` → `BrainFTS.search()`

**RRF merge** (`_rrf_merge()`):
```python
scores[db_id] += 1.0 / (60 + rank + 1)   # for each result in each list
```
Returns top-3 merged IDs. Engine fetches top-1 that matches optional category filter. `_score` is set to `0.75` (hybrid match sentinel).

**Confidence cap in scoring:** `min(float(db_match.get("_score", 0.75)), 0.74)` — a pattern match alone never reaches the 0.85 AUTO threshold.

---

### Step 6: Confidence Scoring and Routing

**What runs:** `engine/triage_graph.py:node_score_and_route()` → `_score_and_route_impl()`  
**Input:** `deduped_findings`, `db_match`, `fingerprint`  
**Output:** `findings_scored`, `overall_confidence`, `fix_mode`, `auto_fixable_count`  
**Failure mode:** returns `fix_mode="MANUAL"`, `overall_confidence=0.0` if no findings  
**Code:** `engine/triage_graph.py` → `_score_and_route_impl()`, `_score_cw_finding()`, `_score_semgrep_finding()`, `_score_schema_finding()`

**Per-finding confidence — chain_walker** (`_score_cw_finding()`):

| Finding | fix_mode | confidence |
|---|---|---|
| STRIPE chain | AUTO | 0.99 |
| AUTH — middleware issue or broken_at | MANUAL | 0.85 |
| AUTH — server.ts broken_at | AUTO | 0.97 |
| AUTH — other | GUIDED | 0.75 |

**Per-finding confidence — probe_scanner** (`_score_semgrep_finding()`):

| check_id contains | fix_mode | confidence |
|---|---|---|
| `webhook`, `cookies`, `auth-helpers` | AUTO | 0.97 |
| `missing-dynamic`, `dynamic` | AUTO | 0.95 |
| `getsession`, `get-session` | AUTO | 0.97 |
| `probe-scanner-failed` | MANUAL | 0.20 |
| default | GUIDED | 0.75 |

**Per-finding confidence — schema_checker** (`_score_schema_finding()`):

| check contains | fix_mode | confidence |
|---|---|---|
| `rls` | GUIDED | 0.88 |
| `trigger` or `on_auth` | GUIDED | 0.90 |
| other | GUIDED | 0.72 |

**Overall fix_mode** (`_overall_fix_mode()`):

| Condition | fix_mode |
|---|---|
| avg_conf ≥ 0.85 AND auto_count > 0 | AUTO |
| avg_conf ≥ 0.60 | GUIDED |
| avg_conf ≥ 0.40 | CLAUDE |
| else | MANUAL |

---

### Step 7: Surgical Context Extraction

**What runs:** `engine/claude_agent.py:_get_surgical_context()` → `engine/slicer.py:slice_file()` with `engine/claude_agent.py:_extract_minimal_context()` fallback  
**Input:** `file_path`, `line_num`, `repo_path`  
**Output:** string — tree-sitter function slice or 7-line window, formatted with line numbers and `>>>` marker  
**Failure mode:** any exception in slicer silently falls through to `_extract_minimal_context()`  
**Code:** `engine/claude_agent.py` → `_get_surgical_context()` → `engine/slicer.py` → `slice_file()`

**slicer.py primary path (tree-sitter):**
- Reuses parser from `fix_writer.py` (shared `_TS_PARSER`)
- Keyword set: `AUTH_KEYWORDS | STRIPE_KEYWORDS` — getUser, getSession, createServerClient, createBrowserClient, updateSession, supabase.auth, constructEvent, stripe.webhooks, request.text, request.json, STRIPE_WEBHOOK_SECRET
- Collects all function/arrow/method nodes via AST walk
- Selects node whose `start_line–end_line` contains `line_num`; if none, picks closest by start_line distance
- `max_lines=40` — truncates with `// ... (N lines truncated)` comment if function exceeds 40 lines
- Returns `{file, function_name, start_line, end_line, source, keywords_found}`
- Falls back to first 4,000 chars of file as single slice if tree-sitter parser is unavailable

**`_extract_minimal_context()` fallback (7-line window):**
- `start = max(0, line_num - 4)` — 3 lines before the broken line
- `end = min(len(lines), line_num + 3)` — 3 lines after
- Marks broken line with `>>>`, all others with `   `

---

### Step 8: Claude API Fix Call (PATH A or PATH B)

**What runs:** `engine/claude_agent.py:ClaudeAgent.fix()`  
**Input:** `findings` (normalized), `repo_path`, `db_match`, `hint`, `shadow`  
**Output:** `AgentResult(success, changes_applied, root_cause, confidence, tokens_used, path_used)`  
**Failure mode:** returns `AgentResult(success=False, error=...)` — caller in `agent_loop` retries up to 3 times  
**Code:** `engine/claude_agent.py` → `fix()` → `_apply_known_diff()` or `_claude_api_fix()`

---

#### PATH A — brain.db diff applies directly

**Condition:** `db_match` has `fix_diff` starting with `---` AND old content from diff found verbatim in target file (`_diff_is_applicable()`).

Steps:
1. `_parse_diff()` extracts `(rel_file, old_block, new_block)` from unified diff
2. `_resolve_file()` tries `repo_path/rel_file` then `repo_path/src/rel_file`
3. Verifies `old_stripped in content`
4. `content.replace(old_stripped, new_stripped, 1)` — if no change, falls back to `_line_replace()` (strip-and-match preserving original indent)
5. `_write_atomic()` writes atomically
6. Returns `AgentResult(path_used="brain_db_diff", tokens_used=0, confidence="HIGH")`

Zero tokens. Typically < 1ms.

---

#### PATH B — Claude API surgical call

**Condition:** PATH A not applicable or failed.

**Model:** `claude-sonnet-4-5`, `max_tokens=1000`  
**System prompt:** `"You are a surgical code fixer. Return only valid JSON. Never explain. Never use markdown."`

**User prompt structure:**
```
TICKET: <hint>
ISSUE: <finding message>
FILE: <relative path>
LINE: <line number>
CONTEXT (function containing the broken line, >>> marks the problem):
<slicer output>
KNOWN PATTERN FROM DATABASE:
<db_match pattern + fix_diff[:300] if available>

PLANNING STEP — required before JSON output:
State in exactly one sentence what change you will make.
Format: "I will change [old content] to [new content] in [file] at line [N]."
If you cannot state this precisely → return empty changes array.

[JSON rules + schema]
```

**JSON schema Claude must return:**
```json
{
  "root_cause": "one sentence",
  "changes": [
    {"file": "rel/path", "line": N, "old": "exact content", "new": "replacement"}
  ],
  "confidence": "HIGH|MED|LOW"
}
```
Maximum 3 changes. Empty `changes` array → `AgentResult(success=False)`.

**Response parsing:**
1. Extract ` ```json ... ``` ` fenced block first
2. Strip all fence markers, find first `{ ... }` block
3. `json.loads()` — invalid JSON returns `AgentResult(success=False, error="Claude returned invalid JSON")`

**Code:** `engine/claude_agent.py` → `_claude_api_fix()` (lines 347–555)

---

### Step 9: Apply Changes Atomically

**What runs:** `engine/claude_agent.py` apply loop → `_verify_change_safe()` + `_write_atomic()`  
**Input:** each `change` dict from Claude's JSON — `{file, line, old, new}`  
**Output:** change written to disk; entry added to `changes_applied` list  
**Failure mode:** change is silently skipped (not retried) if `_verify_change_safe()` returns False  
**Code:** `engine/claude_agent.py` → lines 499–536, `_verify_change_safe()`, `_write_atomic()`

**Safety check `_verify_change_safe()`:**
1. Check exact line: `old_stripped in lines[line_idx].strip()`
2. Check offsets −2, −1, +1, +2: updates `change["line"]` to actual line if found there
3. Returns `False` if no match — change is skipped entirely

**Atomic write `_write_atomic()`:**
1. `tempfile.mkstemp(prefix=".rkt_", suffix=".tmp", dir=<same dir as target>)`
2. Write full new content to temp file
3. `os.replace(tmp, path)` — atomic POSIX rename
4. On any exception: `os.unlink(tmp)` cleanup, then re-raise

**Indentation preservation:** strips leading whitespace from Claude's `new` content, prepends original line's indent length in spaces.

---

### Step 10: Validation Loop

**What runs:** `engine/agent_loop.py:run_fix_loop()`  
**Input:** `findings`, `repo_path`, `db_match`, `hint`, `shadow=False`, `max_attempts=3`  
**Output:** `LoopResult(success, attempts, final_result, validation_passed, tsc_errors, chain_errors)`  
**Failure mode:** after 3 attempts, returns `LoopResult(success=False, error="Failed after 3 attempts")`  
**Code:** `engine/agent_loop.py` → `run_fix_loop()`

**Three validation gates per attempt (in order):**

**Gate 1 — oxc** (`run_oxc_validation()` → `fix_validator.validate_fix_plan()`):
- Targets changed `.ts/.tsx` files only
- Writes each file to a `/tmp` copy, runs `oxlint` or `oxc` binary
- Non-blocking: if neither binary on PATH, returns `(True, [])`
- **Code:** `engine/agent_loop.py` → `run_oxc_validation()`, `engine/fix_validator.py` → `validate_fix_plan()`

**Gate 2 — tsc** (`run_tsc()`):
- `npx tsc --noEmit --pretty false` in `repo_path`
- 30-second timeout; returns `(True, [])` on timeout or `FileNotFoundError`
- Parses stdout+stderr for lines containing `error TS` or `Error:`

**Gate 3 — chain_walker rescan** (`run_chain_validation()`):
- Re-runs `chain_walker.walk(repo_path)`
- Checks if any original `broken_at` locations still appear in new findings
- Returns `(True, [])` on any exception

**Retry prompt on failure:**
```
<original_hint>

[Attempt N applied changes but validation failed]
tsc: PASS|FAIL
chain_walker: PASS|FAIL
Errors:
<actual error lines>

Fix these errors. Do not repeat the previous approach.
```
Oxc failure uses: `[Attempt N — oxc syntax errors in changed files]`

---

### Step 11: Delivery

**What runs:** `bin/rkt-diagnose` — rsync back, npm install, Cursor open  
**Input:** `RESULT_FILE` (`.rkt_result.json`) checked for `fixes_applied=True`  
**Output:** fixed files on remote container; Cursor opened to project  
**Failure mode:** rsync back and npm install are non-fatal (no exit check)  
**Code:** `bin/rkt-diagnose` → lines 119–151

Steps:
1. Read `fixes_applied` from `.rkt_result.json` — rsync back only runs if `True`
2. Delete `RESULT_FILE` before rsync so it never lands in the project
3. `rsync -az --quiet` from `LOCAL_TMP/` to `$SSH_HOST:$REMOTE_PROJECT_PATH/` — same excludes as pull
4. `npm install --prefer-offline --quiet` on remote (stdout suppressed, non-fatal)
5. Prompt: `[Enter to open · Ctrl+C to skip]`
6. `cursor --remote "ssh-remote+$SSH_HOST" "$REMOTE_PROJECT_PATH"` — launched in background

Session ends with: `When done:  rkt-done`

---

## Brain.db Learning Loop

Every successful fix feeds back through two channels:

**Auto-save on success (`verified=0`):**
- Triggered in `diagnose_output.py:_spawn_save_fix_writeback()` after any successful fix
- Runs in a daemon thread — non-blocking, best-effort
- Calls `db.save_fix(pattern, error_signature, category, fix_diff, project_type, verified=0)`
- `verified=0` means unconfirmed — improves retrieval but not used by BrainFTS (which requires `verified=1`)
- Each `save_fix()` triggers `SemanticIndex.rebuild_from_db()` in a background thread

**Engineer confirmation via `rkt-done` (`verified=1`):**
- Engineer confirms fix worked after `rocket push`
- `db.save_fix(..., verified=1)` called — triggers `rebuild_indexes.sh` as a subprocess
- `rebuild_indexes.sh` rebuilds both SemanticIndex (usearch) and BrainFTS (tantivy)
- BrainFTS **only** indexes `verified=1` rows — this is the quality gate for pattern search

**Growth mechanics:**
- `save_fix()` uses `SHA-256(pattern)[:16]` as row ID — duplicate patterns increment `uses`, no duplicate rows
- `uses` counter visible in `brain-inject.sh` session startup output
- 11 built-in fixes from `seed_builtin_fixes()` are all `verified=1` — they seed BrainFTS immediately on first run

---

## Failure Modes and Escalation

**HIGH confidence, validation passes:**
```
✓  2 changes · Claude API · 847 tokens
CHANGES APPLIED:
───────────────────────────────────────────────────────
middleware.ts              line 12   getSession → getUser
───────────────────────────────────────────────────────
  1 file changed · review in Cursor · then: rocket push
```

**HIGH confidence, validation fails after 3 retries:**
```
⚠  validation failed
  ⚠ tsc errors — review in Cursor
  - middleware.ts(12,5): error TS2345: ...
  ⚠ violations persist — review in Cursor
```
Fix IS rsync'd back. `loop_result.validation_passed = False`. Engineer reviews in Cursor.

**MED confidence (0.60–0.84):**
```
⚠  MED confidence — review carefully · 1 change · Claude API · 612 tokens
```

**LOW confidence (< 0.60):**
```
⚠  LOW confidence (48%) — investigate in Cursor
  LOW confidence — open Cursor and investigate manually
```
No files changed. rsync back does not run.

**Shadow mode (`--shadow` flag):**
```
⚠  SHADOW MODE — diagnosis only, no files will be modified
  shadow — 2 change(s) would apply · Claude API · 847 tokens
WOULD APPLY (shadow — no files modified):
  middleware.ts              line 12   getSession → getUser
```

---

## Known Limitations

**ast-grep calls may be zero:**  
`_AST_GREP_AVAILABLE` is set at import time by `from ast_grep_py import SgRoot`. If `ast_grep_py` is not installed in the engine venv, Rules 1, 6, and 9 fall through to ripgrep regex patterns. The ripgrep fallback is functional but cannot distinguish structural context (e.g., `await cookies()` vs `cookies()` in a complex expression) as cleanly as AST matching.

**brain.db size is small initially:**  
11 seeded `verified=1` fixes on a fresh install. Pattern retrieval improves only as real tickets are processed and confirmed via `rkt-done`.

**tsc validation adds 4–5 seconds per attempt:**  
With max 3 retries, worst case is ~15 seconds of tsc time per ticket.

**RLS and schema findings are never AUTO-fixed:**  
schema_checker findings score GUIDED (0.72–0.90) — they never reach the AUTO threshold on their own. The engine identifies the issue and informs the Claude prompt, but the SQL migration must be run manually in the Supabase SQL editor.

**Infrastructure issues are not fixable:**  
Orphan routes, misconfigured rewrites, deploy target errors, and similar infrastructure problems cannot be fixed through file edits. These require escalation.

**`node_validate_fix` in triage_graph is currently inactive:**  
`triage_graph.node_validate_fix()` checks `if not fix_plan: return {}`. `fix_plan` is never populated by the triage pipeline itself — it is built separately in `diagnose_output.py` after `run_triage()` returns. The oxc gate for triage-time validation is therefore always a no-op. Oxc validation runs in `agent_loop.py` instead.

**Middleware fix bypasses Claude entirely:**  
AUTH chain findings with `fix_mode="MANUAL"` (middleware missing `updateSession`) are handled by `diagnose_output.py:_invoke_claude_manual_fixes()` — a deterministic Python rewriter that does not call the Claude API. It finds `updateSession` export location and either rewrites the function body or replaces the whole file with a canonical inline template.

---

## File Reference

| File | Entry point | Purpose |
|---|---|---|
| `bin/rkt-diagnose` | — | SSH init, rsync pull/back, Cursor open |
| `engine/diagnose_output.py` | `main()` | Steps 2–4: triage, fix, validate, output |
| `engine/triage_graph.py` | `run_triage()` | 12-node sequential pipeline |
| `engine/fingerprint.py` | `fingerprint()` | Project type detection from signals |
| `engine/chain_walker.py` | `walk()` | AUTH / STRIPE / RLS / ENV chain traces |
| `engine/probe_scanner.py` | `run_probe_scanner()` | 12 active rules, ast-grep + ripgrep |
| `engine/schema_checker.py` | `check()` | SQL migration auditor (5 checks) |
| `engine/db.py` | `hybrid_lookup()` | SemanticIndex + BrainFTS + RRF retrieval |
| `engine/brain_fts.py` | `BrainFTS.search()` | Tantivy BM25 full-text search |
| `engine/slicer.py` | `slice_file()` | Tree-sitter function extraction (40-line max) |
| `engine/claude_agent.py` | `ClaudeAgent.fix()` | PATH A (diff) + PATH B (Claude API) |
| `engine/agent_loop.py` | `run_fix_loop()` | oxc → tsc → chain_walker, max 3 retries |
| `engine/fix_validator.py` | `validate_fix_plan()` | oxlint on changed .ts/.tsx files |
| `engine/tracer.py` | `trace()` | Phase timing + tool call logging |