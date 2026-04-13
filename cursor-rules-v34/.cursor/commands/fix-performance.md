# Purpose: Diagnose and fix performance issues in a Rocket.new project — N+1 queries, missing indexes, slow DB queries, client-side data fetching

Performance problems in Rocket projects are silent until they're catastrophic.
This command finds them before users do.

## SCOPE LOCK
I will only touch files directly related to the performance issue identified.
I will NOT change logic, auth, or unrelated components.

## CHECKPOINT PROTOCOL
After every 3 files changed, STOP and output:
- Files changed + summary
- Remaining work
- Any assumptions needing verification
Wait for "continue" before proceeding.

---

## PHASE 1 — Database Performance (via Supabase MCP)

If Supabase MCP is connected, run these immediately:

```sql
-- A. Missing indexes on foreign keys (most common Rocket performance gap)
SELECT
  tc.table_name,
  kcu.column_name,
  'MISSING INDEX' AS status
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
AND tc.table_schema = 'public'
AND NOT EXISTS (
  SELECT 1 FROM pg_indexes pi
  WHERE pi.tablename = tc.table_name
  AND pi.indexdef LIKE '%' || kcu.column_name || '%'
);

-- B. Tables with no indexes at all (beyond primary key)
SELECT t.tablename
FROM pg_tables t
WHERE t.schemaname = 'public'
AND (
  SELECT COUNT(*) FROM pg_indexes i
  WHERE i.tablename = t.tablename
  AND i.indexname NOT LIKE '%_pkey'
) = 0;

-- C. Largest tables (high row count = indexes matter most here)
SELECT
  relname AS table_name,
  n_live_tup AS estimated_rows
FROM pg_stat_user_tables
WHERE schemaname = 'public'
ORDER BY n_live_tup DESC
LIMIT 10;

-- D. Slow query detection (if pg_stat_statements enabled)
SELECT
  LEFT(query, 80) AS query_preview,
  calls,
  ROUND((mean_exec_time)::numeric, 2) AS avg_ms,
  ROUND((total_exec_time)::numeric, 2) AS total_ms
FROM pg_stat_statements
WHERE mean_exec_time > 100
ORDER BY mean_exec_time DESC
LIMIT 10;
```

Report all findings before touching any code.

---

## PHASE 2 — N+1 Query Detection in Code

```bash
# Find Supabase queries inside loops or map functions (N+1 pattern)
grep -rn "\.map\|forEach\|for.*of" ./app ./components 2>/dev/null | while read line; do
  file=$(echo "$line" | cut -d: -f1)
  linenum=$(echo "$line" | cut -d: -f2)
  # Check if there's a supabase query within 5 lines after
  context=$(sed -n "$((linenum)),$((linenum+5))p" "$file" 2>/dev/null)
  if echo "$context" | grep -q "supabase\|\.from("; then
    echo "⚠️ Possible N+1: $file:$linenum"
    echo "$context"
    echo "---"
  fi
done

# Find sequential awaits that could be parallelized
grep -rn "await supabase" ./app ./lib 2>/dev/null | awk -F: '{print $1}' | sort | uniq -d | while read f; do
  echo "Multiple sequential awaits in: $f — consider Promise.all()"
done
```

---

## PHASE 3 — Client-Side Data Fetching (Should Be Server Components)

```bash
# useEffect with supabase fetch (should be Server Component instead)
grep -rn "useEffect" ./app ./components 2>/dev/null | while read line; do
  file=$(echo "$line" | cut -d: -f1)
  linenum=$(echo "$line" | cut -d: -f2)
  context=$(sed -n "$((linenum)),$((linenum+10))p" "$file" 2>/dev/null)
  if echo "$context" | grep -q "supabase\|fetch\|axios"; then
    echo "⚠️ Client-side fetch in: $file:$linenum"
    echo "Consider: move to Server Component or React Query"
    echo "---"
  fi
done

# Missing loading.tsx (no loading state = perceived slowness)
find ./app -type d | while read dir; do
  if ls "$dir/page.tsx" 2>/dev/null | grep -q "page"; then
    if ! ls "$dir/loading.tsx" 2>/dev/null | grep -q "loading"; then
      echo "⚠️ Missing loading.tsx: $dir"
    fi
  fi
done
```

---

## PHASE 4 — Image Optimization

```bash
# <img> tags instead of Next.js <Image> (no optimization)
grep -rn "<img " ./app ./components 2>/dev/null | grep -v "//\|<!--"

# Next.js Image without width/height (causes layout shift)
grep -rn "<Image" ./app ./components 2>/dev/null | grep -v "width\|fill"
```

---

## PHASE 5 — Generate Performance Report

```
╔══════════════════════════════════════════════╗
║     PERFORMANCE AUDIT REPORT                 ║
╚══════════════════════════════════════════════╝

━━━ 🔴 CRITICAL (causing real slowness now) ━━━
[N+1 queries found — table + location]
[Missing indexes on high-traffic tables]
[Client-side fetches that should be Server Components]

━━━ 🟡 IMPORTANT (will slow down at scale) ━━━
[Tables with no indexes]
[Sequential awaits that should be parallelized]
[Missing loading states]

━━━ 🟢 QUICK WINS ━━━
[<img> tags to convert to <Image>]
[Queries that can add .limit()]

━━━ RECOMMENDED FIX ORDER ━━━
1. Add missing indexes (SQL — fastest win, zero code change)
2. Fix N+1 queries (replace loop queries with single JOIN query)
3. Move useEffect fetches to Server Components
4. Add missing loading.tsx files
5. Convert <img> to <Image>
```

---

## Common Fixes

### Fix: Missing index
```sql
-- Add after identifying table + column from Phase 1
CREATE INDEX CONCURRENTLY your_table_column_idx ON your_table(column_name);
-- CONCURRENTLY = no table lock, safe on live database
```

### Fix: N+1 query → single query with join
```typescript
// ❌ N+1 — runs one query per post
const posts = await supabase.from('posts').select('*')
const postsWithProfiles = await Promise.all(
  posts.data.map(async post => {
    const profile = await supabase.from('profiles').select('*').eq('id', post.user_id).single()
    return { ...post, profile: profile.data }
  })
)

// ✅ Single query with join
const { data } = await supabase
  .from('posts')
  .select(`*, profiles(display_name, avatar_url)`)
  .order('created_at', { ascending: false })
```

### Fix: Parallel queries instead of sequential
```typescript
// ❌ Sequential — waits for each query
const profile = await supabase.from('profiles').select('*').eq('id', userId).single()
const posts = await supabase.from('posts').select('*').eq('user_id', userId)
const stats = await supabase.from('stats').select('*').eq('user_id', userId)

// ✅ Parallel — all run simultaneously
const [profileRes, postsRes, statsRes] = await Promise.all([
  supabase.from('profiles').select('*').eq('id', userId).single(),
  supabase.from('posts').select('*').eq('user_id', userId),
  supabase.from('stats').select('*').eq('user_id', userId),
])
```

### Fix: useEffect fetch → Server Component
```typescript
// ❌ Client-side fetch with useEffect
'use client'
export function Dashboard() {
  const [data, setData] = useState(null)
  useEffect(() => {
    supabase.from('projects').select('*').then(({ data }) => setData(data))
  }, [])
}

// ✅ Server Component — no loading state needed, no client JS
export default async function Dashboard() {
  const supabase = await createClient()
  const { data } = await supabase.from('projects').select('*')
  return <ProjectList projects={data ?? []} />
}
```
