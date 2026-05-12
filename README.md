# Rocket Support Engine

AI-powered diagnostic and fix system for Next.js/Supabase projects.

## CLI Commands

### rkt — Main entry point
`bin/rkt` - Main diagnostic runner. Orchestrates full analysis: chain_walker → schema_checker → fingerprint → semgrep → brain.db → KB.

### rkt-diagnose
`bin/rkt-diagnose` - Fast chain validation (<1s). Checks four dependency chains: AUTH, STRIPE, RLS, ENV.

### rkt-quick
`bin/rkt-quick` - Lightweight triage. Runs probe_scanner.py for fast error detection.

### rkt-lint
`bin/rkt-lint` - Code quality checks. Runs format_output.py and syntax validation.

### rkt-ok / rkt-done
`bin/rkt-ok` - Mark diagnosis complete.
`bin/rkt-done` - Mark fix verified.

### rkt-rules-add
`bin/rkt-rules-add` - Add new fix pattern to brain.db.

## Core Engine Modules

### engine/chain_walker.py (346 lines)
Layer 0 fast chain checker. Walks four dependency chains in <1 second:

| Chain | Precondition | Checks |
|-------|--------------|--------|
| AUTH | @supabase in package.json | middleware.ts has updateSession, server.ts uses @supabase/ssr, callback has exchangeCodeForSession |
| STRIPE | stripe in package.json | webhook uses request.text(), not request.json() |
| RLS | supabase/migrations/ exists | RLS enabled, SELECT policies for auth.uid() |
| ENV | @supabase OR stripe in package.json | All required env vars present |

### engine/probe_scanner.py
Fast error detector with 9 scan functions:

- scan_getsession() — Detects getSession() vs getUser() misuse
- scan_stripe_webhook() — Detects request.json() in webhooks
- scan_cookies_without_await() — Detects missing await on cookies()
- scan_missing_dynamic_export() — Detects missing dynamic = 'force-dynamic'
- scan_env_secrets() — Detects NEXT_PUBLIC_ on secret keys
- scan_supabase_wrong_import() — Detects @supabase/auth-helpers-nextjs usage
- scan_anon_key_format() — Detects old anon_key vs new sb_publishable_ format
- scan_headers_without_await() — Detects missing await on headers()
- scan_use_client_server_import() — Detects 'use client' in server files

### engine/triage_graph.py
Project fingerprinting. Identifies project type (SaaS, E-Commerce, AI, Booking, Landing, Blog) from package.json dependencies.

### engine/schema_checker.py
Database schema validation. Checks RLS policies, triggers, and migrations.

### engine/fingerprint.py
Pattern matching against brain.db fix patterns.

### engine/db.py
brain.db interface. SQLite database of 31 fix patterns across 7 categories:

| Category | Fixes |
|----------|-------|
| AUTH | 10 |
| SUPABASE | 7 |
| BUILD | 5 |
| STRIPE | 4 |
| UI | 3 |
| ENV | 1 |
| RLS | 1 |

### engine/fix_writer.py
Applies verified fixes to codebase.

### engine/rkt_engine.py
Main orchestration. Runs: chain_walker → probe_scanner → fingerprint → semgrep → brain.db lookup → KB search.

### engine/learn_fix.py
Learning system. Stores new fixes to brain.db with pattern matching.

### engine/format_output.py
Output formatting. Produces structured diagnostic reports.

## Knowledge Base

### engine/kb/
Live documentation:

- kb/supabase_ssr (22K) — @supabase/ssr usage patterns
- kb/supabase_rls (25K) — RLS policy reference
- kb/nextjs_middleware (30K) — Middleware patterns
- kb/nextjs_cookies (12K) — Next.js 15 cookies() await rules
- kb/nextjs_15_upgrade (17K) — Upgrading to Next.js 15

### kb_search.py
BM25 full-text search. Query with: `python3 -c "import sys; sys.path.insert(0,'engine/kb'); import kb_search; print(kb_search.search('your query'))"`

## Tests

### tests/engine/
6 test files:

- test_brain_fts.py — Brain database FTS tests
- test_db.py — Database interface tests
- test_schema_checker.py — Schema validation tests
- test_chain_walker.py — Chain walking tests
- test_probe_scanner.py — Probe scanner tests
- test_probe_scanner.py — Probe scanner tests

## Claude Code Hooks

