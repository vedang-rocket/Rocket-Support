# Purpose: Implement a new feature in a Rocket.new project using schema-first, phase-by-phase approach

This is a Rocket.new Next.js App Router project using Supabase `@supabase/ssr` + Tailwind.

## CHECKPOINT PROTOCOL

After every 3 files changed, STOP and output:
- Files changed so far + one-line summary of each change
- Current understanding of remaining work
- Any assumptions made that need your verification

Do not proceed until you explicitly say "continue".

Rationale: Accuracy degrades ~2% per reasoning step. At 20 steps, failure rate compounds to ~40%. Checkpoints reset context and keep changes reviewable.

---


## Usage
/implement-feature [feature name]
Example: /implement-feature user file uploads
Example: /implement-feature team invitations
Example: /implement-feature subscription billing

## Before writing any code — I will do this first

**Phase 0 — Plan (output plan.md, no code)**

I will produce a structured plan covering:
1. TypeScript types needed
2. Database schema (tables, columns, constraints, indexes)
3. RLS policies for each table
4. New files to create (full paths)
5. Existing files to modify (and exactly what changes)
6. Implementation phases with clear boundaries
7. What must NOT change (existing working code)

I will NOT write any implementation code until you confirm the plan.

---

**Phase 1 — Schema and migration (data layer only)**

Once plan is approved:
```
- Define TypeScript type in lib/types.ts
- Generate SQL migration file in supabase/migrations/[timestamp]_[feature].sql
- Include: CREATE TABLE, indexes, RLS enable, all 4 CRUD policies
- Output SQL only — no application code yet
```
Wait for confirmation that SQL ran successfully before Phase 2.

---

**Phase 2 — API layer**

```
- Create app/api/[feature]/route.ts
- GET and POST handlers
- Server-side auth check (getUser()) before every handler
- Typed Supabase queries using types from Phase 1
- Proper error responses
```
Wait for confirmation before Phase 3.

---

**Phase 3 — UI components**

```
- Server Component for data fetching (app/(protected)/[feature]/page.tsx)
- Client Component for interactivity (components/[feature]/*.tsx)
- Loading state (loading.tsx)
- Empty state and error state
```

---

**Phase 4 — Auth protection and verification**

```
- Confirm route is inside (protected)/ group or has explicit getUser() check
- RLS provides database-level protection (already done in Phase 1)
- End-to-end test: create item → appears in list → second user cannot see it
```

## Hard constraints throughout all phases
- `getUser()` never `getSession()` in server code
- Server Component fetches data — Client Component handles interactions
- RLS on every new table, no exceptions
- `ON DELETE CASCADE` on all foreign keys referencing auth.users
- Index on `user_id` column for every new table
- One phase at a time — I will not jump ahead without confirmation

## Output format for plan.md
```markdown
# Feature: [name]

## Types
[TypeScript type definitions]

## Database
[SQL schema]

## Files to create
[list with full paths]

## Files to modify  
[list with what changes]

## Phases
Phase 1: [description]
Phase 2: [description]
...

## Must NOT change
[list of protected files/areas]
```
