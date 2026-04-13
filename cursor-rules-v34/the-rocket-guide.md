# The Rocket Cursor Rules Guide — V19

Your complete reference for fixing and building in Rocket.new projects using Cursor IDE.

---

## What This System Is

This `.cursor/` folder is a complete operating system for working on Rocket.new projects.
It has 7 layers, each doing a different job:

| Layer | Files | Job |
|---|---|---|
| Rules | `.cursor/rules/*.mdc` | What Cursor must always know and never violate |
| Skills | `.cursor/skills/*/SKILL.md` | Step-by-step procedures for specific problem types |
| Commands | `.cursor/commands/*.md` | Heavy-weight injectable prompts for high-stakes operations |
| Hooks | `.cursor/hooks-scripts/*.sh` | Automatic safety guards that fire on every action |
| MCP | `.cursor/mcp.json` | Live connections to Supabase, Stripe, and Memory |
| Memory | `memory-bank/` | Persistent knowledge that survives session restarts |
| Instincts | `memory-bank/instincts/` | Learned patterns with confidence scores — grows over time |

---

## The Workflow — Every Session

### Opening a new project for the first time:
```
1. Copy .cursor/ + memory-bank/ + AGENTS.md to project root
2. chmod +x .cursor/hooks-scripts/*.sh
3. Update .cursor/mcp.json with project credentials
4. Reload Window → verify MCP green
5. /check-mcp
6. /audit-codebase       ← NEVER skip this
7. /make-legible         ← if many files lack headers
8. Read the audit report → pick the right fix command
```

### Fixing a specific issue:
```
/fix-auth         → any login, session, OAuth, middleware problem
/fix-database     → data not loading, RLS blocking, migrations missing
/fix-stripe       → webhook broken, payment fails, subscription issues
/fix-deployment   → Netlify build failure, works-local-not-prod
/fix-performance  → slow queries, N+1, missing indexes
/debug-error      → paste any error → chain-of-thought root cause
```

### Before accepting any change:
```
/review-diff      → 9-point security + correctness check
                    Checks: scope, auth patterns, Stripe safety, RLS,
                    secrets, breaking changes, TypeScript, Lazy Delete bug
```

### Implementing a new feature:
```
/spec-feature     → lock acceptance criteria FIRST (no code yet)
/plan-feature     → generate plan.md (no code yet)
/implement-feature → phase-by-phase implementation
```

### End of session:
```
/reflect          → extract all learnings → write to instincts
/learn-eval       → extract + quality-gate before saving
/update-memory    → save fixes to memory-bank/
/handoff-report   → report for the user (technical + plain English)
```

---

## The Self-Training Loop

This system gets smarter with every project you work on.

```
Session ends
    ↓
session-learning.sh fires automatically
    ↓
Writes observation to memory-bank/observations.jsonl
    ↓
You run /reflect or /learn-eval
    ↓
Patterns extracted → YAML instincts in memory-bank/instincts/
    ↓
Next session: Cursor reads instincts → already knows what went wrong before
    ↓
When confidence >= 0.9 + evidence >= 5:
/reflect --promote → pattern added to permanent rules
```

After 10 real projects, the instinct library has more accurate Rocket-specific knowledge
than any documentation. After 50 projects, it's essentially self-correcting.

---

## MCP — The Live Connection

MCP transforms Cursor from "reading static code" to "querying live systems."

| Without MCP | With MCP |
|---|---|
| Reads migration files to guess schema | Queries actual `information_schema` |
| Assumes RLS policies exist | Reads `pg_policies` directly |
| Guesses if profile trigger exists | Checks `pg_trigger` in seconds |
| Manual Stripe dashboard checks | Reads webhook endpoints directly |

**The golden rule**: when in doubt about database state, ask the database.
Never guess from code files when MCP can give you the real answer.

**Switching projects**: update `--project-ref` in mcp.json → Reload Window → 30 seconds.

---

## The 10 Rules That Matter Most

1. `getUser()` not `getSession()` — in all server-side code
2. `request.text()` not `request.json()` — in all Stripe webhook handlers
3. `lib/supabase/server.ts` in Server Components — `client.ts` in `'use client'` only
4. `middleware.ts` at project root — never inside `/app/`
5. `await cookies()` — Next.js 15 made it async, not optional
6. Never `NEXT_PUBLIC_` on service role key or Stripe secret key
7. Never `@supabase/auth-helpers-nextjs` — use `@supabase/ssr`
8. Social OAuth never works on localhost — test on deployed URL
9. Never accept a diff with `// ... existing code ...` — Lazy Delete bug
10. `/audit-codebase` first on every new project — never skip

Violating any of these causes silent failures that are hard to debug.
The rules layer in `.cursor/rules/` enforces all of them automatically.

---

## Commands Reference

