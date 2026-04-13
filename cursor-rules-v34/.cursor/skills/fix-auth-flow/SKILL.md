---
name: fix-auth-flow
description: >
    user cannot log in, login broken, can't sign in, session not persisting after page refresh,
  OAuth redirect fails blank page after Google login, dashboard redirects to login loop,
  JWT expired error, AuthSessionMissingError, middleware not working sessions expire randomly,
  protected route accessible without login, Google OAuth not working, GitHub login fails,
  magic link not working email link expired, password reset redirect broken, auth session missing,
  user gets logged out every hour, signInWithOAuth callback error, middleware.ts not running,
  exchangeCodeForSession error, dashboard blank after signup no user data
globs: ["**/*.ts", "**/*.tsx", "**/*.js", "**/*.sql"]
---

# Skill: Fix Auth Flow

**Stack**: Next.js App Router + Supabase `@supabase/ssr`  
**When to use**: Any authentication issue in a Rocket.new project

---

## Step 1 — Run the Automated Audit First

**Step 0 — MCP Live Check (fastest path)**

If Supabase MCP is connected, run these BEFORE anything else:
```sql
-- Profile trigger exists?
SELECT tgname FROM pg_trigger WHERE tgname = 'on_auth_user_created';

-- Any users with no profile? (blank dashboard cause)
SELECT COUNT(*) as orphaned FROM auth.users u
WHERE NOT EXISTS (SELECT 1 FROM public.profiles p WHERE p.id = u.id);

-- RLS on profiles enabled?
SELECT relrowsecurity FROM pg_class 
WHERE relname = 'profiles' AND relnamespace = 'public'::regnamespace;

-- Policies on profiles?
SELECT policyname, cmd FROM pg_policies 
WHERE tablename = 'profiles' AND schemaname = 'public';
```
These 4 queries surface the root cause of 80% of auth issues in under 30 seconds.
If MCP is not connected, proceed to Step 1 below.

## Step 1 — Run the Shell Audit

```bash
# Copy scripts/audit-auth.sql → paste into Supabase SQL Editor → Run
# This surfaces RLS issues, missing triggers, and table state in one shot
```

Then run these shell checks:

```bash
# A. Middleware location (most common root cause)
ls middleware.ts 2>/dev/null && echo "✅ middleware at root" || echo "❌ MISSING at root"
ls app/middleware.ts 2>/dev/null && echo "❌ WRONG LOCATION — move to root" || echo "✅ not in /app"

# B. getSession() in server code (silent auth bug)
grep -rn "getSession()" ./app ./lib ./middleware.ts
# Any result NOT in a comment/string = broken — replace with getUser()

# C. Deprecated package
grep "auth-helpers-nextjs" package.json && echo "❌ DEPRECATED — migrate to @supabase/ssr"

# D. Auth callback route exists
ls app/auth/callback/route.ts 2>/dev/null && echo "✅ exists" || echo "❌ MISSING — OAuth will fail"

# E. Environment variables loaded
node -e "require('dotenv').config({path:'.env'}); \
  console.log('URL:', !!process.env.NEXT_PUBLIC_SUPABASE_URL, \
  'ANON:', !!process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY)"
```

---

## Step 2 — Identify Symptom → Follow Branch

### Symptom A: Users randomly logged out / session expires after ~1 hour
**Cause**: `middleware.ts` missing or not calling `updateSession()`  
**Fix**:
```typescript
// middleware.ts — MUST be at project root
import { type NextRequest } from 'next/server'
import { updateSession } from '@/lib/supabase/middleware'

export async function middleware(request: NextRequest) {
  return await updateSession(request)
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)'],
}
```

### Symptom B: Protected route accessible without login
**Cause**: Client-side-only auth check, or `getSession()` instead of `getUser()`  
**Fix**:
```typescript
// app/(protected)/[page]/page.tsx
import { redirect } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'

export default async function Page() {
  const supabase = await createClient()
  const { data: { user }, error } = await supabase.auth.getUser() // NOT getSession()
  if (error || !user) redirect('/login')
  // ... rest of page
}
```

