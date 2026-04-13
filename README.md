# rkt — Rocket.new Support Tool

Intelligent CLI for diagnosing and fixing Rocket.new client projects.
Runs a 4-layer engine: structural chain checks → fingerprint → Semgrep autofix → fix database + docs.

## Install (one command)

```bash
curl -fsSL https://raw.githubusercontent.com/vedang-rocket/rkt-support-tool/main/install.sh | bash
```

Or clone and run locally:

```bash
git clone git@github.com:vedang-rocket/rkt-support-tool.git ~/rocket-support
bash ~/rocket-support/install.sh
```

After install, reload your shell:

```bash
source ~/.zshrc
```

## Requirements

- macOS (Apple Silicon or Intel)
- Python 3.10+
- Node.js 18+ (for Claude Code)
- [Claude Code](https://claude.ai/code): `npm install -g @anthropic-ai/claude-code`
- SSH key configured for `github-rocket` host alias (for cloning client repos)

## What It Installs

| Component | Location | Purpose |
|-----------|----------|---------|
| `rkt` | `~/rocket-support/bin/rkt` | Diagnose a client repo with Claude |
| `rkt-main` | `~/rocket-support/bin/rkt-main` | Full project setup (11 steps) |
| Python engine | `~/rocket-support/engine/` | 4-layer fix pipeline |
| brain.db | `~/.rocket-support/brain.db` | Seeded fix pattern database |
| Global hooks | `~/.claude/hooks/` | Claude Code automation hooks |
| Global skills | `~/.claude/skills/` | Claude Code skill files |

## Commands

### Diagnose a client repo

```bash
rkt cliently
```

Clones the repo (if needed), runs the full engine, and opens Claude Code with a structured diagnosis prompt.

### Full project setup

```bash
rkt-main cliently
```

Runs all 11 setup steps: clone → Cursor rules → Graphify → Supabase client → UI/UX Pro Max → global skills → MCP servers → CLAUDE.md generation → Obsidian vault → RuFlo → .gitignore.

### Use a local folder (skip clone)

```bash
rkt-main --local ~/Downloads/myproject
# or shorthand:
rkt-main ~/Downloads/myproject
```

### Re-run on already-setup project

```bash
rkt-main cliently --force       # redo all 11 steps
rkt-main cliently --no-diagnose # setup only, skip Claude diagnosis
```

## Engine Layers

The fix engine runs automatically on every `rkt` or `rkt-main` call:

1. **chain_walker** — Structural break detection (AUTH, STRIPE, RLS, ENV chains)
2. **schema_checker** — SQL migration audit (triggers, RLS, CASCADE, TIMESTAMPTZ)
3. **fingerprint** — Project type classification (SaaS, E-Commerce, AI, Booking, Landing, Blog)
4. **Semgrep** — AST-level autofix scan using Rocket.new-specific rules
5. **Fix database** — Vector similarity search against 10+ seeded patterns
6. **KB search** — BM25 search over Supabase, Next.js, and Stripe docs

Every finding is rated **[HIGH]** / **[MED]** / **[LOW]** confidence and shown with a 30-line code context window.

## The 10 Hard Rules

Violations of these are caught automatically:

1. `getUser()` not `getSession()` in server code
2. `request.text()` not `request.json()` in Stripe webhooks
3. `middleware.ts` at project root — never inside `/app`
4. `@supabase/ssr` only — never `@supabase/auth-helpers-nextjs`
5. `await cookies()` — required in Next.js 15
6. Never `NEXT_PUBLIC_` prefix on service role / secret keys
7. Never `// ... existing code ...` in diffs
8. Always `export const dynamic = 'force-dynamic'` on authenticated pages
9. Social OAuth never works on localhost
10. New Supabase projects (post-Nov 2025): `sb_publishable_` key, not `anon_key`

## SSH Setup for Client Repos

Add to `~/.ssh/config`:

```
Host github-rocket
  HostName github.com
  User git
  IdentityFile ~/.ssh/your_key
```

Test with: `ssh -T git@github-rocket`

## Updating

```bash
cd ~/rocket-support && git pull
# or re-run the installer (idempotent):
bash ~/rocket-support/install.sh
```
