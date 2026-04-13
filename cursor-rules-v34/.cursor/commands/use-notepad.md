# Purpose: Inject a Notepad template into the current prompt — zero re-typing, zero token waste

Instead of writing long boilerplate prompts, reference a Notepad.
The Notepad expands with the exact template + any variables you provide.

## Usage
/use-notepad [name] [variables]

Examples:
/use-notepad rls-template table=projects
/use-notepad api-route-template method=POST path=app/api/notifications/route.ts
/use-notepad new-feature-checklist feature=file-uploads
/use-notepad supabase-query-patterns
/use-notepad mcp-diagnostics table=subscriptions

---

## Available Notepads

| Name | What It Injects | Token Cost vs Typing |
|---|---|---|
| `rls-template` | Complete RLS SQL for a table | Saves ~200 tokens |
| `api-route-template` | Standard route handler pattern | Saves ~300 tokens |
| `supabase-query-patterns` | All query patterns reference | Saves ~400 tokens |
| `new-feature-checklist` | Full feature verification checklist | Saves ~500 tokens |
| `mcp-diagnostics` | All diagnostic MCP queries | Saves ~300 tokens |

---

## What I Will Do

1. Find the Notepad matching `[name]`
2. Insert the template with `[variables]` substituted
3. Execute it immediately — no re-explanation needed

### For `rls-template table=projects`:
```sql
-- RLS setup for: projects table

ALTER TABLE projects ENABLE ROW LEVEL SECURITY;

CREATE POLICY "select_own" ON projects FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "insert_own" ON projects FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "update_own" ON projects FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "delete_own" ON projects FOR DELETE USING (auth.uid() = user_id);

CREATE INDEX IF NOT EXISTS projects_user_id_idx ON projects(user_id);
```
Run via Supabase MCP `execute_sql` or paste in Supabase SQL Editor.

### For `api-route-template method=POST path=app/api/notifications/route.ts`:
Creates a complete POST route handler at the specified path following
all Rocket.new conventions — auth check, typed response, error handling.

### For `new-feature-checklist feature=file-uploads`:
Runs through the complete verification checklist specifically for the
file-uploads feature — checking schema, API, UI, auth layers.

---

## Creating Your Own Notepads

1. Cursor → View → Notepads → New Notepad
2. Name it exactly as you want to reference it
3. Paste the template with `[VARIABLE]` placeholders
4. Reference with `/use-notepad name variable=value`

**Best candidates for custom Notepads:**
- Any prompt you've typed more than twice
- Project-specific component templates
- Standard SQL patterns for this project's schema
- Common debugging sequences

---

## Token Efficiency

A 500-token prompt template you type repeatedly → save those tokens every time.
10 uses = 5,000 tokens saved. 100 uses = 50,000 tokens saved.
At scale, Notepads pay for themselves within the first week.
