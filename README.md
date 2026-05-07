# Rocket-Support — rkt

Three commands. Unzip → triage → fix → deliver. Under 10 seconds to diagnosis.

Built for Rocket.new support engineers. Unzip a client project, get a root cause diagnosis, apply fixes automatically or via Cursor/Claude, then deliver a clean zip back to the client.

---

## What's New (May 2026)

### Intelligence System — 5-Tier Upgrade

A complete overhaul of the diagnosis intelligence layer, raising accuracy from **35-45% → targeting 85-90%** across all ticket types.

**Tier 1 — Data + Retrieval (done)**
- Replaced 128-dim character n-gram embeddings with **512-dim word unigram+bigram hashing** (MD5-deterministic). Same bug described differently now scores 0.4–0.6 vs the previous 0.05.
- Fixed `rkt_engine.py` db_lookup query contamination: was injecting project-type `common_failure` string into every query regardless of hint, causing STRIPE patterns to surface for AUTH bugs on SaaS projects.
- Cleaned `brain.db`: deleted 11 garbage `Manual fix:` entries and fixed 2 crossed `error_signature` values (AUTH patterns with STRIPE/SUPABASE signatures).

**Tier 2 — New Detection Rules (done)**
- **Rule 9** — `headers()` not awaited in Next.js 15 (same pattern as Rule 6 `cookies()`)
- **Rule 11** — `'use client'` file imports server-only supabase/ssr export (hard build failure)
- **Rule 12** — Server Action mutates data without `revalidatePath()` (stale cache symptom)
- **ENV chain** — now checks `.env.production` alongside `.env.local` for `SUPABASE_SERVICE_ROLE_KEY` and `STRIPE_WEBHOOK_SECRET`
- **schema_checker** — new `rls:insert_policy` check catches RLS enabled with no INSERT policy

**Tier 3 — Semantic Search (done)**
- New `brain_fts.py`: tantivy BM25 full-text index over all fixes. Field boosts: `error_msg` exact match, `symptom`, `fix_summary`. Handles technical tokens like `PGRST301`, `42501`, `constructEvent` that vector search misses.
- New `SemanticIndex` class in `db.py`: usearch ANN with 64-dim TF-IDF LSA vectors fitted on the brain.db corpus. "dashboard blank after login" → AUTH match at 0.68 score.
- New `hybrid_lookup()` in `db.py`: runs both searches in parallel, merges with **Reciprocal Rank Fusion (RRF)** — `1/(k + rank)` weighted sum. Falls back to word n-gram cosine when either index is cold.

**Tier 4 — Surgical Context (done)**
- New `engine/slicer.py`: tree-sitter AST extraction of auth/stripe-touching functions only (8–40 lines). Reduces per-ticket token cost from ~3,000–8,000 tokens to ~400–700. Falls back to full-file read when tree-sitter unavailable.
- New `engine/fix_validator.py`: applies fix diffs to temp files, runs `oxlint`, returns structured errors. Wired as `validate_fix` node in `triage_graph.py` between `symptom_rank` and `build_summary`. Non-blocking when oxlint not installed.

**Tier 5 — Pattern Bootstrap (done)**
- New `engine/git_extractor.py`: scans `~/Documents/Rocket` repos for support-related commits, checks out the broken state (parent commit), runs chain_walker for symptom extraction, saves to brain.db.
- New `engine/learn_fix.py`: interactive prompt at end of `rkt-done` — engineer confirms category, pattern, error signature, optional diff — saves with `verified=1` for highest-priority retrieval.
- `bin/rkt-done` updated to call `learn_fix.py` automatically after each successful push+clean.

