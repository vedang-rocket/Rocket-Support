---
name: search-first
description: >
  research before coding, does this library exist, find existing solution before writing code,
  should I use a package or write custom, check npm before implementing, check if MCP exists,
  starting new feature look for existing tools, add X functionality search first,
  before creating utility helper abstraction, avoid reinventing the wheel,
  find existing implementation pattern
globs: []
alwaysApply: false
---

# Skill: Search Before You Code

**The rule**: Before writing any utility, helper, integration, or abstraction — run this 4-step check.

## The 4-Step Check (2 minutes, saves hours)

### Step 1 — Does it already exist in this repo?
```bash
# Search for existing implementations
grep -rn "function handle\|async function fetch\|export function" ./lib ./utils 2>/dev/null | head -20
# Search for the concept in existing code
rg "rate.limit\|throttle\|debounce" ./lib ./app 2>/dev/null
```

### Step 2 — Does a battle-tested package exist?

For Rocket.new projects, check these first:
```bash
# Already in package.json?
cat package.json | grep -i "zod\|axios\|date-fns\|clsx\|lucide"

# Common packages by category:
# Validation:    zod (TS), joi
# Date handling: date-fns, dayjs (NOT moment)
# HTTP client:   ky, got (Node), native fetch (preferred)
# Form handling: react-hook-form
# Animation:     framer-motion
# Email:         resend (already in most Rocket projects)
# File upload:   uploadthing, supabase storage (already available)
```

### Step 3 — Does an MCP server already provide this?

Before adding any new integration, check `.cursor/mcp.json`:
- Supabase MCP already handles: table queries, schema info, RLS checks, migrations
- Stripe MCP already handles: product reads, customer lookups, balance
- Memory MCP already handles: cross-session knowledge storage

If the MCP can do it → use MCP, don't write API wrapper code.

### Step 4 — Does a Cursor skill/notepad already cover it?

Check `.cursor/skills/` and `.cursor/notepads/`:
- `@rls-setup` → standard RLS SQL patterns
- `@api-route-pattern` → full route handler with auth
- `@supabase-queries` → common Supabase query patterns
- `fix-auth-flow` skill → full auth diagnostic procedure

## Decision Matrix

| Signal | Action |
|---|---|
| Exact match, well-maintained, MIT/Apache | **Adopt** — install and use directly |
| Partial match, good foundation | **Extend** — install + write thin wrapper |
| Multiple weak matches | **Compose** — combine 2-3 small packages |
| MCP already provides it | **Use MCP** — no code needed |
| Nothing suitable found | **Build** — write custom, informed by research |

## Anti-patterns to avoid

- Writing a utility without checking if one exists in the repo
- Ignoring that MCP already provides the capability
- Wrapping a library so heavily it loses its benefits
- Installing a 500KB package for one small feature
- Writing custom email sending when Resend is already in the project

## Rocket.new specific — things you almost never need to write

- **Email sending** → Resend is already configured, just call the API
- **File storage** → Supabase Storage bucket already exists
- **Database queries** → Supabase client already set up, RLS already configured
- **Auth checks** → `supabase.auth.getUser()` already works everywhere
- **Payments** → Stripe is already integrated if it's in package.json
- **UI components** → shadcn/ui components are already available in most Rocket projects
