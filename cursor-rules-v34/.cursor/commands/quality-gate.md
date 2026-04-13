# Purpose: Run comprehensive quality checks across the codebase or specific paths

## Usage
/quality-gate              — full codebase check
/quality-gate app/         — check specific directory
/quality-gate app/api/     — check API routes only

## What I Will Do

### Gate 1 — TypeScript
```bash
npx tsc --noEmit
```
Report: error count, files with errors, most common error types.

### Gate 2 — Security Patterns
```bash
# Forbidden patterns
grep -rn "getSession()" ./app ./lib ./middleware.ts
grep -rn "request\.json()" ./app/api/webhooks
grep -rn "NEXT_PUBLIC_.*SERVICE_ROLE\|NEXT_PUBLIC_.*SECRET" .env* ./.env
grep -rn "auth-helpers-nextjs" ./package.json ./app ./lib
```

### Gate 3 — Code Quality
```bash
# Files over 500 lines (Cursor comprehension limit)
find ./app ./lib ./components -name "*.ts" -o -name "*.tsx" | xargs wc -l | sort -rn | awk '$1 > 500'

# Missing file headers (embedding index signal)
find ./app ./lib -name "*.ts" -o -name "*.tsx" | xargs grep -L "@file" | head -20

# console.log in production code
grep -rn "console\.log" ./app ./lib --include="*.ts" --include="*.tsx" | grep -v "// " | head -10
```

### Gate 4 — RLS Coverage (via Supabase MCP)
```sql
-- Tables without any RLS policies (data leak risk)
SELECT t.tablename FROM pg_tables t
WHERE t.schemaname = 'public'
AND NOT EXISTS (
  SELECT 1 FROM pg_policies p
  WHERE p.tablename = t.tablename AND p.schemaname = 'public'
);

-- Tables with RLS disabled
SELECT relname FROM pg_class
WHERE relnamespace = 'public'::regnamespace 
AND relkind = 'r' AND relrowsecurity = false;
```

### Gate 5 — Missing Error Boundaries
```bash
# Pages without error.tsx (unhandled errors crash entire page)
find ./app -name "page.tsx" | while read f; do
  dir=$(dirname "$f")
  [ ! -f "$dir/error.tsx" ] && echo "Missing error.tsx: $dir"
done | head -10
```

## Output Format

```
QUALITY GATE REPORT — [scope] — [date]

Gate 1 TypeScript    ✅ 0 errors / ❌ [n] errors
Gate 2 Security      ✅ Clean / ❌ [n] violations
Gate 3 Code Quality  ✅ Clean / ⚠️  [n] warnings
Gate 4 RLS Coverage  ✅ All tables covered / ❌ [n] tables unprotected
Gate 5 Error Bounds  ✅ All pages covered / ⚠️  [n] missing error.tsx

VERDICT: PASS / FAIL / NEEDS ATTENTION

CRITICAL (must fix before shipping):
  [list]

WARNINGS (should fix):
  [list]
```