---

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/vedang-rocket/Rocket-Support/main/install.sh | bash
```

Installs in under 2 minutes. Idempotent — safe to run multiple times.

**Requirements:** macOS · Python 3.9+ · Node.js 18+ · bun · Claude Code (`npm install -g @anthropic-ai/claude-code`)

---

## Three Commands

### `rkt-crazy` — Full pipeline (triage + Cursor setup + fix)

```bash
rkt-crazy ~/Downloads/client.zip "auth broken after login"
rkt-crazy ~/Downloads/client.zip "dashboard blank" --fast   # skip Cursor setup
```

Runs all three phases end to end. Use this for new client projects.

---

### `rkt-triage` — Fast pipeline (triage + fix, no Cursor setup)

```bash
rkt-triage ~/Downloads/client.zip "stripe webhook 400"
```

Same triage + fix menu as `rkt-crazy`, but skips Phase 2 (Cursor rule installation). Use this when the project is already set up or you just want a fast diagnosis.

---

### `rkt-deliver` — Package and deliver

```bash
rkt-deliver
rkt-deliver /path/to/workspace
```

Learns from your changes, strips all tooling artifacts, and zips the fixed project for delivery. If run inside a workspace, it uses the current directory automatically.

---

## How It Works

```
rkt-crazy ~/Downloads/client.zip "issue"

  PHASE 1 — TRIAGE                          (~3 seconds)
  ├─ Unzip → flatten → snapshot → workspace
  ├─ bun install
  └─ 7-layer engine:
       chain_walker  → schema_checker → fingerprint
     → probe_scanner → fix_database   → kb_search → slicer
     Outputs: root cause, confidence %, recommended fix mode

  PHASE 2 — CURSOR SETUP                    (~45 seconds, skip with --fast)
  └─ rkt-main --no-diagnose on workspace:
     61 Cursor rules · Graphify · UI/UX Pro Max · skills
     MCPs · CLAUDE.md · code-review-graph · Obsidian · RuFlo

  PHASE 3 — FIX MODE MENU                   (your choice)
  └─ Pre-selected from triage recommendation
     [1] AUTO · [2] GUIDED · [3] CLAUDE · [4] MANUAL
```

---

## Fix Modes

| Mode | What it does |
|------|-------------|
| **AUTO** | Applies all high-confidence fixes with `--yes --non-interactive`. No prompts. Run `rkt-deliver` when done. |
| **GUIDED** | Writes `.rkt_prompt.md` to the workspace (triage findings as a ready-to-paste Cursor prompt), then opens Cursor. Open the file, paste into Cursor chat, press Enter. |
| **CLAUDE** | Launches `claude --dangerously-skip-permissions` in the workspace. Full agentic fix. Run `rkt-deliver` when Claude exits. |
| **MANUAL** | Interactive per-file review via `rkt_smart.py`. Shows each diff, you approve or skip. |

### GUIDED mode — step by step

When you select GUIDED, Cursor opens automatically with `.rkt_prompt.md` in the workspace root:

```
In Cursor:
  1. Open file: .rkt_prompt.md
  2. Select all text (Cmd+A)
  3. Paste into Cursor chat
  4. Press Enter
