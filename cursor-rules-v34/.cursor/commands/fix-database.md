# Purpose: Diagnose and fix Supabase data issues — empty results, RLS, wrong client, missing migrations

This is a Rocket.new Next.js App Router project using Supabase `@supabase/ssr`.

## CHECKPOINT PROTOCOL

After every 3 files changed, STOP and output:
- Files changed so far + one-line summary of each change
- Current understanding of remaining work
- Any assumptions made that need your verification

Do not proceed until you explicitly say "continue".

Rationale: Accuracy degrades ~2% per reasoning step. At 20 steps, failure rate compounds to ~40%. Checkpoints reset context and keep changes reviewable.

---


## Context I need from you before starting
- Which table is not returning data?
- What does the query look like? (paste the relevant code block)
- Is the user authenticated when the query runs? (yes/no or unknown)
- Is this a read issue (SELECT) or a write issue (INSERT/UPDATE/DELETE)?

## My diagnostic sequence — I will follow this exactly

**Step 0 — MCP Live Diagnostics (run BEFORE reading any code)**

If Supabase MCP is connected, run these immediately:
```sql
-- A. Does the table exist + row count?
SELECT schemaname, tablename 
FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;

-- B. RLS enabled on target table?
SELECT relrowsecurity FROM pg_class 
WHERE relname = 'your_table' AND relnamespace = 'public'::regnamespace;

-- C. What policies exist?
SELECT policyname, cmd, qual FROM pg_policies 
WHERE tablename = 'your_table' AND schemaname = 'public';

-- D. Exact column names (policy column must match exactly)
SELECT column_name FROM information_schema.columns 
WHERE table_name = 'your_table' AND table_schema = 'public'
ORDER BY ordinal_position;
```
These 4 queries answer 90% of Supabase data issues before touching a single file.
If MCP is not connected, skip to Step 1.

**Step 1 — Scope lock**
I will only modify queries, RLS policies, and the specific component with the data issue.
I will NOT touch auth logic, UI styling, unrelated pages, or other tables.

**Step 2 — Run SQL diagnostics FIRST, report before writing any code**

Run these in Supabase SQL Editor (replace `your_table` with the actual table name):
```sql
-- A. Does the table exist?
SELECT EXISTS (
  SELECT 1 FROM information_schema.tables 
  WHERE table_schema = 'public' AND table_name = 'your_table'
) AS table_exists;

-- B. Is RLS enabled?
SELECT relrowsecurity FROM pg_class 
WHERE relname = 'your_table' AND relnamespace = 'public'::regnamespace;

-- C. What policies exist?
SELECT policyname, cmd, qual, with_check 
FROM pg_policies 
WHERE tablename = 'your_table' AND schemaname = 'public';

-- D. Does data actually exist?
SELECT COUNT(*) FROM your_table;

-- E. Exact column names (policy must match)
SELECT column_name FROM information_schema.columns 
WHERE table_name = 'your_table' AND table_schema = 'public'
ORDER BY ordinal_position;
```

**Step 3 — Check the code**
```bash
# Is the correct Supabase client used?
grep -n "from '@/lib/supabase" [file-with-the-query]
# Server Component must use server.ts, not client.ts
```

**Step 4 — Identify the failure**
Based on diagnostic results, identify which of these is the cause:
- A) Table doesn't exist → migrations not pushed
- B) RLS on + zero policies → all queries return `[]` silently
- C) Wrong column name in policy → policy never matches
- D) Wrong Supabase client for context → browser client in Server Component
- E) Supabase project paused → all queries fail with connection error

**Step 5 — Apply minimal fix**
Fix only the identified layer. Show SQL or TypeScript diff, one change at a time.

## Hard constraints
- Never disable RLS entirely to fix a query issue — fix the policy instead
- Never use the service role key in client components
- Always use `auth.uid()` in RLS policies, not hardcoded UUIDs
- `.maybeSingle()` when row might not exist, `.single()` only when guaranteed

## Output format
1. SQL diagnostic results (paste output)
2. Root cause (one sentence: "The issue is: X")
3. Fix: SQL (if RLS/schema) or TypeScript diff (if query/client)
4. Verification query to confirm fix worked
