# Rocket-Support — rkt

Three commands. Unzip → triage → fix → deliver. Under 60 seconds.

Built for Rocket.new support engineers. Unzip a client project, get a root cause diagnosis, apply fixes automatically or via Cursor/Claude, then deliver a clean zip back to the client.

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
```

Learns from your changes, strips all tooling artifacts, and zips the fixed project to `~/Downloads/` for delivery.

---

## How It Works

```
rkt-crazy ~/Downloads/client.zip "issue"

  PHASE 1 — TRIAGE                          (~13 seconds)
  ├─ Unzip → flatten → snapshot → workspace
  ├─ bun install
  └─ 6-layer engine: chain_walker → schema → fingerprint
                     → semgrep → fix_database → kb_search
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

The prompt contains: issue description, category, confidence, all findings with source and fix mode, and the 7 Rocket.new hard rules.

---

## The Engine (6 Layers)

Runs automatically during triage on every client project:

```
Layer 0:  chain_walker     → Cross-file structural breaks (AUTH, STRIPE, RLS, ENV)
Layer 0b: schema_checker   → SQL migration audit (TIMESTAMPTZ, triggers, RLS, CASCADE)
Layer 1:  fingerprint      → Project type (SaaS, E-Commerce, AI, Booking, Landing, Blog)
Layer 2:  Semgrep          → AST-level autofix scan (7 Rocket.new-specific rules)
Layer 3:  Fix database     → Vector similarity search in brain.db
Layer 4:  KB search        → Supabase, Next.js, Stripe docs injected as context
```

Every finding is scored **HIGH / MED / LOW** confidence before a fix is proposed.

### Confidence → action

| Confidence | Meaning | Behaviour in AUTO mode |
|-----------|---------|----------------------|
| HIGH | Single string replacement, import swap | Applied automatically |
| MED | Adding export, function change | Applied with warning |
| LOW | Middleware restructure, template replacement | Diff shown only — **never auto-applied** |

> Middleware (`middleware-missing-updatesession`) is always `PREVIEW_ONLY`. The canonical template destroys custom route logic, so it is never written automatically.

### Semgrep rules (7)

| Rule | Catches |
|------|---------|
| `supabase-getsession-not-getuser` | `.auth.getSession()` in server code |
| `stripe-webhook-request-json` | `request.json()` in Stripe webhook handler |
| `stripe-webhook-req-json-var` | Variable-form `req.json()` in webhook |
| `supabase-js-in-server-file` | `@supabase/supabase-js` import in server file |
| `supabase-missing-dynamic-export` | Missing `force-dynamic` on authenticated page |
| `middleware-missing-updatesession` | `middleware.ts` without `updateSession` |
| `schema-timestamptz` | Bare `TIMESTAMP` column in SQL migration |

---

## brain.db — The Learning Database

Every fix run saves patterns to `~/.rocket-support/brain.db`. The database improves with every client project.

```bash
# Check what has been learned
python3 ~/rocket-support/engine/rkt_smart.py --db-stats
```

```
Fix database: ~/.rocket-support/brain.db
Total fixes:  12

Category     Uses   V   Pattern
AUTH         7      ✓   middleware.ts missing updateSession()
STRIPE       3      ✓   request.json() in webhook handler
SUPABASE     3      ✓   Missing RLS, missing profile trigger
ENV          1          NEXT_PUBLIC_ on service role key
```

`rkt-deliver` automatically saves any manual fixes made in GUIDED or CLAUDE mode back to brain.db.

---

## rkt-deliver Cleanup

Before zipping, `rkt-deliver` strips all tooling artifacts from the workspace:

**Directories removed:**
`.rkt_snapshot` · `node_modules` · `.next` · `.claude` · `.cursor` · `.swarm` · `.claude-flow` · `memory-bank` · `graphify-out` · `code-review-graph` · `.code-review-graph`

**Files removed:**
`CLAUDE.md` · `AGENTS.md` · `.mcp.json` · `the-rocket-guide.md` · `TROUBLESHOOTING.md` · `.rkt_meta.json` · `.rkt_prompt.md` · `ruvector.db` · `ruvector.db-shm` · `ruvector.db-wal` · `*.rkt_backup`

The output zip lands at `~/Downloads/<projectname>_fixed_<timestamp>.zip`.

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

### Workspace management

```bash
# List all workspaces
python3 -c "
import sys; sys.path.insert(0,'~/rocket-support/engine')
import workspace as w
for m in w.list_workspaces(): print(m['workspace_name'], m['workspace_path'])
"
```

### Maintenance

```bash
# Refresh KB docs
~/rocket-support/engine/kb/refresh.sh

# Backup everything
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
5. `await cookies()` required in Next.js 15 — not optional
6. Never `NEXT_PUBLIC_` prefix on service role or secret keys
7. Never produce `// ... existing code ...` in diffs — Lazy Delete bug
8. Always `export const dynamic = 'force-dynamic'` on authenticated pages
9. Social OAuth never works on localhost — test on deployed URL only
10. Post-Nov 2025 Supabase projects use `sb_publishable_` key format, not `anon_key`
