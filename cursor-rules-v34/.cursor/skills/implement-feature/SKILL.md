---
name: implement-feature
description: >
    how do I add a new page, how to build a new feature, adding a new Supabase table,
  creating an API route endpoint, how to add authentication to a route, implement from scratch,
  build a dashboard, add CRUD operations, how do I add file upload, add real-time updates,
  integrate payments Stripe, add email sending Resend, add a chat interface OpenAI,
  add role-based access control, add Google OAuth social login, implement search,
  add user profile page, create new Server Action, build a form with validation,
  how to add notifications, implement subscription billing, add admin panel
globs: ["**/*.ts", "**/*.tsx", "**/*.js", "**/*.sql"]
---

# Skill: Implement Feature

**Stack**: Next.js App Router + Supabase + Tailwind  
**When to use**: Adding any new feature to an existing Rocket.new project

---

## The 7-Step Procedure

Every feature follows this exact sequence. Never skip steps — each depends on the previous.

```
Step 1: Schema      → define the data shape (TypeScript type)
Step 2: Migration   → write and run the SQL
Step 3: API Route   → server-side data access
Step 4: Component   → UI that uses the API
Step 5: Auth        → protect the route/component
Step 6: Test        → verify each layer works
Step 7: Verify      → end-to-end check
```

---

## Step 1 — Schema: Define the TypeScript Type First

Before writing any SQL or code, define the data shape. This is the contract everything else is built against — it prevents type errors and hallucinations at every later step.

```typescript
// lib/types.ts (or inline in the feature file)
export type YourFeature = {
  id: string                          // UUID, primary key
  user_id: string                     // FK to auth.users
  name: string                        // required text field
  description: string | null          // optional text
  status: 'active' | 'archived'       // enum — use union types
  metadata: Record<string, unknown> | null  // JSON column
  created_at: string                  // timestamptz → string in TS
  updated_at: string
}

// Derived types for forms (omit server-generated fields)
export type CreateYourFeature = Pick<YourFeature, 'name' | 'description' | 'status'>
export type UpdateYourFeature = Partial<CreateYourFeature>
```

---

## Step 2 — Migration: Write and Run the SQL

Create the file: `supabase/migrations/[timestamp]_add_[feature].sql`

```sql
-- supabase/migrations/20240118_add_your_feature.sql

-- Table
CREATE TABLE IF NOT EXISTS your_feature (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  name TEXT NOT NULL,
  description TEXT,
  status TEXT DEFAULT 'active' CHECK (status IN ('active', 'archived')),
  metadata JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index on user_id (ALWAYS add this — queries filter by user)
CREATE INDEX IF NOT EXISTS your_feature_user_id_idx ON your_feature(user_id);

-- Optional: updated_at auto-update trigger
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER your_feature_updated_at
  BEFORE UPDATE ON your_feature
  FOR EACH ROW EXECUTE PROCEDURE update_updated_at();

-- RLS
ALTER TABLE your_feature ENABLE ROW LEVEL SECURITY;
CREATE POLICY "select_own" ON your_feature FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "insert_own" ON your_feature FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "update_own" ON your_feature FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "delete_own" ON your_feature FOR DELETE USING (auth.uid() = user_id);
```

**Run it**: Copy SQL → Supabase SQL Editor → Run  
OR: In Rocket → Integrations → Supabase → Migrations → Push

---

## Step 3 — API Route: Server-Side Data Access

```typescript
// app/api/your-feature/route.ts
import { NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'
import type { YourFeature, CreateYourFeature } from '@/lib/types'

export async function GET() {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const { data, error } = await supabase
    .from('your_feature')
    .select<'*', YourFeature>('*')
    .order('created_at', { ascending: false })

  if (error) return NextResponse.json({ error: error.message }, { status: 500 })
  return NextResponse.json(data)
}

export async function POST(request: Request) {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const body: CreateYourFeature = await request.json()

  // Validate required fields
  if (!body.name?.trim()) {
    return NextResponse.json({ error: 'name is required' }, { status: 400 })
  }

  const { data, error } = await supabase
    .from('your_feature')
    .insert({ ...body, user_id: user.id })
    .select<'*', YourFeature>()
    .single()

  if (error) return NextResponse.json({ error: error.message }, { status: 500 })
  return NextResponse.json(data, { status: 201 })
}
```

---

## Step 4 — Component: UI Layer

**Prefer Server Components for display, Client Components only for interactivity.**

```typescript
// app/(protected)/your-feature/page.tsx — Server Component (data fetching)
import { redirect } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'
import { YourFeatureList } from '@/components/your-feature/list'
import type { YourFeature } from '@/lib/types'

export default async function YourFeaturePage() {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) redirect('/login')

  const { data: items } = await supabase
    .from('your_feature')
    .select<'*', YourFeature>('*')
    .order('created_at', { ascending: false })

  return (
    <div className="container mx-auto p-6">
      <h1 className="text-2xl font-bold mb-6">Your Feature</h1>
      <YourFeatureList items={items ?? []} />
    </div>
  )
}

// components/your-feature/list.tsx — Client Component (interactions)
'use client'
import { useState } from 'react'
import type { YourFeature } from '@/lib/types'

export function YourFeatureList({ items }: { items: YourFeature[] }) {
  const [list, setList] = useState(items)
  // ... interactive UI
  return <div>{list.map(item => <div key={item.id}>{item.name}</div>)}</div>
}
```

---

## Step 5 — Auth Protection

**Three layers — implement all three:**

```typescript
// Layer 1: Middleware (already handles session refresh in middleware.ts)

// Layer 2: Layout-level auth check (protects whole route group)
// app/(protected)/layout.tsx
import { redirect } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'

export default async function ProtectedLayout({ children }: { children: React.ReactNode }) {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) redirect('/login')
  return <>{children}</>
}

// Layer 3: RLS in Supabase (database-level — already done in Step 2)
// Even if layers 1 and 2 are bypassed, the database won't return other users' data
```

---

## Step 6 — Test Each Layer

```bash
# 1. TypeScript compiles
npx tsc --noEmit

# 2. Table exists and has RLS
# Run in Supabase SQL Editor:
# SELECT * FROM pg_policies WHERE tablename = 'your_feature';

# 3. API route responds correctly
curl -X GET http://localhost:3000/api/your-feature
# Should return: {"error":"Unauthorized"} (not logged in)

# 4. Test with browser:
# - Navigate to /your-feature without login → should redirect to /login
# - Log in → navigate to /your-feature → should show feature page
# - Create an item → should appear in the list
# - Log in as different user → should NOT see first user's items
```

---

## Step 7 — Verify End-to-End

```sql
-- Run in Supabase SQL Editor after creating test items
SELECT * FROM your_feature ORDER BY created_at DESC LIMIT 5;

-- Verify user_id is set correctly (not null)
SELECT id, user_id, name, created_at FROM your_feature 
WHERE user_id IS NULL;
-- Should return 0 rows
```

---

## Common Mistakes by Step

| Step | Mistake | Fix |
|---|---|---|
| Schema | Using `any` for JSONB columns | Use `Record<string, unknown>` |
| Migration | No index on `user_id` | Always add: `CREATE INDEX ... ON table(user_id)` |
| Migration | `ON DELETE CASCADE` missing | Without it, deleting a user leaves orphaned rows |
| API Route | Using `getSession()` | Always `getUser()` in server code |
| Component | Fetching data in `useEffect` | Fetch in Server Component, pass as props |
| Auth | Client-side only auth check | Add server-side `getUser()` + `redirect()` |
| Verify | Testing as same user | Always test with TWO different accounts |