| Command | When |
|---|---|
| `/audit-codebase` | First thing on every new project |
| `/check-mcp` | MCP not working |
| `/harness-audit` | Check health of the config system itself |
| `/security-audit` | Before production deploy |
| `/quality-gate` | Full quality check before shipping |
| `/fix-auth` | Any auth/session/OAuth issue |
| `/fix-database` | Data empty, RLS blocking, migrations |
| `/fix-stripe` | Webhook, payment, subscription issues |
| `/fix-deployment` | Netlify build failures |
| `/fix-performance` | Slow queries, N+1 problems |
| `/make-legible` | Add file headers to messy project |
| `/spec-feature` | Before building anything new |
| `/plan-feature` | Complex feature planning |
| `/implement-feature` | Phase-by-phase feature build |
| `/debug-error` | Paste any error for root cause |
| `/refactor-safe` | Safe refactoring with scope-lock |
| `/review-diff` | Before accepting ANY change |
| `/yolo-tdd` | Autonomous TDD loop |
| `/test-fix-loop` | TypeScript error elimination loop |
| `/model-route` | Choose right model for a task |
| `/reflect` | Extract session learnings → instincts |
| `/learn-eval` | Quality-gated learning extraction |
| `/instinct-status` | View learned instincts |
| `/instinct-export` | Share instincts with teammates |
| `/instinct-import` | Import teammate instincts |
| `/evolve` | Cluster instincts into formal skills |
| `/fresh-session` | Reset context after long session |
| `/update-memory` | Save session to memory-bank |
| `/handoff-report` | Report for user when done |
| `/sync-rules` | Pull/push rules from master repo |
| `/load-context` | Generate full project briefing |
| `/capture-convention` | Format mistake as a rule instantly |
| `/docs` | Search Rocket/Supabase/Next.js docs |
| `/use-notepad` | Inject a reusable template |

---

## Troubleshooting

See `TROUBLESHOOTING.md` for detailed solutions to common setup problems.

For MCP connection issues: run `/check-mcp` — it diagnoses each server individually.
For hook issues: confirm `chmod +x .cursor/hooks-scripts/*.sh` was run.
For rules not loading: ask Cursor "which rules are you applying?" to debug auto-loading.

---

## V20 — The New Hook Architecture

V20 replaces 4 shell scripts with 14 Node.js hooks covering every Cursor event:

| Hook | What It Does |
|---|---|
| `sessionStart` | Loads previous session + active issues + instinct count into context before you type |
| `sessionEnd` | Parses actual JSONL transcript → extracts user messages, tools, files → writes session log |
| `stop` | Writes cost estimate to `memory-bank/costs.jsonl` after every response |
| `beforeShellExecution` | Blocks dangerous cmds + dev servers outside tmux + embedded secrets |
| `afterFileEdit` | console.log detection with line numbers, format reminder, review reminder at 5+ edits |
| `beforeSubmitPrompt` | Catches API keys before they're sent to the AI |
| `beforeTabFileRead` | Hard blocks Tab from reading .env/.key/.pem |
| `beforeReadFile` | Warns when agent reads sensitive files |
| `beforeMCPExecution` | Logs all MCP calls to mcp-audit.log |
| `afterMCPExecution` | Logs MCP results to mcp-audit.log |
| `subagentStart`/`Stop` | Logs every agent spawn and completion |
| `preCompact` | Marks compaction point in session log so you can see where context was summarized |
| `afterShellExecution` | Captures PR URL from gh pr create, build status |

**Runtime controls** (set in shell):
```bash
export ECC_HOOK_PROFILE=minimal    # only critical hooks
export ECC_HOOK_PROFILE=standard   # default — all hooks except git-push-reminder
export ECC_HOOK_PROFILE=strict     # everything including tmux reminder and push review
export ECC_DISABLED_HOOKS=pre:shell:dev-server-block,post:edit:format-remind
```

## The Dynamic System Prompt Pattern (Power User)

From the ECC longform guide — the most powerful context pattern:

```bash
# Add to ~/.zshrc or ~/.bashrc
alias cursor-dev='ECC_HOOK_PROFILE=standard cursor .'
alias cursor-review='ECC_HOOK_PROFILE=strict cursor .'
alias cursor-research='ECC_HOOK_PROFILE=minimal cursor .'
```

**Why**: System prompt content (loaded via sessionStart hook) has higher authority than user messages, which have higher authority than tool results. The sessionStart hook injects previous session context directly into the highest-authority layer automatically.

## V20 New Skills

- `/iterative-retrieval` — Use before giving any subagent context. 3-cycle loop: broad search → score relevance 0-1 → refine → repeat. Stops when 3+ files score ≥0.7. Saves 8x tokens vs "send everything".
- `/search-first` — 4-step check before writing any utility: does it exist in repo? In packages? As MCP capability? As a skill/notepad? Only write custom code after all four return nothing.
- `/skill-stocktake` — Audits your entire `.cursor/skills/` for quality. Keep/Improve/Merge/Retire verdict per skill with specific reasoning. Run monthly.

## V20 New Agents

- `loop-operator` — Monitors autonomous loops (`/yolo-tdd`, fix loops). Detects stalls, retry storms, scope drift. Escalates when no progress across 2 checkpoints or cost drifts outside budget.
- `harness-optimizer` — Analyzes `.cursor/` configuration. Identifies hook coverage gaps, rule loading efficiency, MCP tool count, memory bank health. Proposes minimal reversible changes.

## Cost Tracking

Every session now writes to `memory-bank/costs.jsonl`:
```json
{"timestamp":"2026-03-19T10:30:00Z","model":"cursor-composer","input_tokens":12500,"output_tokens":3200,"estimated_cost_usd":0.0663}
```

To see your session costs:
```bash
cat memory-bank/costs.jsonl | python3 -c "
import json,sys
rows = [json.loads(l) for l in sys.stdin if l.strip()]
total = sum(r.get('estimated_cost_usd',0) for r in rows)
print(f'Sessions: {len(rows)} | Total estimated: \${total:.4f}')
"
```
