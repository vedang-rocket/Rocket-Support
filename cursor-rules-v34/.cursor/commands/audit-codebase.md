# Purpose: Full automated health check on a new Rocket.new project — run this FIRST before anything else

This command replaces 30 minutes of manual reading with a 3-minute automated audit.
Run it the moment you open a user's project. Do not touch any code until this completes.

## SCOPE
Read-only. This command produces a report. It changes nothing.

---

## PHASE 1 — MCP Live Database Check (if Supabase MCP connected)

Run all of these via Supabase MCP `execute_sql` tool and report results:

```sql
-- A. All tables that exist
SELECT tablename FROM pg_tables 
WHERE schemaname = 'public' ORDER BY tablename;

-- B. Which tables have RLS enabled vs disabled
SELECT relname AS table_name,
  CASE relrowsecurity WHEN true THEN '✅ RLS on' ELSE '❌ RLS OFF' END AS rls_status
FROM pg_class
WHERE relnamespace = 'public'::regnamespace AND relkind = 'r'
ORDER BY relname;

-- C. Tables with ZERO policies (silent data leak risk)
SELECT t.tablename
FROM pg_tables t
WHERE t.schemaname = 'public'
AND NOT EXISTS (
  SELECT 1 FROM pg_policies p 
  WHERE p.tablename = t.tablename AND p.schemaname = 'public'
);

-- D. Profile trigger exists?
SELECT tgname FROM pg_trigger WHERE tgname = 'on_auth_user_created';

-- E. Users with no profile row (broken signups)
SELECT COUNT(*) AS orphaned_users FROM auth.users u
WHERE NOT EXISTS (SELECT 1 FROM public.profiles p WHERE p.id = u.id);

-- F. Migration files vs actual tables (are migrations pushed?)
SELECT COUNT(*) AS table_count FROM pg_tables WHERE schemaname = 'public';
```

---

## PHASE 2 — Code Red Flag Scan

Run these shell commands and report every hit:

```bash
# 1. getSession() in server code (critical security bug)
echo "=== getSession() usage (must be 0) ===" 
grep -rn "getSession()" ./app ./lib ./middleware.ts 2>/dev/null

# 2. middleware.ts location (must be at root)
echo "=== middleware.ts location ==="
ls middleware.ts 2>/dev/null && echo "✅ at root" || echo "❌ MISSING from root"
ls app/middleware.ts 2>/dev/null && echo "❌ WRONG — inside /app" || true

# 3. Deprecated Supabase package
echo "=== Deprecated auth-helpers ==="
grep -r "auth-helpers-nextjs" package.json 2>/dev/null && echo "❌ DEPRECATED" || echo "✅ clean"

# 4. request.json() in Stripe webhook (silent failure)
echo "=== Stripe webhook raw body ==="
grep -rn "request\.json()" app/api/webhooks/ 2>/dev/null && echo "❌ BROKEN" || echo "✅ clean"

# 5. Auth callback route exists
echo "=== Auth callback route ==="
ls app/auth/callback/route.ts 2>/dev/null && echo "✅ exists" || echo "❌ MISSING — OAuth will fail"

# 6. Service role key accidentally exposed
echo "=== Service role key exposure ==="
grep -rn "NEXT_PUBLIC_SUPABASE_SERVICE_ROLE\|NEXT_PUBLIC.*SERVICE_ROLE" .env (or .env.local) ./app ./lib 2>/dev/null && echo "❌ EXPOSED" || echo "✅ clean"

# 7. Files with no header (hurts embedding accuracy)
echo "=== Files missing @file headers ==="
find ./app ./lib ./components -name "*.ts" -o -name "*.tsx" 2>/dev/null | head -20 | while read f; do
  if ! grep -q "@file\|@purpose\|@module" "$f" 2>/dev/null; then
    echo "  missing header: $f"
  fi
done

# 8. TypeScript errors
echo "=== TypeScript errors ==="
npx tsc --noEmit 2>&1 | head -20

# 9. Environment variables completeness
echo "=== Required env vars ==="
for var in NEXT_PUBLIC_SUPABASE_URL NEXT_PUBLIC_SUPABASE_ANON_KEY SUPABASE_SERVICE_ROLE_KEY STRIPE_SECRET_KEY NEXT_PUBLIC_SITE_URL; do
  ENV_FILE=".env"; [ -f ".env (or .env.local)" ] && ENV_FILE=".env (or .env.local)"; grep -q "^$var=" "$ENV_FILE" 2>/dev/null && echo "  ✅ $var" || echo "  ❌ MISSING: $var"
done
```

---

## PHASE 3 — Architecture Consistency Check

Read these files and report what you find:

```
@middleware.ts — does it call updateSession()? Is it at root?
@lib/supabase/server.ts — is it using @supabase/ssr createServerClient?
@lib/supabase/client.ts — is it using @supabase/ssr createBrowserClient?
@app/auth/callback/route.ts — does it call exchangeCodeForSession(code)?
@app/api/webhooks/stripe/route.ts — does it use request.text() not request.json()?
```

---

## PHASE 4 — Generate the Project Health Report

Output this exact format:

```
╔══════════════════════════════════════════════╗
║     ROCKET PROJECT HEALTH REPORT             ║
╚══════════════════════════════════════════════╝

PROJECT: [folder name]
AUDITED: [date]

━━━ DATABASE ━━━
Tables found: [list]
RLS status: [X tables enabled, Y tables DISABLED ❌]
Tables with no policies: [list or "none ✅"]
Profile trigger: [exists ✅ / MISSING ❌]
Orphaned users: [count]
Migrations: [appears pushed ✅ / UNCERTAIN ⚠️]

━━━ CRITICAL CODE ISSUES ━━━
getSession() in server code: [count — 0 ✅ or list of files ❌]
middleware.ts location: [root ✅ / wrong ❌ / missing ❌]
Deprecated auth-helpers: [clean ✅ / found ❌]
Stripe raw body: [clean ✅ / broken ❌]
Auth callback route: [exists ✅ / missing ❌]
Service role key exposed: [clean ✅ / exposed ❌]

━━━ CODE QUALITY ━━━
TypeScript errors: [count]
Files missing headers: [count]
Environment variables: [X/9 present]

━━━ VERDICT ━━━
🔴 CRITICAL (fix before anything else): [list]
🟡 IMPORTANT (fix soon): [list]  
🟢 CLEAN: [list]

━━━ RECOMMENDED FIX ORDER ━━━
1. [highest priority issue]
2. [second priority]
3. [etc.]
```

---

## INTERACTIVE SELECTION (After Report)

After delivering the report, render this interactive prompt:

```
From the issues found above, which would you like to fix?

Reply with one of:
  "fix all critical"     → I will run the appropriate fix commands for all 🔴 items
  "fix [number]"         → I will fix only that item from the recommended order
  "fix auth"             → I will run /fix-auth
  "fix database"         → I will run /fix-database
  "fix stripe"           → I will run /fix-stripe
  "fix performance"      → I will run /fix-performance
  "security audit"       → I will run /security-audit
  "make legible"         → I will run /make-legible
  "skip"                 → You will handle fixes manually

Waiting for your selection.
```

This makes the audit report immediately actionable — one reply routes to the right fix command automatically.