### Symptom C: OAuth (Google/GitHub) redirect fails / blank page after consent
**Critical fact**: Social OAuth NEVER works on `localhost` — requires a live deployed URL.

```
Checklist:
□ Testing on deployed URL? (not localhost — OAuth won't work there)
□ app/auth/callback/route.ts exists?
□ Supabase callback URL in Google/GitHub OAuth app:
  https://[project-id].supabase.co/auth/v1/callback
□ All app URLs in Supabase → Auth → URL Configuration:
  http://localhost:3000
  https://[app].netlify.app
  https://[custom-domain.com]
```

```typescript
// app/auth/callback/route.ts — exact required content
import { NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url)
  const code = searchParams.get('code')
  const next = searchParams.get('next') ?? '/dashboard'

  if (code) {
    const supabase = await createClient()
    const { error } = await supabase.auth.exchangeCodeForSession(code)
    if (!error) return NextResponse.redirect(`${origin}${next}`)
  }
  return NextResponse.redirect(`${origin}/login?error=auth_failed`)
}
```

### Symptom D: Login works, but dashboard is blank (no user data shown)
**Cause**: Profile trigger missing — `profiles` table is empty after signup  
**Fix**: Run `scripts/audit-auth.sql` to confirm, then:
```sql
-- Run in Supabase SQL Editor
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.profiles (id, display_name, created_at)
  VALUES (NEW.id, COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.email), NOW())
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE PROCEDURE public.handle_new_user();

-- Backfill existing users who have no profile
INSERT INTO public.profiles (id, display_name, created_at)
SELECT id, email, created_at FROM auth.users
WHERE id NOT IN (SELECT id FROM public.profiles)
ON CONFLICT DO NOTHING;
```

### Symptom E: "JWT expired" / "Invalid JWT" / "no API key"
**Cause**: Missing middleware (tokens never refresh) or env vars not set  
**Fix**: Verify `middleware.ts` exists at root (Step 1). Then check env vars:
```bash
node -e "require('dotenv').config({path:'.env'}); \
  console.log(process.env.NEXT_PUBLIC_SUPABASE_URL ? '✅ URL set' : '❌ URL missing')"
```

### Symptom F: "AuthApiError: Email link is invalid or has expired"
**Cause**: Confirmation link older than 24h, or already used  
**Fix**: Add resend link in the UI:
```typescript
await supabase.auth.resend({ type: 'signup', email: userEmail })
```

### Symptom G: Works in dev, auth broken in production
**Cause**: Production URL not added to Supabase redirect URLs  
**Fix**: Supabase Dashboard → Auth → URL Configuration → add:
- `https://your-app.netlify.app`
- `https://your-app.netlify.app/auth/callback`
- `https://your-custom-domain.com` (if applicable)

---

## Step 3 — Verify Fix

```bash
# 1. TypeScript check — no auth-related type errors
npx tsc --noEmit | grep -i "auth\|session\|cookie\|middleware"

# 2. Confirm no getSession() remains in server code
grep -rn "getSession()" ./app ./lib ./middleware.ts
# Expected: 0 results (or only in comments)

# 3. Test the full flow
# - Sign up new user → check profiles table for new row
# - Log out → navigate to /dashboard → should redirect to /login
# - Log in → should redirect to /dashboard
```

---

## Step 4 — Common Fixes Reference

| Error | File | Fix |
|---|---|---|
| `AuthSessionMissingError` | Server Component | Use `createClient` from `lib/supabase/server.ts` |
| Session lost on refresh | `middleware.ts` | Must call `updateSession()` |
| OAuth blank redirect | `app/auth/callback/route.ts` | Must call `exchangeCodeForSession(code)` |
| Hydration error with auth | Client Component | Wrap auth state in `useEffect`, not top-level |
| `cookies() should be awaited` | `lib/supabase/server.ts` | `const cookieStore = await cookies()` |

---

## Reference Files
- `scripts/audit-auth.sql` — diagnostic queries for Supabase SQL Editor
