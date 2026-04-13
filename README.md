# Rocket-Support — rkt

One command. Clone → diagnose → fix. Under 60 seconds.

Built for Rocket.new support engineers. Diagnoses client repos automatically using a 6-layer engine — no manual code reading required.

---

## Install (one command)

```bash
curl -fsSL https://raw.githubusercontent.com/vedang-rocket/Rocket-Support/main/install.sh | bash
```

Installs everything in under 2 minutes. Idempotent — safe to run multiple times.

### What it installs

| Component | Location | Purpose |
|-----------|----------|---------|
| `rkt` | `~/rocket-support/bin/rkt` | Diagnose any client repo |
| `rkt-main` | `~/rocket-support/bin/rkt-main` | Full project setup (11 steps) |
| Python engine | `~/rocket-support/engine/` | 6-layer fix pipeline |
| brain.db | `~/.rocket-support/brain.db` | Learned fix pattern database |
| Global hooks | `~/.claude/hooks/` | Claude Code automation |
| Global skills | `~/.claude/skills/` | `/think` `/graph` `/memory` `/ux` `/review` |
| KB docs | `~/rocket-support/kb/` | Live Supabase + Next.js + Stripe docs |

### Requirements

- macOS (Apple Silicon or Intel)
- Python 3.9+
- Node.js 18+
- Claude Code (`npm install -g @anthropic-ai/claude-code`)
- SSH access to client GitHub repos

---

## Commands

### Diagnose a client repo

```bash
rkt cliently
```

Clones the repo, switches to the most recently updated branch, runs the full 6-layer engine, outputs findings with confidence scoring and code context.

### Full project setup

```bash
rkt-main cliently
```

Runs all 11 setup steps: clone → latest branch → v34 Cursor rules → Graphify → UI/UX Pro Max → global skills → MCP servers → CLAUDE.md → code-review-graph → Obsidian vault → RuFlo → .gitignore. Then runs full diagnosis.

### Use any GitHub URL

```bash
rkt git@github.com:VedangP57/Cliently.git
rkt-main git@github.com:VedangP57/Cliently.git
```

### Use a local folder (no GitHub needed)

```bash
rkt ~/Downloads/clientproject
rkt-main ~/Downloads/clientproject
rkt-main --local /path/to/project
```

### Modifiers

```bash
rkt-main cliently --force        # redo all 11 steps
rkt-main cliently --no-diagnose  # setup only, skip diagnosis
```

---

## What Gets Installed Per Project

Every `rkt-main` run installs these into the client project:

**For Claude Code:**
- 6 skills: `/think` `/graph` `/memory` `/ux` `/review` `/obsidian`
- 5 MCPs: context7, sequential-thinking, memory, playwright, code-review-graph
- RuFlo V3 daemon (15 agents, hierarchical-mesh swarm, vector memory)
- Global hooks: tsc-check, chain-walker guard, graphify, UX detector
- Project-specific CLAUDE.md with engine intelligence

**For Cursor:**
- 61 v34 Cursor rules
- 40 commands
- UI/UX Pro Max skills
- 4 MCPs in `.cursor/mcp.json`
- Graphify context graph

---

## The 6-Layer Engine

Runs automatically on every `rkt` or `rkt-main` call:

```
Layer 0:  chain_walker     → Cross-file structural breaks (AUTH, STRIPE, RLS, ENV)
Layer 0b: schema_checker   → SQL migration audit (triggers, RLS, CASCADE, TIMESTAMPTZ)
Layer 1:  fingerprint      → Project type (SaaS, E-Commerce, AI, Booking, Landing, Blog)
Layer 2:  Semgrep          → AST-level autofix scan (7 Rocket.new-specific rules)
Layer 3:  Fix database     → Vector similarity search (learns from every fix)
Layer 4:  KB search        → Live Supabase, Next.js, Stripe docs injected
```

Every finding is rated **[HIGH]** / **[MED]** / **[LOW]** confidence and shown with a 30-line code context window.

### Sample output

