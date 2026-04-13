# Notepad: MCP Diagnostic Queries
# Reference with: @notepad-mcp-diagnostics

Quick MCP queries to run when debugging any Rocket.new issue.

## Run all via Supabase MCP execute_sql:

```sql
-- 1. All tables (confirm migrations ran)
SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;

-- 2. RLS status per table
SELECT relname, relrowsecurity FROM pg_class
WHERE relnamespace = 'public'::regnamespace AND relkind = 'r';

-- 3. All policies on a specific table (replace 'profiles')
SELECT policyname, cmd, qual FROM pg_policies
WHERE tablename = 'profiles' AND schemaname = 'public';

-- 4. Profile trigger exists?
SELECT tgname FROM pg_trigger WHERE tgname = 'on_auth_user_created';

-- 5. Orphaned users (no profile = blank dashboard)
SELECT COUNT(*) FROM auth.users u
WHERE NOT EXISTS (SELECT 1 FROM public.profiles p WHERE p.id = u.id);

-- 6. Column names for a table (replace 'your_table')
SELECT column_name, data_type FROM information_schema.columns
WHERE table_name = 'your_table' AND table_schema = 'public';

-- 7. Tables with zero policies (data leak risk)
SELECT t.tablename FROM pg_tables t
WHERE t.schemaname = 'public'
AND NOT EXISTS (SELECT 1 FROM pg_policies p WHERE p.tablename = t.tablename);
```
