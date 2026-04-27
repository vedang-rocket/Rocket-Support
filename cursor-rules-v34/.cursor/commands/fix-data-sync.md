# /fix-data-sync — Fix Client-Side Data Not Loading / Out of Sync

## When to use
- Dashboard or CRM shows empty state after login
- Data loads on first visit but not after navigating away and back
- Data loads but is stale — doesn't reflect recent saves
- Batch save/upsert silently fails — no error shown, data reverts
- Some tables load, others don't (partial data)
- localStorage config is out of sync with database state
- Component shows old data after another user made changes

**Not for**: Server Component data issues, RLS blocking, Stripe webhook problems.
For those → use `/fix-database`, `/fix-supabase-rls`, or `/fix-stripe`.

---

## Diagnostic Phase (READ ONLY — no changes yet)

### Step 1 — Identify where data fetching lives

```bash
# Find the main data hook(s)
grep -rn "supabase.from\|createClient" src/hooks/ src/contexts/ --include="*.ts" --include="*.tsx"

# Find all useEffect calls that fetch data
grep -rn "useEffect" src/hooks/ src/contexts/ -A 5

# Find localStorage usage (config persistence)
grep -rn "localStorage\|useLocalStorage" src/hooks/ src/contexts/ src/app/
```

### Step 2 — Check the user guard

The #1 cause: data fetch fires before AuthContext sets `user`.

```bash
# Does every data-fetching useEffect guard on user?
grep -B2 -A10 "useEffect" src/hooks/*.ts src/contexts/*.tsx | grep -E "if.*!user|user.*===.*null|!user\b"
```

Expected: every fetch has `if (!user) return` before `supabase.from()`.

### Step 3 — Check the Supabase client type

```bash
# Wrong client type causes silent 0-row returns
grep -rn "createBrowserClient\|createServerClient\|createClient" src/hooks/ src/contexts/
```

- `'use client'` files → must use `createBrowserClient` (via `createClient()` from `lib/supabase/client`)
- Server files → must use `createServerClient` (via `createClient()` from `lib/supabase/server`)

### Step 4 — Check RLS (if 0 rows returned from DB)

Run directly in Supabase SQL editor (bypasses RLS — confirms rows exist):
```sql
SELECT COUNT(*) FROM your_table;   -- substitute actual table name
```

If rows exist but app shows empty → RLS is blocking → use `/fix-supabase-rls` instead.

### Step 5 — Inspect localStorage for stale config

```
DevTools → Application tab → Local Storage → [your origin]
Look for: pipeline config, column config, user preferences
If values look wrong or out of date → clear them and reload
```

---

## Fix Phase — Apply in order, stop when data loads

### Fix 1 — Add user guard to data-fetching useEffect

```typescript
// ❌ WRONG — fires immediately, user is null
useEffect(() => {
  fetchClients()
}, [])

// ✅ CORRECT — waits for user to be set by AuthContext
useEffect(() => {
  if (!user) return
  fetchClients()
}, [user])
```

### Fix 2 — Use Promise.allSettled (not Promise.all) for parallel loads

```typescript
// ❌ WRONG — one failure cancels all others
const [staff, clients, deals] = await Promise.all([
  fetchStaff(),
  fetchClients(),
  fetchDeals(),
])

// ✅ CORRECT — each load is independent; failures are logged, not thrown
const results = await Promise.allSettled([
  fetchStaff(),
  fetchClients(),
  fetchDeals(),
])
results.forEach((result, i) => {
  if (result.status === 'rejected') {
    console.error(`Load failed at index ${i}:`, result.reason)
  }
})
```

### Fix 3 — Refetch from DB after upsert (don't rely on local state)

```typescript
// ❌ WRONG — optimistic update drifts from DB truth
setDeals(prev => prev.map(d => d.id === updated.id ? updated : d))

// ✅ CORRECT — upsert then refetch
await supabase.from('deals').upsert(dealToRow(updated), { onConflict: 'id' })
const { data: fresh } = await supabase
  .from('deals')
  .select('*')
  .eq('id', updated.id)
  .single()
if (fresh) setDeals(prev => prev.map(d => d.id === fresh.id ? rowToDeal(fresh) : d))
```

### Fix 4 — Add camelCase ↔ snake_case mapper (if fields are undefined)

```typescript
// lib/supabase/mappers.ts
export function rowToClient(row: Record<string, unknown>): Client {
  return {
    id: row.id as string,
    firstName: row.first_name as string,
    lastName: row.last_name as string,
    company: row.company as string,
    email: row.email as string,
    createdAt: row.created_at as string,
    // ... map every field
  }
}

export function clientToRow(client: Client): Record<string, unknown> {
  return {
    id: client.id,
    first_name: client.firstName,
    last_name: client.lastName,
    company: client.company,
    email: client.email,
  }
}

// Usage in every fetch:
const { data } = await supabase.from('clients').select('*')
setClients((data ?? []).map(rowToClient))

// Usage in every upsert:
await supabase.from('clients').upsert(clientToRow(client), { onConflict: 'id' })
```

### Fix 5 — Add localStorage schema version (prevents stale config crashes)

```typescript
const CONFIG_VERSION = 'v2'  // bump this when config structure changes

function loadConfig() {
  const version = localStorage.getItem('config_version')
  if (version !== CONFIG_VERSION) {
    localStorage.clear()
    localStorage.setItem('config_version', CONFIG_VERSION)
    return defaultConfig
  }
  const raw = localStorage.getItem('crm_config')
  return raw ? JSON.parse(raw) : defaultConfig
}
```

### Fix 6 — Reduce batch chunk size if upserts silently fail

```typescript
// If 200-item chunks fail silently, try 50
const CHUNK_SIZE = 50  // was 200

for (let i = 0; i < records.length; i += CHUNK_SIZE) {
  const chunk = records.slice(i, i + CHUNK_SIZE)
  const { error } = await supabase
    .from('clients')
    .upsert(chunk.map(clientToRow), { onConflict: 'id' })
  if (error) {
    console.error(`Chunk ${i}–${i + CHUNK_SIZE} failed:`, error.message)
    // continue — don't break; let other chunks succeed
  }
}
```

---

## Verify

```bash
# Confirm user guard is present before every fetch
grep -A8 "useEffect" src/hooks/*.ts | grep -c "if (!user)"

# Confirm mappers are called on every fetch result
grep -n "rowToClient\|rowToDeal\|rowToStaff" src/hooks/*.ts src/lib/supabase/*.ts

# Confirm Promise.allSettled is used for parallel loads
grep -rn "Promise.allSettled\|Promise.all" src/hooks/ src/contexts/
```

## Files Changed
Document which files were touched and why:
- `src/hooks/[main data hook]` — added user guard, switched to allSettled
- `src/lib/supabase/mappers.ts` — created (if missing)
- `src/lib/supabase/crmService.ts` — updated upsert chunk size (if applicable)

## If Still Broken

1. Open browser DevTools → Console → look for network errors on Supabase requests
2. Check Supabase Dashboard → API logs → filter by your table — are requests arriving?
3. If requests arrive but return 0 rows → RLS issue → run `/fix-supabase-rls`
4. If requests don't arrive → client not initialized → check env vars: `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY`
