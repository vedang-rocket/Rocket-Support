# /start — New Project Kickoff

Runs `/load-context` and `/audit-codebase` in one pass.
Use this every time you open a project for the first time in a session.

---

## SEQUENCE (run all steps, report inline as you go)

### Step 1 — Identify project type (10 seconds)

```bash
cat package.json | grep -E '"name"|"version"|"stripe|openai|anthropic|resend|twilio|calendly"'
find ./app/api ./src/app/api -name "route.ts" 2>/dev/null | sort
ls src/contexts/AuthContext.tsx src/hooks/ 2>/dev/null
```

State immediately: **"This is TYPE [X] — [description]"**
(See `rocket-project-types.mdc` for detection guide.)

---

### Step 2 — Read product brief

Read `docs/PRD.md` if it exists. Extract:
- What the app does (one sentence)
- Who uses it
- What the user reported is broken

If no PRD exists, ask exactly these three questions and wait for answers before continuing:
```
1. What does this app do? (one sentence)
2. What's broken? (describe what you're seeing)
3. Any rules I must know? (e.g. "only admins can delete records")
```

---

### Step 3 — Live database check (via Supabase MCP)

Run all queries and report results inline:

```sql
-- Tables + row counts + RLS status
SELECT
  t.tablename,
  CASE c.relrowsecurity WHEN true THEN '✅ RLS on' ELSE '❌ RLS OFF' END AS rls,
  COALESCE(s.n_live_tup, 0) AS rows
FROM pg_tables t
JOIN pg_class c ON c.relname = t.tablename
LEFT JOIN pg_stat_user_tables s ON s.relname = t.tablename
WHERE t.schemaname = 'public'
ORDER BY s.n_live_tup DESC NULLS LAST;

-- Tables with RLS on but ZERO policies (silent data leak)
SELECT t.tablename AS no_policies
FROM pg_tables t
WHERE t.schemaname = 'public'
AND NOT EXISTS (
  SELECT 1 FROM pg_policies p
  WHERE p.tablename = t.tablename AND p.schemaname = 'public'
);

-- Profile trigger
SELECT tgname FROM pg_trigger WHERE tgname = 'on_auth_user_created';

-- Orphaned users (signed up but no profile row)
SELECT COUNT(*) AS orphaned_users FROM auth.users u
WHERE NOT EXISTS (SELECT 1 FROM public.profiles p WHERE p.id = u.id);
```

If MCP is not connected: note "⚠️ MCP not connected — database state unknown" and continue.

---

### Step 4 — Previous session memory

```
search_nodes: "[project folder name]"
```

- Found → summarise previous findings in 2-3 sentences
- Not found → "First session on this project"

Also read `memory-bank/project-context.md` and `memory-bank/active-issues.md` if they exist.

---

### Step 5 — Code red flag scan

Run these and report every hit:

```bash
# Auth files — where do they live?
echo "=== Auth file locations ==="
ls middleware.ts src/middleware.ts 2>/dev/null
ls lib/supabase/middleware.ts lib/supabase/session.ts src/lib/supabase/middleware.ts src/lib/supabase/session.ts 2>/dev/null
ls contexts/AuthContext.tsx src/contexts/AuthContext.tsx 2>/dev/null
ls app/auth/callback/route.ts src/app/auth/callback/route.ts 2>/dev/null

# Critical code bugs
echo "=== getSession() in server code (must be 0) ==="
grep -rn "getSession()" ./app ./src/app ./lib ./src/lib ./middleware.ts ./src/middleware.ts 2>/dev/null

echo "=== Deprecated auth-helpers ==="
grep "auth-helpers-nextjs" package.json 2>/dev/null && echo "❌ DEPRECATED" || echo "✅ clean"

echo "=== Stripe webhook raw body ==="
grep -rn "request\.json()" app/api/webhooks/ src/app/api/webhooks/ 2>/dev/null && echo "❌ BROKEN" || echo "✅ clean or no Stripe"

echo "=== Service role key exposed to browser ==="
grep -rn "NEXT_PUBLIC_.*SERVICE_ROLE\|NEXT_PUBLIC_.*SECRET" .env .env.local ./app ./src 2>/dev/null && echo "❌ EXPOSED" || echo "✅ clean"

echo "=== TypeScript errors ==="
npx tsc --noEmit 2>&1 | head -15

echo "=== Environment variables ==="
for var in NEXT_PUBLIC_SUPABASE_URL NEXT_PUBLIC_SUPABASE_ANON_KEY NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY SUPABASE_SERVICE_ROLE_KEY STRIPE_SECRET_KEY NEXT_PUBLIC_SITE_URL; do
  grep -q "^$var=" .env.local 2>/dev/null && echo "  ✅ $var" || echo "  ❌ MISSING: $var"
done
```

---

### Step 6 — Learned patterns check

Read `memory-bank/learned-patterns.md`.
List the top 3 patterns most relevant to this project type.

---

### Step 7 — Output the combined report

```
╔══════════════════════════════════════════════════════════════╗
║                /start REPORT — [PROJECT NAME]                ║
╚══════════════════════════════════════════════════════════════╝
OPENED: [date]  |  TYPE: [A/B/C/D/E/F/G/H] — [description]

📱 WHAT THIS IS
[One sentence. Who uses it. What it does.]

👤 USER REPORT
[What the user said is broken, or "not reported yet"]

━━━ DATABASE ━━━
Tables: [list with row counts]
RLS: [X tables on ✅ / Y tables OFF ❌]
No-policy tables: [list or "none ✅"]
Profile trigger: [✅ exists / ❌ MISSING]
Orphaned users: [count or "0 ✅"]

━━━ CRITICAL CODE ISSUES ━━━
getSession() in server code: [0 ✅ / list of files ❌]
middleware location: [✅ root / ❌ wrong / ❌ missing]
Deprecated auth-helpers: [✅ clean / ❌ found]
Stripe raw body: [✅ clean / ❌ broken / — no Stripe]
Service role key exposed: [✅ clean / ❌ exposed]

━━━ ENVIRONMENT ━━━
[list each var as ✅ present or ❌ missing]
TypeScript errors: [count or "0 ✅"]

━━━ PREVIOUS SESSIONS ━━━
[Summary from memory, or "First session"]

━━━ PATTERNS TO WATCH ━━━
1. [Most relevant learned pattern for this project type]
2. [Second]
3. [Third]

━━━ VERDICT ━━━
🔴 CRITICAL (fix before anything else): [list]
🟡 IMPORTANT (fix soon): [list]
🟢 CLEAN: [list]

━━━ RECOMMENDED FIX ORDER ━━━
1. [highest priority]
2. [second]
3. [etc.]
```

---

### Step 8 — Interactive fix selector

After the report:

```
Ready to fix. What would you like to do?

  "fix all critical"   → run fix commands for all 🔴 items in order
  "fix auth"           → /fix-auth
  "fix database"       → /fix-database
  "fix stripe"         → /fix-stripe
  "fix data sync"      → /fix-data-sync
  "fix deployment"     → /fix-deployment
  "fix performance"    → /fix-performance
  "preview error"      → /preview-error
  "make legible"       → /make-legible
  "security audit"     → /security-audit
  "fix [number]"       → fix item N from the recommended order above
  "skip"               → I'll handle it manually

Or just describe the problem in plain English and I'll route it.
```

Wait for selection. Do not start any fix until the user replies.