```
── Layer 0: chain_walker ──
  [AUTH] src/middleware.ts: updateSession missing

── Layer 0b: schema_checker ──
  [SCHEMA] Bare TIMESTAMP columns — replace with TIMESTAMPTZ

── Layer 2: Semgrep — 21 violation(s) ──
  [MED] supabase-js-in-server-file → src/app/api/admin/users/route.ts:2
  [MED] supabase-missing-dynamic-export → src/app/dashboard/page.tsx:162

── Layer 3: Fix database — 81% match ──
  Pattern: request.json() in Stripe webhook handler
  Autofix: const body = await request.text()

── KB search — 2 chunks ──
  [supabase_ssr]  Supabase SSR cookie refresh pattern
  [supabase_rls]  RLS policy with auth.uid()
```

---

## The 10 Hard Rules (v34)

Violations are caught automatically by the engine:

1. `getUser()` not `getSession()` in server code
2. `request.text()` not `request.json()` in Stripe webhooks
3. `middleware.ts` at project root — never inside `/app`
4. `@supabase/ssr` only — never `@supabase/auth-helpers-nextjs`
5. `await cookies()` required in Next.js 15
6. Never `NEXT_PUBLIC_` prefix on service role or secret keys
7. Never `// ... existing code ...` in diffs
8. Always `export const dynamic = 'force-dynamic'` on authenticated pages
9. Social OAuth never works on localhost
10. Post-Nov 2025 Supabase projects use `sb_publishable_` key format

---

## Confidence Scoring

Every fix is rated before being applied:

| Level | Meaning | Action |
|-------|---------|--------|
| `[HIGH]` | Single string replacement, import swap | Auto-applied |
| `[MED]` | Adding export, function change | Applied with warning |
| `[LOW]` | Middleware restructure, file move | Diff shown only — apply manually |

---

## brain.db — The Learning Database

Every fix gets saved to `~/.rocket-support/brain.db`. Similarity improves with every run.

```bash
# Check what's been learned
source ~/rocket-support/engine/.venv/bin/activate
python3 ~/rocket-support/engine/rkt_smart.py --db-stats
```

```
Category     Uses   Pattern
AUTH         7      middleware.ts missing updateSession()
STRIPE       3      request.json() in webhook handler
SUPABASE     3      Missing RLS, missing profile trigger
ENV          1      NEXT_PUBLIC_ on service role key
```

---

## Knowledge Base

Live documentation fetched from GitHub raw sources. Searched on every diagnosis run.

```bash
# Refresh weekly
~/rocket-support/engine/kb/refresh.sh
```

Sources: Supabase SSR guide, Supabase RLS docs, Next.js middleware, Next.js cookies(), Next.js 15 upgrade guide.

---

## SSH Setup for Client Repos

Add to `~/.ssh/config`:

```
Host github-rocket
  HostName github.com
  User git
  IdentityFile ~/.ssh/your_key
```

Test: `ssh -T git@github-rocket`

For any GitHub URL:
```bash
rkt git@github.com:OrgName/repo.git
```
Requires your SSH key to be authorized on that GitHub account.

---

## For Cursor Users

`rkt-main` installs to both Claude Code and Cursor automatically:

- `.cursor/rules/` — 61 v34 rules
- `.cursor/commands/` — 40 commands
- `.cursor/skills/` — UI/UX Pro Max
- `.cursor/mcp.json` — 4 MCP servers
- `.cursor/rules/graphify.mdc` — code graph context

Claude Code hooks and `rkt` diagnosis require Claude Code CLI.

---

## Updating

```bash
cd ~/rocket-support && git pull
# or re-run installer (idempotent):
bash ~/rocket-support/install.sh
```

---

## Maintenance

```bash
# Refresh KB docs
~/rocket-support/engine/kb/refresh.sh

# Check brain.db learnings
source ~/rocket-support/engine/.venv/bin/activate
python3 ~/rocket-support/engine/rkt_smart.py --db-stats

# Backup everything
cd ~ && zip -r ~/Downloads/rkt-backup-$(date +%Y%m%d).zip \
  rocket-support/ .rocket-support/brain.db \
  .claude/settings.json .claude/mcp.json \
  .claude/hooks/ .claude/skills/ \
  --exclude "rocket-support/engine/.venv/*"
```