```

The prompt contains: issue description, category, confidence, all findings with source and fix mode, and the 10 Rocket.new hard rules.

---

## The Engine (7 Layers)

Runs automatically during triage on every client project:

```
Layer 0:  chain_walker     → Cross-file structural breaks (AUTH, STRIPE, RLS, ENV)
Layer 0b: schema_checker   → SQL migration audit (TIMESTAMPTZ, triggers, RLS policies, CASCADE)
Layer 1:  fingerprint      → Project type (SaaS, E-Commerce, AI, Booking, Landing, Blog)
Layer 2:  probe_scanner    → AST + regex scan — 12 rules, <1 second
Layer 3:  fix_database     → Hybrid semantic search in brain.db (~15ms)
Layer 4:  KB search        → Supabase, Next.js, Stripe docs injected as context
Layer 5:  slicer           → Surgical function extraction for Claude context (400–700 tokens)
```

Every finding is scored **HIGH / MED / LOW** confidence before a fix is proposed.

---

## Engine: chain_walker

Walks 4 cross-file dependency chains. Returns the first break per chain in under 1 second. All 4 chains always run — no early exit.

| Chain | Files checked | What it finds |
|-------|--------------|---------------|
| **AUTH** | `middleware.ts`, `lib/supabase/server.ts`, `app/auth/callback/route.ts` | Missing `updateSession`, wrong client factory, missing `exchangeCodeForSession` |
| **STRIPE** | `app/api/webhooks/stripe/route.ts`, webhook handler, checkout route | `request.json()` instead of `request.text()`, missing `constructEvent`, missing `user_id` in metadata |
| **RLS** | `supabase/migrations/*.sql` | Missing `on_auth_user_created` trigger, missing `enable row level security` |
| **ENV** | `.env.local`, `.env.production` | Missing `SUPABASE_SERVICE_ROLE_KEY`, missing `STRIPE_WEBHOOK_SECRET` in both dev and deploy env files |

---

## Engine: schema_checker

Audits `supabase/migrations/*.sql` for 5 required patterns:

| Check ID | What it looks for | Failure means |
|----------|------------------|--------------|
| `trigger:on_auth_user_created` | `on_auth_user_created` trigger | Profile rows never created on signup |
| `rls:enable_row_level_security` | `enable row level security` | Tables fully open to public |
| `rls:insert_policy` | `for insert` policy | Users can read but cannot write — 403 on form submit |
| `foreign_key:on_delete_cascade` | `on delete cascade` | Orphaned rows when users deleted |
| `timestamptz` | No bare `TIMESTAMP` without timezone | Silent timezone corruption in queries |

---

## Engine: probe_scanner

Layer 2 uses `ast-grep-py` (AST-accurate pattern matching, no false positives from comments or strings) and `rg` (ripgrep, path-filtered). Runs in under 1 second.

### Full rule list (12 active rules)

| Rule | ID | Detects | Tool |
|------|----|---------|------|
| 1 | `supabase-getsession-not-getuser` | `.auth.getSession()` in server code | ast-grep |
| 2 | `supabase-auth-helpers-deprecated` | `@supabase/auth-helpers-nextjs` import | rg |
| 4 | `stripe-webhook-request-json` | `request.json()` in Stripe webhook handler | rg + glob |
| 5 | `supabase-wrong-import` | `@supabase/supabase-js` in server file | rg + glob |
| 6 | `cookies-without-await` | `cookies()` without `await` in Next.js 15 | ast-grep |
| 7 | `next-public-service-role-key` | `NEXT_PUBLIC_` on secret env vars | rg + .env glob |
| 8 | `supabase-missing-dynamic-export` | Authenticated page missing `force-dynamic` | rg + glob |
| *(new)* 9 | `headers-without-await` | `headers()` without `await` in Next.js 15 | ast-grep |
| — | `anon-key-format` | Old `eyJ` JWT format on post-Nov 2025 projects | rg |
| *(new)* 11 | `use-client-server-import` | `'use client'` file imports `createServerClient` | rg + head-read |
| *(new)* 12 | `server-action-missing-revalidate` | Server Action mutates DB without `revalidatePath()` | file-read |

Rule 3 (middleware location) is handled by `chain_walker`. Rule 10 is handled by `schema_checker`.

### Confidence → action

| Confidence | Meaning | Behaviour in AUTO mode |
|-----------|---------|----------------------|
| HIGH | Single string replacement, import swap | Applied automatically |
| MED | Adding export, function change | Applied with warning |
| LOW | Middleware restructure, template replacement | Diff shown only — **never auto-applied** |

---

## brain.db — The Learning Database

Location: `~/.rocket-support/brain.db`

Every support session saves patterns. The database improves with every ticket. Currently **29 verified patterns** across AUTH, STRIPE, SUPABASE, BUILD, ENV, and RLS categories.

### How retrieval works (3-tier hybrid search)

```
Query: "dashboard blank after login getSession"

  Tier 1 — Semantic (usearch + TF-IDF LSA)
  ├─ 64-dim LSA vectors fitted on brain.db corpus
  ├─ usearch ANN cosine search — returns ranked IDs
  └─ "dashboard blank after login" → AUTH 0.68

  Tier 2 — Full-text (tantivy BM25)
  ├─ en_stem tokenizer, symptom + error_msg + fix_summary fields
  ├─ Exact technical token matching (PGRST301, constructEvent, etc.)
  └─ Returns ranked IDs independently

  Tier 3 — RRF Merge
  ├─ Reciprocal Rank Fusion: score = sum(1 / (60 + rank))
  ├─ Merged top-3 IDs fetched from brain.db
  └─ Falls back to word n-gram cosine if both indexes cold
```

### Embedding details

- **Method**: word unigram + bigram hashing, MD5-deterministic, 512 dimensions
- **Why MD5**: Python's `hash()` is PYTHONHASHSEED-randomized per process; `hashlib.md5` gives identical vectors across runs
- **Previous**: 128-dim character 3/4-gram hashing — caused ~0.05 cosine for same bug described differently
- **Now**: same-vocabulary bugs score 0.3–0.7; semantic synonyms handled by Tier 1 LSA

### Database stats

```bash
# Check what's been learned
python3 ~/rocket-support/engine/rkt_smart.py --db-stats

# Direct query
sqlite3 ~/.rocket-support/brain.db \
  "SELECT category, uses, verified, SUBSTR(pattern,1,60) FROM fixes ORDER BY uses DESC;"

# Rebuild semantic + FTS indexes after manual DB edits
python3 ~/rocket-support/engine/migrate_embeddings.py
python3 -c "
import sys; sys.path.insert(0,'engine')
from brain_fts import get_brain_fts
get_brain_fts().rebuild_from_db()
import db; db.SemanticIndex().rebuild_from_db()
"
```

### Auto-learn pipeline

After each `rkt-done`, you're prompted to save the fix to brain.db:

```
── Auto-Learn ─────────────────────────────────────
Save fix to brain.db for future tickets? [y/N]: y
Pattern: getSession used in server action
Error signature: Dashboard blank after signup
Category: 1 (AUTH)
Fix diff: (paste unified diff, end with ---)
✓ Pattern saved: a3f8c2d1... [AUTH]
```

Manually run pattern extraction from past git history:

```bash
engine/.venv/bin/python engine/git_extractor.py --repos-dir ~/Documents/Rocket
engine/.venv/bin/python engine/git_extractor.py --dry-run   # preview without saving
```

---

## engine/slicer.py — Surgical Token Extraction

Before Claude reads files, `slicer.py` extracts only functions that touch auth/stripe keywords:

```python
from slicer import slice_repo, format_slices_for_prompt

slices = slice_repo("/path/to/project", keywords=["getUser", "createServerClient"])
context = format_slices_for_prompt(slices, repo_path="/path/to/project")
# Each slice: {file, function_name, start_line, end_line, source, keywords_found}
```

**Token reduction:**

| Approach | Tokens per file | Files read |
|----------|----------------|-----------|
| Whole-file reads (old) | 3,000–8,000 | 3–5 |
| Surgical slices (new) | 80–200 per function | only those touching keywords |
| **Total** | **~50,000 old** | **~400–700 new** |

Keywords tracked: all auth (`getUser`, `getSession`, `createServerClient`, `updateSession`, `supabase.auth`) + all stripe (`constructEvent`, `stripe.webhooks`, `request.text`, `STRIPE_SECRET_KEY`) + RLS patterns.

Falls back to a 40-line head of the file if tree-sitter fails.

---

## engine/fix_validator.py — oxc Validation Gate

After `fix_writer` generates a diff, `fix_validator` applies it to a temp file and runs `oxlint`:

```python
from fix_validator import validate_fix_plan, validation_errors_to_context

errors = validate_fix_plan(fix_plan, repo_path)
# errors = [{"file": "...", "errors": ["error: ..."]}, ...]

if errors:
    context = validation_errors_to_context(errors)
    # Feed context back to fix_writer for retry
```

Wired as `validate_fix` node in `triage_graph.py` (between `symptom_rank` and `build_summary`). Completely non-blocking when `oxlint` is not installed.

Install oxlint once:
```bash
npm install -g oxlint
```

---

## triage_graph.py — Pipeline Nodes

The diagnosis pipeline is a LangGraph `StateGraph` with 12 nodes:

```
fingerprint → chain_walker → schema → semgrep(probe_scanner)
           → fs_checks → context_filter → deduplicate
           → db_lookup → score_and_route → symptom_rank
           → validate_fix → build_summary → END
```

### Routing logic

| Condition | Fix mode |
|-----------|---------|
| avg confidence ≥ 0.85 AND auto_count > 0 | AUTO |
| avg confidence ≥ 0.60 | GUIDED |
| avg confidence ≥ 0.40 | CLAUDE |
| below 0.40 | MANUAL |

### Scoring weights per source

| Source | AUTO threshold | Confidence |
|--------|---------------|-----------|
| STRIPE `request.text()` | 0.99 | Certain |
| AUTH server.ts `getUser()` | 0.97 | Certain |
| AUTH middleware | 0.85 | High |
| probe_scanner (ast-grep) | 0.80–0.97 | High |
| probe_scanner (rg) | 0.70–0.85 | Med-High |
| schema_checker | 0.75 | Med |
| db_match | 0.75 | Med |

---

## Support Container Workflow

Use these when handling live support threads on the remote container (`support-vedang-patel`):

```bash
rkt-ok <threadId>      # init thread, install rules, open remote Cursor + Ghostty panes
rkt-rules-add          # inject cursor-rules-v34 into active remote project
rkt-rules-remove       # remove injected rules + cleanup .gitignore block
rkt-done               # remove rules, push, clean, auto-learn prompt, close serve pane
```

### `rkt-ok` — Session startup sequence

1. `rocket clean` — wipe any existing project on container
2. `rocket init <threadId>` — pull client project, verify `"code":"OK"`
3. Detect project folder in `/home/ubuntu/app`
4. Install cursor rules (`rkt-rules-add`)
5. Open Cursor remotely (`cursor --remote ssh-remote+support-vedang-patel <path>`)
6. Write launcher scripts to `/tmp/`
7. Open Ghostty split panes via AppleScript:
   - **Left pane**: `npm install && npm run build && npm run serve`
   - **Right pane**: interactive bash shell for rocket commands

### `rkt-done` — Session teardown sequence

1. Detect active project
2. Confirm push/clean
3. `rkt-rules-remove --yes` — strip injected Cursor rules
4. `rocket push` — push changes to Rocket.new
5. `rocket clean` — wipe container
6. **Auto-learn prompt** — save fix pattern to brain.db (`verified=1`)
7. Close serve pane via AppleScript

---

## Commands Reference

### Primary workflow

```bash
rkt-crazy <project.zip> ["issue"]           # full pipeline
rkt-crazy <project.zip> ["issue"] --fast    # skip Cursor setup
rkt-triage <project.zip> ["issue"]          # triage + fix only
rkt-deliver                                 # package and deliver
```

### Project setup only

```bash
rkt-main <project-name>                     # clone from GitHub + full 11-step setup
rkt-main --local /path/to/project           # local folder + full setup
rkt-main /path/to/project                   # shorthand for --local
rkt-main <project-name> --no-diagnose       # setup only, skip fix scan
rkt-main <project-name> --force             # redo all 11 steps
rkt-main <project-name> --yes               # auto-apply all fixes
rkt-main <project-name> --preview-only      # show diffs, write nothing
```

### Diagnosis only

```bash
python3 ~/rocket-support/engine/rkt_smart.py <path>                    # interactive
python3 ~/rocket-support/engine/rkt_smart.py <path> --yes              # auto-apply
python3 ~/rocket-support/engine/rkt_smart.py <path> --preview-only     # diff only
python3 ~/rocket-support/engine/rkt_smart.py <path> --fingerprint-only # type detection
python3 ~/rocket-support/engine/rkt_smart.py --db-stats                # brain.db stats
python3 ~/rocket-support/engine/rkt_smart.py --seed-db                 # seed built-in patterns
```

### Database maintenance

```bash
# Check learned patterns
sqlite3 ~/.rocket-support/brain.db \
  "SELECT category, uses, verified, SUBSTR(pattern,1,70) FROM fixes ORDER BY uses DESC;"

# Backup before changes
cp ~/.rocket-support/brain.db ~/.rocket-support/brain.db.backup

# Rebuild all embeddings after manual DB edits
engine/.venv/bin/python engine/migrate_embeddings.py

# Extract patterns from git history
engine/.venv/bin/python engine/git_extractor.py --repos-dir ~/Documents/Rocket

# Run cleanup (idempotent — safe to re-run)
engine/.venv/bin/python engine/cleanup_db.py
```

### Engine file reference

| File | Purpose |
|------|---------|
| `engine/db.py` | brain.db access, 512-dim embeddings, SemanticIndex, hybrid_lookup, RRF |
| `engine/brain_fts.py` | tantivy BM25 full-text index (`~/.rocket-support/brain_fts/`) |
| `engine/rkt_engine.py` | Main diagnosis orchestrator, db_lookup, build_claude_prompt |
| `engine/chain_walker.py` | AUTH/STRIPE/RLS/ENV cross-file chain checking |
| `engine/probe_scanner.py` | 12-rule AST + rg scanner |
| `engine/schema_checker.py` | SQL migration audit (5 checks) |
| `engine/fingerprint.py` | Project type detection (7 types, 3 signal dimensions) |
| `engine/triage_graph.py` | LangGraph 12-node pipeline |
| `engine/slicer.py` | tree-sitter surgical function extraction |
| `engine/fix_validator.py` | oxc lint gate for generated fixes |
| `engine/fix_writer.py` | Fix plan generation and atomic application |
| `engine/git_extractor.py` | Git history pattern bootstrap |
| `engine/learn_fix.py` | Interactive auto-learn prompt for rkt-done |
| `engine/migrate_embeddings.py` | One-time embedding regeneration utility |
| `engine/cleanup_db.py` | Idempotent DB cleanup (noise entries, crossed signatures) |
| `engine/kb/` | BM25-indexed local copies of Supabase/Next.js/Stripe docs |

---

## Workspace management

```bash
# List all workspaces
python3 -c "
import sys; sys.path.insert(0,'~/rocket-support/engine')
import workspace as w
for m in w.list_workspaces(): print(m['workspace_name'], m['workspace_path'])
"
```

---

## Maintenance

```bash
# Refresh KB docs
~/rocket-support/engine/kb/refresh.sh

# Run test suite
engine/.venv/bin/python -m pytest tests/ -v   # 20 tests

# Full backup
cd ~ && zip -r ~/Downloads/rkt-backup-$(date +%Y%m%d).zip \
  rocket-support/ .rocket-support/brain.db \
  .claude/settings.json .claude/mcp.json \
  --exclude "rocket-support/engine/.venv/*"

# Update
cd ~/rocket-support && git pull
```

---

## The 10 Hard Rules

Violations caught automatically by the engine. Never violate these in a fix:

1. `getUser()` not `getSession()` in server code — getSession() doesn't validate JWT
2. `request.text()` not `request.json()` in Stripe webhook handlers
3. `middleware.ts` at project root — never inside `/app`
4. `@supabase/ssr` only — never `@supabase/auth-helpers-nextjs` (deprecated)
5. `await cookies()` and `await headers()` required in Next.js 15
6. Never `NEXT_PUBLIC_` prefix on service role or secret keys
7. Never produce `// ... existing code ...` in diffs — Lazy Delete bug
8. Always `export const dynamic = 'force-dynamic'` on authenticated pages
9. Social OAuth never works on localhost — test on deployed URL only
10. Post-Nov 2025 Supabase projects use `sb_publishable_` key format, not `anon_key`

---

## rkt-deliver Cleanup

Before zipping, `rkt-deliver` strips all tooling artifacts from the workspace:

**Directories removed:**
`.rkt_snapshot` · `node_modules` · `.next` · `.claude` · `.cursor` · `.swarm` · `.claude-flow` · `memory-bank` · `graphify-out` · `code-review-graph` · `.code-review-graph`

**Files removed:**
`CLAUDE.md` · `AGENTS.md` · `.mcp.json` · `the-rocket-guide.md` · `TROUBLESHOOTING.md` · `.rkt_meta.json` · `.rkt_prompt.md` · `.rkt_handoff_prompt.md` · `bun.lock` · `ruvector.db` · `ruvector.db-shm` · `ruvector.db-wal` · `*.rkt_backup`

The output zip lands at `~/Documents/Rocket/<project>/fixed/<project>_fixed.zip`.

---

## Performance

| Layer | Before | After |
|-------|--------|-------|
| probe_scanner (was semgrep) | 10–30s | <1s |
| db_lookup embedding (was char n-gram) | ~12ms | ~15ms (word n-gram + hybrid) |
| db_lookup accuracy | 35–45% | 55–60% (Tier 1) → 85–90% (all tiers) |
| Claude prompt tokens per ticket | ~50,000 | ~700 (with slicer) |
| brain.db patterns | 40 (11 noise) | 29 clean + growing via auto-learn |
| **Phase 1 total** | **~32s** | **~3s** |

### Accuracy by tier

| After | Accuracy | What it adds |
|-------|----------|-------------|
| Baseline | 35–45% | — |
| Tier 1 (embeddings + cleanup + query fix) | 55–60% | Correct retrieval on existing 29 clean patterns |
| Tier 2 (5 new rules) | 62–68% | headers(), use-client-server-import, revalidatePath, .env.production, RLS INSERT |
| Tier 3 (semantic + BM25 + RRF) | 72–78% | Same bug described differently now matches; exact error codes hit |
| Tier 4 (slicer + oxc gate) | 78–83% | Token cost down 85%; bad-deploy class eliminated by lint validation |
| Tier 5 (git history + auto-learn) | 85–90% | 80–120+ new patterns from real client history |
