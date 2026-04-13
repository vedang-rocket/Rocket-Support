---
name: fix-database-performance
description: >
  slow database query supabase fix, query taking too long supabase,
  EXPLAIN ANALYZE postgres supabase, Seq Scan slow fix index,
  supabase query performance dashboard slow, N+1 query nextjs supabase,
  too many connections supabase fix, RLS making queries slow,
  missing index supabase fix, database performance debugging supabase,
  pg_stat_statements slow queries find, supabase performance advisor,
  timeout 57014 query cancelled fix, query optimization supabase nextjs
globs: ["**/*.ts", "**/*.tsx", "**/*.sql"]
alwaysApply: false
---

# Skill: Fix Database Performance

**Stack**: Supabase PostgreSQL + Next.js
**When to use**: Any query is slow, timeouts are happening (57014), or the app feels sluggish under load.

---

## Step 1 — Run Database Advisors First (30 seconds)

Before touching any code:
```
Supabase Dashboard → Advisors → Performance Advisor
```
It automatically finds missing indexes on FK columns and other common issues. Fix everything it flags before continuing.

---

## Step 2 — Find the Slow Query

### Via Dashboard (easiest)
```
Supabase Dashboard → Reports → Query Performance
→ Sort by "Total time" or "Average time"
→ Click a query to see its full text
```

### Via SQL (if you need more detail)
```sql
SELECT
  SUBSTRING(query, 1, 100) AS query,
  calls,
  ROUND(mean_exec_time::NUMERIC, 1) AS avg_ms,
  ROUND(total_exec_time::NUMERIC, 0) AS total_ms
FROM pg_stat_statements
WHERE mean_exec_time > 100   -- queries averaging over 100ms
ORDER BY mean_exec_time DESC
LIMIT 10;
```

---

## Step 3 — Run EXPLAIN ANALYZE on the Slow Query

```sql
-- In Supabase SQL Editor — replace with the actual slow query
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT * FROM orders WHERE user_id = '[USER_ID]' AND status = 'pending';
```

### Read the output — 3 things to check

**1. Seq Scan on a large table = needs an index**
```
Seq Scan on orders  (actual time=0.02..48.3 rows=3 loops=1)
  Rows Removed by Filter: 89997   ← reading 90k rows to find 3
```
→ Fix: `CREATE INDEX CONCURRENTLY idx ON orders(user_id, status);`

**2. High cost relative to rows returned**
```
cost=0.00..45210.00   ← high cost
rows=3                ← only returning 3 rows
```
→ Large mismatch = wrong execution plan, probably missing index.

**3. Estimated vs actual rows differ greatly**
```
(cost=... rows=10000 ...) (actual rows=3 ...)
```
→ Statistics are stale. Run: `ANALYZE orders;`

---

## Step 4 — Add the Right Index

```sql
-- For WHERE user_id = x AND status = y  →  composite index
CREATE INDEX CONCURRENTLY orders_user_status_idx ON orders(user_id, status);

-- For WHERE created_at > x  →  B-tree on timestamp
CREATE INDEX CONCURRENTLY orders_created_at_idx ON orders(created_at DESC);

-- For JSONB column queries  →  GIN index
CREATE INDEX CONCURRENTLY events_metadata_idx ON events USING gin(metadata);

-- For arrays  →  GIN index
CREATE INDEX CONCURRENTLY products_tags_idx ON products USING gin(tags);

-- For large time-series tables  →  BRIN (tiny index, very fast for date ranges)
CREATE INDEX CONCURRENTLY events_ts_brin ON events USING brin(created_at);

-- Partial index for filtered queries (much smaller, faster)
CREATE INDEX CONCURRENTLY active_orders_idx ON orders(user_id)
WHERE deleted_at IS NULL AND status NOT IN ('completed', 'cancelled');
```

Always use `CONCURRENTLY` in production — it doesn't lock writes.

---

## Step 5 — Check if RLS is the Bottleneck

```sql
-- Test query without RLS — if suddenly fast, RLS is the problem
SET row_security = off;
EXPLAIN ANALYZE SELECT * FROM orders WHERE user_id = '[ID]';
SET row_security = on;
```

**Fix slow RLS policy:**
```sql
-- SLOW — auth.uid() called per row
CREATE POLICY "slow_policy" ON orders USING (user_id = auth.uid());

-- FAST — result cached for whole query
CREATE POLICY "fast_policy" ON orders USING (user_id = (SELECT auth.uid()));

-- Verify policy has a supporting index
-- Every column in a USING() clause must have an index
CREATE INDEX CONCURRENTLY orders_user_id_idx ON orders(user_id);
```

---

## Step 6 — Fix N+1 Queries

N+1 = 1 query to get parent rows, then 1 query per row for children.

```typescript
// DETECT: look for looped supabase queries in your code
// BAD — N+1 (N queries for N orders)
const orders = await supabase.from('orders').select('*')
for (const order of orders.data) {
  const profile = await supabase     // ← one extra query PER order
    .from('profiles').select('*').eq('id', order.user_id).single()
}

// FIX — single join query
const { data: orders } = await supabase
  .from('orders')
  .select('*, profiles(full_name, avatar_url)')
```

---

## Step 7 — Fix Connection Exhaustion (too many connections)

```sql
-- Check current connections
SELECT state, COUNT(*) FROM pg_stat_activity WHERE datname = 'postgres' GROUP BY state;
-- idle = leaked connections
```

```typescript
// FIX — Drizzle/Prisma on Netlify MUST use port 6543 and max: 1
const client = postgres(process.env.DATABASE_URL!, {
  prepare: false,
  max: 1,           // ← critical for serverless
})

// FIX — supabase-js (no change needed — uses REST API, no direct connections)
```

---

## Step 8 — Fix Timeout 57014

```
Error: canceling statement due to statement timeout (code 57014)
```

```sql
-- Increase timeout for specific long-running query only
BEGIN;
SET LOCAL statement_timeout = '60s';
-- run your query here
COMMIT;
```

```typescript
// In supabase-js — use raw SQL via rpc for timeout-sensitive operations
await supabase.rpc('run_with_timeout', { timeout_ms: 30000 })
```

---

## Verify

After each change, re-run EXPLAIN ANALYZE and confirm:
- Seq Scan replaced with Index Scan
- Actual time dropped significantly
- No more Rows Removed by Filter in the thousands
