---
name: fix-supabase-rls
description: >
    Supabase query returns empty array [], data not loading despite data existing in dashboard,
  new row violates row-level security policy error, users can see other users data privacy issue,
  insert fails silently no error but row not created, update not working no error returned,
  delete not working, RLS blocking queries, PGRST116 JSON object requested multiple rows,
  permission denied for table, policy missing no policies found, unauthorized data access,
  authenticated user sees empty results, maybeSingle vs single error, row level security enabled
  all queries empty, supabase select returns nothing, storage upload permission denied
globs: ["**/*.ts", "**/*.tsx", "**/*.js", "**/*.sql"]
---

# Skill: Fix Supabase RLS

**Stack**: Supabase PostgreSQL + Row Level Security  
**When to use**: Any issue where data doesn't load, silently returns `[]`, or throws RLS errors

---

## Step 1 — Diagnose Fast

**Step 0 — MCP Live Check (run first if MCP connected)**

```sql
-- Run via Supabase MCP execute_sql tool:

-- RLS enabled?
SELECT relrowsecurity FROM pg_class 
WHERE relname = 'your_table' AND relnamespace = 'public'::regnamespace;

-- Policies that exist?
SELECT policyname, cmd, qual, with_check FROM pg_policies 
WHERE tablename = 'your_table' AND schemaname = 'public';

-- Exact column names (policy must reference exact name)
SELECT column_name FROM information_schema.columns 
WHERE table_name = 'your_table' AND table_schema = 'public'
ORDER BY ordinal_position;
```
These 3 queries give the complete RLS picture immediately. If MCP not connected, use Step 1 below.

## Step 1 — Diagnose via SQL Editor

```bash
# Run in your terminal to get the table name you're debugging
# Then paste the queries below into Supabase SQL Editor
```

```sql
-- Replace 'your_table' with the actual table name

-- A. Is RLS enabled?
SELECT relrowsecurity FROM pg_class 
WHERE relname = 'your_table' AND relnamespace = 'public'::regnamespace;
-- true = RLS on | false = RLS off (data visible to everyone)

-- B. What policies exist?
SELECT policyname, cmd, qual, with_check 
FROM pg_policies 
WHERE tablename = 'your_table' AND schemaname = 'public';
-- Empty result + RLS enabled = all queries return [] silently

-- C. What are the exact column names? (policy must use exact names)
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'your_table' AND table_schema = 'public'
ORDER BY ordinal_position;
```

---

## Step 2 — Identify the Pattern

### Pattern A: Empty `[]` with no error — RLS silently blocking
```
RLS is ON + zero policies = all queries return [] silently
This is Supabase's default behavior — it's not a bug
Fix: Add the correct policies (see references/rls-templates.md)
```

### Pattern B: `"new row violates row-level security policy"`
```
INSERT policy missing or incorrect WITH CHECK expression
Fix: Add INSERT policy with WITH CHECK (auth.uid() = user_id)
Verify: The column name in the policy MUST match exactly
```

### Pattern C: User sees other users' data
```
SELECT policy too permissive, or RLS is disabled entirely
Fix: Enable RLS + restrict SELECT to auth.uid() = user_id
```

### Pattern D: Admin can't see all data
```
Admin needs a bypass policy — see references/rls-templates.md#admin-access
```

### Pattern E: Correct user sees empty data on first load
```
Likely: profile trigger missing — user row exists in auth.users
but no row in the table being queried
Run: SELECT * FROM your_table WHERE user_id = '[paste user UUID]'
If empty: data insert on signup is broken, not an RLS issue
```

---

## Step 3 — Apply the Fix

### Standard fix — full CRUD for own rows

```sql
-- Enable RLS first
ALTER TABLE your_table ENABLE ROW LEVEL SECURITY;

-- SELECT: users see only their own rows
CREATE POLICY "select_own" ON your_table
  FOR SELECT USING (auth.uid() = user_id);

-- INSERT: users can only insert rows where user_id = their ID
CREATE POLICY "insert_own" ON your_table
  FOR INSERT WITH CHECK (auth.uid() = user_id);

-- UPDATE: users can only update their own rows
CREATE POLICY "update_own" ON your_table
  FOR UPDATE USING (auth.uid() = user_id);

-- DELETE: users can only delete their own rows
CREATE POLICY "delete_own" ON your_table
  FOR DELETE USING (auth.uid() = user_id);
```

### Quick fix — if you need to unblock immediately and add policies later

```sql
-- WARNING: This allows ALL authenticated users to read ALL rows
-- Use only for debugging — remove before production
CREATE POLICY "temp_debug_allow_all" ON your_table
  FOR ALL USING (auth.role() = 'authenticated');
```

---

## Step 4 — Verify Fix

```typescript
// Add this temporarily to your Server Component to debug
const { data, error, count } = await supabase
  .from('your_table')
  .select('*', { count: 'exact' })

console.log({
  data,
  error,          // RLS errors appear here as strings
  count,          // 0 with no error = RLS is silently blocking
  userIdUsed: user?.id,
})
```

```sql
-- Verify from Supabase SQL Editor that policies are applied
SELECT * FROM pg_policies WHERE tablename = 'your_table';
-- Should show: select_own, insert_own, update_own, delete_own
```

---

## Step 5 — Storage RLS (separate from table RLS)

Storage buckets have their own RLS — table policies do NOT cover storage.

```sql
-- Allow users to manage files in their own folder (named by user_id)
CREATE POLICY "upload_own" ON storage.objects
  FOR INSERT WITH CHECK (
    bucket_id = 'your-bucket' 
    AND auth.uid()::text = (storage.foldername(name))[1]
  );

CREATE POLICY "read_own" ON storage.objects
  FOR SELECT USING (
    bucket_id = 'your-bucket' 
    AND auth.uid()::text = (storage.foldername(name))[1]
  );

CREATE POLICY "delete_own" ON storage.objects
  FOR DELETE USING (
    bucket_id = 'your-bucket' 
    AND auth.uid()::text = (storage.foldername(name))[1]
  );
```

---

## Reference Files
- `references/rls-templates.md` — all policy patterns (public, admin, join-based, shared access)
