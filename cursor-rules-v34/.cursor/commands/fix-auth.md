# Purpose: Full auth diagnostic and fix for any Rocket.new auth issue

This is a Rocket.new Next.js App Router project using Supabase `@supabase/ssr`.

## Context I need from you before starting
Provide the following or I will ask:
- The exact error message (copy/paste verbatim, not paraphrased)
- Which file the error occurs in
- What triggers it (e.g., "after OAuth login", "on page refresh", "on first load")

## CHECKPOINT PROTOCOL

After every 3 files changed, STOP and output:
- Files changed so far + one-line summary of each change
- Current understanding of remaining work
- Any assumptions made that need your verification

Do not proceed until you explicitly say "continue".

Rationale: Accuracy degrades ~2% per reasoning step. At 20 steps, failure rate compounds to ~40%. Checkpoints reset context and keep changes reviewable.

---
## My diagnostic sequence — I will follow this exactly

**Step 0 — MCP Live Diagnostics (run BEFORE reading any code)**

If Supabase MCP is connected, run these immediately and report results:
```sql
-- A. Profile trigger exists?
SELECT tgname FROM pg_trigger WHERE tgname = 'on_auth_user_created';
-- B. Users with no profile row (blank dashboard cause)
SELECT COUNT(*) FROM auth.users u
WHERE NOT EXISTS (SELECT 1 FROM public.profiles p WHERE p.id = u.id);
-- C. RLS on profiles table
SELECT relrowsecurity FROM pg_class 
WHERE relname = 'profiles' AND relnamespace = 'public'::regnamespace;
```
Report each result before touching any code. If MCP is not connected, skip to Step 1.

**Step 1 — Scope lock declaration**
I will only touch files directly related to the auth issue.
I will NOT modify: data fetching logic, Stripe code, UI components, unrelated routes.

**Step 2 — Run these checks first, report results before fixing anything**
```bash
# A. Middleware location
ls middleware.ts && echo "✅ root" || echo "❌ missing from root"
ls app/middleware.ts 2>/dev/null && echo "❌ WRONG LOCATION" || true

# B. getSession() in server code (critical security bug)
grep -rn "getSession()" ./app ./lib ./middleware.ts

# C. auth/callback route
ls app/auth/callback/route.ts && echo "✅ exists" || echo "❌ MISSING — OAuth will fail"

# D. Deprecated package
grep "auth-helpers-nextjs" package.json && echo "❌ DEPRECATED"
```

**Step 3 — Chain-of-thought trace**
Trace the full auth flow from the trigger point to the failure.
State what SHOULD happen at each step vs what IS happening.
Name the exact step where behavior diverges.
Do not propose any code until the trace is complete.

**Step 4 — Minimal fix**
Apply the smallest possible change that fixes the identified root cause.
Show the diff. Explain every line changed.
Do not restructure, rename, or "improve" anything else.

## Hard constraints
- `getUser()` always in server code — never `getSession()`
- `lib/supabase/server.ts` in Server Components — `lib/supabase/client.ts` in `'use client'` only
- Social OAuth NEVER works on localhost — must test on deployed URL
- `app/auth/callback/route.ts` must call `supabase.auth.exchangeCodeForSession(code)`
- `middleware.ts` must be at project root and call `updateSession()`

## Output format
1. Diagnostic results (shell command output)
2. Chain-of-thought trace (numbered steps)
3. Root cause identified (one sentence)
4. Files to change: [list]
5. Files NOT touched: [list]
6. Diff for each file (one at a time, waiting for confirmation)

