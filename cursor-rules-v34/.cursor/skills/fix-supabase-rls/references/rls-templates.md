# RLS Policy Templates

Complete reference for every Row Level Security pattern used in Rocket.new projects.

---

## 1. Standard User-Owns-Data (Most Common)

```sql
ALTER TABLE your_table ENABLE ROW LEVEL SECURITY;

CREATE POLICY "select_own" ON your_table FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "insert_own" ON your_table FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "update_own" ON your_table FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "delete_own" ON your_table FOR DELETE USING (auth.uid() = user_id);
```

---

## 2. Public Read + Owner Write

Use for: blog posts, product listings, public profiles

```sql
ALTER TABLE posts ENABLE ROW LEVEL SECURITY;

-- Anyone can read
CREATE POLICY "public_read" ON posts FOR SELECT USING (true);

-- Only owner can write
CREATE POLICY "owner_insert" ON posts FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "owner_update" ON posts FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "owner_delete" ON posts FOR DELETE USING (auth.uid() = user_id);
```

---

## 3. Admin Access (Read All Rows)

```sql
-- Admin can read all rows (assumes 'role' column in profiles table)
CREATE POLICY "admin_read_all" ON your_table FOR SELECT
  USING (
    auth.uid() = user_id  -- own rows always visible
    OR EXISTS (
      SELECT 1 FROM profiles 
      WHERE id = auth.uid() AND role = 'admin'
    )
  );

-- Admin can update any row
CREATE POLICY "admin_update_all" ON your_table FOR UPDATE
  USING (
    auth.uid() = user_id
    OR EXISTS (
      SELECT 1 FROM profiles 
      WHERE id = auth.uid() AND role = 'admin'
    )
  );
```

---

## 4. Team / Shared Access

Use for: workspace-based apps, team projects, shared documents

```sql
-- Members of the same workspace can see the workspace's data
CREATE POLICY "workspace_members_read" ON workspace_items FOR SELECT
  USING (
    workspace_id IN (
      SELECT workspace_id FROM workspace_members 
      WHERE user_id = auth.uid()
    )
  );

CREATE POLICY "workspace_members_insert" ON workspace_items FOR INSERT
  WITH CHECK (
    workspace_id IN (
      SELECT workspace_id FROM workspace_members 
      WHERE user_id = auth.uid()
    )
  );
```

---

## 5. Soft Delete (Status-Based Visibility)

Use for: archived items, deleted records

```sql
-- Users see only their active (non-deleted) rows
CREATE POLICY "select_own_active" ON your_table FOR SELECT
  USING (auth.uid() = user_id AND deleted_at IS NULL);

-- Users can see all their rows including deleted (for trash view)
CREATE POLICY "select_own_all" ON your_table FOR SELECT
  USING (auth.uid() = user_id);
```

---

## 6. Profiles Table (Special Case)

The `profiles` table references `auth.users` with `id` as the primary key, not `user_id`.

```sql
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;

-- Users read their own profile
CREATE POLICY "select_own" ON profiles FOR SELECT USING (auth.uid() = id);

-- Users can read all profiles (for directory/team features)
CREATE POLICY "public_read" ON profiles FOR SELECT USING (true);

-- Users update only their own profile
CREATE POLICY "update_own" ON profiles FOR UPDATE USING (auth.uid() = id);

-- Trigger inserts profile on signup (bypass RLS with SECURITY DEFINER)
-- Note: INSERT is handled by trigger, not direct user action
-- No INSERT policy needed if using the on_auth_user_created trigger
```

---

## 7. Subscriptions Table

```sql
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;

-- Users read their own subscription
CREATE POLICY "select_own" ON subscriptions FOR SELECT USING (auth.uid() = user_id);

-- Stripe webhook inserts/updates via service role key (bypasses RLS)
-- No INSERT/UPDATE policies needed if webhook uses service_role key
-- If using anon key in webhook: add these
CREATE POLICY "service_insert" ON subscriptions FOR INSERT
  WITH CHECK (auth.uid() = user_id);
CREATE POLICY "service_update" ON subscriptions FOR UPDATE
  USING (auth.uid() = user_id);
```

---

## 8. Messages / Chat (Real-Time)

```sql
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages REPLICA IDENTITY FULL;  -- required for real-time

-- Users in the room can read messages
CREATE POLICY "room_members_read" ON messages FOR SELECT
  USING (
    room_id IN (
      SELECT room_id FROM room_members WHERE user_id = auth.uid()
    )
  );

CREATE POLICY "room_members_insert" ON messages FOR INSERT
  WITH CHECK (
    auth.uid() = sender_id
    AND room_id IN (
      SELECT room_id FROM room_members WHERE user_id = auth.uid()
    )
  );
```

---

## 9. Service Role Bypass (for Webhooks, Admin API)

The `service_role` key bypasses ALL RLS policies.  
Use in server-side code only — NEVER expose to browser.

```typescript
// lib/supabase/service.ts — SERVER ONLY
import { createClient } from '@supabase/supabase-js'

export function createServiceClient() {
  return createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!,  // never NEXT_PUBLIC_
  )
}

// Usage in Stripe webhook (needs to bypass RLS to update any user's subscription)
// app/api/webhooks/stripe/route.ts
import { createServiceClient } from '@/lib/supabase/service'
const supabase = createServiceClient()
await supabase.from('subscriptions').upsert({ user_id: session.metadata.user_id, ... })
```

---

## 10. Debugging RLS — Useful Queries

```sql
-- See all policies on all tables
SELECT schemaname, tablename, policyname, cmd, qual, with_check
FROM pg_policies
WHERE schemaname = 'public'
ORDER BY tablename, cmd;

-- Check if RLS is enabled on each table
SELECT 
  relname AS table_name,
  relrowsecurity AS rls_enabled,
  relforcerowsecurity AS rls_forced
FROM pg_class
WHERE relnamespace = 'public'::regnamespace AND relkind = 'r'
ORDER BY relname;

-- Test a policy as a specific user (replace UUID)
SET LOCAL role authenticated;
SET LOCAL "request.jwt.claims" = '{"sub": "YOUR-USER-UUID-HERE"}';
SELECT * FROM your_table LIMIT 5;
RESET role;
```

---

## Common Mistakes

| Mistake | Effect | Fix |
|---|---|---|
| `auth.uid() = id` on a table where the FK is `user_id` | Policy never matches | Check column name: `auth.uid() = user_id` |
| RLS enabled but no policies | All queries silently return `[]` | Add at minimum a SELECT policy |
| Using anon key in Stripe webhook | Can't upsert subscriptions | Use service role key in webhook |
| Forgetting `WITH CHECK` on INSERT | Insert policy has no effect | Add `WITH CHECK` to INSERT policies |
| Missing `REPLICA IDENTITY FULL` | Real-time subscriptions don't fire | Run `ALTER TABLE t REPLICA IDENTITY FULL` |
