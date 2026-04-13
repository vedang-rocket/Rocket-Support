---
name: implement-rbac
description: >
  role based access control supabase, RBAC nextjs supabase,
  admin moderator member roles supabase, different permissions per user supabase,
  user roles supabase jwt claims, restrict pages by role nextjs,
  custom postgres roles supabase, RLS with user roles,
  add admin role supabase, check user role in nextjs server component,
  auth hook custom claims supabase, user_role JWT claim supabase,
  protect route by role nextjs middleware, admin panel access control supabase
globs: ["**/*.ts", "**/*.tsx", "**/*.sql"]
alwaysApply: false
---

# Skill: Implement RBAC (Role-Based Access Control)

**Stack**: Supabase Auth + PostgreSQL + Next.js App Router
**When to use**: App needs different permissions for different user types (admin, member, moderator, etc.)

---

## The Complete 5-Step Implementation

### Step 1 — Schema: enum + roles table
```sql
-- Run in Supabase SQL Editor
CREATE TYPE app_role AS ENUM ('admin', 'moderator', 'member');

CREATE TABLE user_roles (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id    UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  role       app_role NOT NULL DEFAULT 'member',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id)
);

ALTER TABLE user_roles ENABLE ROW LEVEL SECURITY;

-- Users can read their own role (needed for client-side checks)
CREATE POLICY "read_own_role" ON user_roles
  FOR SELECT USING (auth.uid() = user_id);

-- Only admins can change roles (use service_role for bootstrap)
CREATE POLICY "admin_manage_roles" ON user_roles
  FOR ALL USING (
    EXISTS (SELECT 1 FROM user_roles WHERE user_id = auth.uid() AND role = 'admin')
  );

-- Automatically assign 'member' role on signup
CREATE OR REPLACE FUNCTION assign_default_role()
RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public AS $$
BEGIN
  INSERT INTO public.user_roles (user_id, role) VALUES (NEW.id, 'member');
  RETURN NEW;
END;
$$;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION assign_default_role();
```

### Step 2 — Auth Hook: add role to JWT
```sql
CREATE OR REPLACE FUNCTION public.custom_access_token_hook(event JSONB)
RETURNS JSONB LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public AS $$
DECLARE
  claims    JSONB;
  user_role app_role;
BEGIN
  SELECT role INTO user_role
  FROM public.user_roles
  WHERE user_id = (event->>'user_id')::UUID;

  claims := event->'claims';
  claims := jsonb_set(claims, '{user_role}', to_jsonb(COALESCE(user_role::TEXT, 'member')));
  RETURN jsonb_set(event, '{claims}', claims);
END;
$$;

GRANT EXECUTE ON FUNCTION public.custom_access_token_hook TO supabase_auth_admin;
REVOKE EXECUTE ON FUNCTION public.custom_access_token_hook FROM authenticated, anon, public;
```
```
Connect: Supabase Dashboard → Authentication → Hooks → Custom Access Token
→ Set to: public.custom_access_token_hook
```

### Step 3 — RLS policies that use the role
```sql
-- Helper function — reads role from JWT (fast, no DB hit)
CREATE OR REPLACE FUNCTION auth.user_role()
RETURNS TEXT LANGUAGE sql STABLE AS $$
  SELECT COALESCE(auth.jwt() ->> 'user_role', 'member');
$$;

-- Example: admins see all orders, members see only their own
CREATE POLICY "orders_select" ON orders FOR SELECT USING (
  auth.user_role() = 'admin'
  OR auth.uid() = user_id
);

-- Only admins can delete
CREATE POLICY "orders_delete" ON orders FOR DELETE USING (
  auth.user_role() = 'admin'
);

-- Admins can update anything; members only their own
CREATE POLICY "orders_update" ON orders FOR UPDATE USING (
  auth.user_role() = 'admin'
  OR auth.uid() = user_id
);
```

### Step 4 — Read role in Next.js (server-side)
```typescript
// lib/auth.ts — reusable helper
import { createClient } from '@/lib/supabase/server'

export type AppRole = 'admin' | 'moderator' | 'member'

export async function getUserWithRole() {
  const supabase = await createClient()
  const { data: { user }, error } = await supabase.auth.getUser()
  if (error || !user) return null

  // Role is in app_metadata (set by auth hook)
  const role = (user.app_metadata?.user_role ?? 'member') as AppRole
  return { ...user, role }
}

export async function requireRole(requiredRole: AppRole) {
  const user = await getUserWithRole()
  if (!user) throw new Error('Not authenticated')

  const roleHierarchy: AppRole[] = ['member', 'moderator', 'admin']
  const userLevel = roleHierarchy.indexOf(user.role)
  const requiredLevel = roleHierarchy.indexOf(requiredRole)

  if (userLevel < requiredLevel) throw new Error('Insufficient permissions')
  return user
}
```

```typescript
// app/(protected)/admin/page.tsx — protect a page by role
import { requireRole } from '@/lib/auth'
import { redirect } from 'next/navigation'

export default async function AdminPage() {
  try {
    const user = await requireRole('admin')
  } catch {
    redirect('/')  // not admin → redirect
  }

  return <div>Admin panel — only admins see this</div>
}
```

```typescript
// Middleware — protect entire /admin route group
// middleware.ts (project root)
import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'

export async function middleware(request: NextRequest) {
  const response = NextResponse.next()
  const supabase = createServerClient(/* ... */)

  const { data: { user } } = await supabase.auth.getUser()

  if (request.nextUrl.pathname.startsWith('/admin')) {
    if (!user) return NextResponse.redirect(new URL('/login', request.url))
    const role = user.app_metadata?.user_role
    if (role !== 'admin') return NextResponse.redirect(new URL('/', request.url))
  }

  return response
}

export const config = { matcher: ['/admin/:path*'] }
```

### Step 5 — Assign admin role (one-time bootstrap)
```typescript
// app/api/admin/seed-role/route.ts — run once with service_role
import { createClient } from '@supabase/supabase-js'

export async function POST(request: Request) {
  // Protect with a secret so only you can call this
  const { secret, userId } = await request.json()
  if (secret !== process.env.ADMIN_SEED_SECRET) {
    return Response.json({ error: 'Forbidden' }, { status: 403 })
  }

  const adminSupabase = createClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.SUPABASE_SERVICE_ROLE_KEY!
  )

  await adminSupabase
    .from('user_roles')
    .upsert({ user_id: userId, role: 'admin' }, { onConflict: 'user_id' })

  return Response.json({ ok: true })
}
```

---

## Common Mistakes

| Mistake | Fix |
|---|---|
| Reading role from `user_metadata` | Use `app_metadata` — user_metadata is editable by the user themselves via updateUser() |
| Role not showing in JWT after hook setup | User must sign out and sign back in to get new token |
| RLS policy too slow | Add `(SELECT auth.user_role())` with SELECT wrapper to cache per query |
| Auth hook function not granted to supabase_auth_admin | Run the GRANT EXECUTE line |
| Role trigger fires but user_roles row missing | Check trigger is AFTER INSERT on auth.users, not public.users |