### ~/.claude/hooks/
6 shell hooks for session automation:

| Hook | Event | Purpose |
|------|-------|---------|
| ruflo-daemon.sh | SessionStart | Start RuFlo V3 MCP daemon |
| brain-inject.sh | SessionStart | Inject brain.db patterns |
| graphify.sh | PreToolUse: Grep/Glob/Read | Emit file-type scope |
| ux-detector.sh | UserPromptSubmit | UI/UX Pro Max mode |
| chain-walker-check.sh | PostToolUse: Write/Edit | Run chain_walker on .ts/.tsx |
| tsc-check.sh | Stop | Run `npx tsc --noEmit` |

## Top Failure Modes

| Project Type | #1 Failure | #2 Failure |
|--------------|-------------|------------|
| SaaS | Stripe webhook 400 (request.json) | middleware.ts in /app |
| E-Commerce | RLS blocking guest checkout | Missing profile trigger |
| AI | getSession() in server route | Missing dynamic export |
| Booking | Redirect URL missing in Supabase | OAuth fails on localhost |
| Landing | NEXT_PUBLIC_ on service role key | RLS blocking leads INSERT |
| Blog | Missing dynamic export on auth pages | cookies() not awaited |

## The 10 Hard Rules

1. getUser() not getSession() in server code — getSession() skips JWT validation
2. request.text() not request.json() in Stripe webhooks
3. middleware.ts at PROJECT ROOT — never inside /app
4. @supabase/ssr only — never @supabase/auth-helpers-nextjs (deprecated)
5. await cookies() — required in Next.js 15, not optional
6. Never NEXT_PUBLIC_ prefix on service role / secret keys
7. Never // ... existing code ... in diffs — destroys file content
8. Always export const dynamic = 'force-dynamic' on authenticated pages
9. Social OAuth never works on localhost — test on deployed URL only
10. Post-Nov 2025 Supabase projects use sb_publishable_ key format (not anon_key)

## Development

### Installation
```bash
# Install dependencies
cd engine && pip install -r requirements.txt

# Enable Claude Code hooks
cp ~/.claude/hooks/*.sh ~/.claude/hooks/ 2>/dev/null || true

# Initialize brain.db (first run only)
python3 -c "from engine.db import init_db; init_db()"
```

### Running diagnostics
```bash
# Full diagnosis
./bin/rkt /path/to/project

# Fast chain check only
./bin/rkt-diagnose /path/to/project

# Quick triage
./bin/rkt-quick /path/to/project

# Check specific chain
./bin/rkt-diagnose /path/to/project AUTH
```

### Adding fix patterns
```bash
./bin/rkt-rules-add --pattern "getSession" --category AUTH --fix "Replace getSession() with getUser()"
```

### Querying brain.db
```bash
# List all fix patterns
sqlite3 ~/.rocket-support/brain.db "SELECT pattern, category, uses FROM fixes ORDER BY uses DESC;"

# Search by category
sqlite3 ~/.rocket-support/brain.db "SELECT * FROM fixes WHERE category='AUTH';"
```

## Statistics

- Engine modules: 11,857 lines of Python
- Fix patterns in brain.db: 31
- Test files: 6
- KB documents: 5 (total ~106K)
- Claude Code hooks: 6
- Probe scanner functions: 9
- Dependency chains: 4 (AUTH, STRIPE, RLS, ENV)

## What Works

- Fast chain validation (<1s) via chain_walker.py
- 9 probe scanner functions for common Next.js/Supabase errors
- 31 verified fix patterns in brain.db
- Project fingerprinting via triage_graph.py
- KB-based documentation search
- Claude Code hooks for automated checks

## What Does Not Work

- Tests cannot run — pytest not installed in environment
- OAuth testing requires deployed URL (cannot test on localhost)
- Some KB documents may be outdated for newest Supabase versions
- No automatic update mechanism for brain.db patterns

## Quick Reference

```bash
# Run full diagnostic
./bin/rkt /path/to/project

# Check specific hint
./bin/rkt /path/to/project "auth broken"

# Query knowledge base
python3 -c "import sys; sys.path.insert(0,'engine/kb'); import kb_search; print(kb_search.search('middleware'))"

# View brain.db stats
sqlite3 ~/.rocket-support/brain.db "SELECT category, COUNT(*) FROM fixes GROUP BY category;"
```