# Purpose: Full security audit of a Rocket.new project — finds vulnerabilities before they reach production

Run this once per project on first open, and again before any production deployment.
This is a read-only audit. It finds issues and reports them. It does not fix anything.

## SCOPE LOCK
I will read files and run queries only. I will NOT modify any code during this command.
Every finding gets a severity level: 🔴 CRITICAL / 🟡 HIGH / 🟠 MEDIUM / 🟢 LOW

---

## SECTION 1 — Authentication Security

```bash
# 1. getSession() in server code (can be spoofed — use getUser() instead)
grep -rn "getSession()" ./app ./lib ./middleware.ts 2>/dev/null

# 2. Client Supabase used in Server Components (leaks auth state)
grep -rn "from '@/lib/supabase/client'" ./app/**/page.tsx ./app/**/layout.tsx 2>/dev/null

# 3. Protected routes without server-side auth check
grep -rn "redirect\|getUser" ./app/\(protected\)/ 2>/dev/null | grep -c "getUser" || echo "0 server-side auth checks in protected routes"

# 4. Middleware missing (sessions never refresh)
ls middleware.ts 2>/dev/null || echo "❌ NO MIDDLEWARE"
```

Via Supabase MCP:
```sql
-- Routes that exist in code but have no RLS protection on their data tables
SELECT tablename FROM pg_tables 
WHERE schemaname = 'public' 
AND relrowsecurity = false
FROM pg_class WHERE relname = tablename;
```

---

## SECTION 2 — Data Exposure

Via Supabase MCP `execute_sql`:
```sql
-- Tables with RLS disabled (entire table readable by anyone)
SELECT c.relname AS table_name
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' 
AND c.relkind = 'r'
AND c.relrowsecurity = false;

-- Tables with RLS enabled but ZERO policies (returns empty for everyone)
SELECT DISTINCT t.tablename
FROM pg_tables t
WHERE t.schemaname = 'public'
AND NOT EXISTS (
  SELECT 1 FROM pg_policies p 
  WHERE p.tablename = t.tablename AND p.schemaname = 'public'
)
AND EXISTS (
  SELECT 1 FROM pg_class c
  WHERE c.relname = t.tablename AND c.relrowsecurity = true
);

-- Policies that allow ALL users to read ALL rows (overly permissive)
SELECT tablename, policyname, qual
FROM pg_policies
WHERE schemaname = 'public'
AND qual = 'true'
AND cmd = 'SELECT';
```

---

## SECTION 3 — Secret Exposure

```bash
# 1. Service role key with NEXT_PUBLIC_ prefix (exposed to browser)
grep -rn "NEXT_PUBLIC.*SERVICE_ROLE\|NEXT_PUBLIC.*service_role" .env.local ./app ./lib 2>/dev/null

# 2. Hardcoded API keys or secrets in code
grep -rn "sk_live_\|sk_test_\|eyJ.*supabase\|whsec_\|re_[a-zA-Z0-9]" ./app ./lib ./components 2>/dev/null | grep -v ".env"

# 3. .env.local accidentally in git
cat .gitignore 2>/dev/null | grep ".env.local" || echo "⚠️ .env.local may not be in .gitignore"

# 4. Console.log of sensitive data
grep -rn "console\.log.*user\|console\.log.*token\|console\.log.*key\|console\.log.*password" ./app ./lib 2>/dev/null
```

---

## SECTION 4 — Payment Security

```bash
# 1. Stripe webhook using request.json() — signature bypass
grep -rn "request\.json()" ./app/api/webhooks/ 2>/dev/null

# 2. Stripe secret key referenced client-side
grep -rn "STRIPE_SECRET_KEY\|sk_test_\|sk_live_" ./app ./components 2>/dev/null | grep -v "process\.env" | grep -v "route\.ts" | grep -v "action\.ts"

# 3. Webhook handler missing signature verification
grep -A5 "export async function POST" ./app/api/webhooks/stripe/route.ts 2>/dev/null | grep -c "constructEvent" || echo "❌ No signature verification found"
```

Via Stripe MCP (if connected):
```
webhooks.read → check all endpoints have signing secret configured
```

---

## SECTION 5 — API Route Security

```bash
# 1. API routes with no auth check
find ./app/api -name "route.ts" | while read f; do
  if ! grep -q "getUser\|auth\|Unauthorized" "$f" 2>/dev/null; then
    echo "⚠️ No auth check: $f"
  fi
done

# 2. API routes that return all rows without user filtering
grep -rn "\.select\('\*'\)" ./app/api/ 2>/dev/null | grep -v "eq.*user"

# 3. Missing rate limiting on AI/expensive endpoints
grep -rn "openai\|anthropic\|OPENAI" ./app/api/ 2>/dev/null | grep -v "rate\|limit" | head -5
```

---

## SECTION 6 — Generate Security Report

```
╔══════════════════════════════════════════════╗
║     SECURITY AUDIT REPORT                   ║
╚══════════════════════════════════════════════╝

PROJECT: [folder name]
AUDITED: [date]

━━━ 🔴 CRITICAL (fix immediately) ━━━
[List each critical finding with file + line number]

━━━ 🟡 HIGH (fix before production) ━━━
[List each high finding]

━━━ 🟠 MEDIUM (fix soon) ━━━
[List each medium finding]

━━━ 🟢 LOW / INFO ━━━
[List each low finding]

━━━ CLEAN ✅ ━━━
[List areas with no issues found]

━━━ RECOMMENDED FIX ORDER ━━━
1. [Most critical — fix right now]
2. [Second]
3. [etc.]

━━━ SUMMARY ━━━
Critical: X | High: X | Medium: X | Low: X
Overall security posture: [CRITICAL / POOR / FAIR / GOOD]
```

After the report: ask "Which issues should I fix first?" and wait for instruction.
Do NOT start fixing without explicit direction — the developer may already know about some findings.
