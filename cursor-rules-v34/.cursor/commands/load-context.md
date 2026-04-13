# Purpose: Generate a complete project briefing before any work begins — fuses docs, project type detection, and live MCP data into one context window

This is the "librarian" command. It fuses all context sources into a single briefing.
Run it immediately after /sync-rules on every new project.
After this runs, Cursor walks into every session fully briefed — no re-explaining needed.

---

## My Loading Sequence

### Step 1 — Read the Product Brief
Read `docs/PRD.md` if it exists.
Extract:
- What the app does (one sentence)
- Who uses it
- What's currently broken (from user report)
- Business rules that affect fixes

If `docs/PRD.md` doesn't exist → ask the developer to fill it in first, or ask these questions:
```
Before I start, I need 3 things:
1. What does this app do? (one sentence)
2. What did the user report is broken?
3. Are there any business rules I must know? (e.g. "only admins can delete")
```

### Step 2 — Identify Project Type
Run the project type detection from `rocket-project-types.mdc`:

```bash
cat package.json | grep -E '"stripe|openai|anthropic|resend|twilio|calendly"'
find ./app/api -name "route.ts" 2>/dev/null | sort
```

State: "This is a **[TYPE] — [description]**"

### Step 3 — Query Live Database State (via Supabase MCP)

```sql
-- What tables exist and their approximate size
SELECT
  t.tablename,
  c.relrowsecurity AS rls_enabled,
  s.n_live_tup AS row_count
FROM pg_tables t
JOIN pg_class c ON c.relname = t.tablename
JOIN pg_stat_user_tables s ON s.relname = t.tablename
WHERE t.schemaname = 'public'
ORDER BY s.n_live_tup DESC;

-- Profile trigger state
SELECT tgname FROM pg_trigger WHERE tgname = 'on_auth_user_created';

-- Any tables with no RLS policies
SELECT c.relname FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind = 'r'
AND c.relrowsecurity = true
AND NOT EXISTS (
  SELECT 1 FROM pg_policies p WHERE p.tablename = c.relname
);
```

### Step 4 — Check Memory MCP for Previous Sessions

```
search_nodes: "[project folder name]"
```

If results found → summarize previous session findings in one paragraph.
If no results → "First session on this project."

### Step 5 — Check Learned Patterns for Relevance

Read `memory-bank/learned-patterns.md`.
Find any MISTAKE or PATTERN entries that match this project type.
List top 3 most relevant.

### Step 6 — Generate the Project Briefing

Output this exact format:

```
╔══════════════════════════════════════════════════════════════╗
║              PROJECT BRIEFING — [PROJECT NAME]               ║
╚══════════════════════════════════════════════════════════════╝

📱 WHAT THIS IS
[One sentence from PRD.md]
Type: [A/B/C/D/E/F] — [SaaS/E-commerce/AI/Booking/Lead Gen/Blog]

👤 USER REPORT
[What's broken according to the user]

🗄️ LIVE DATABASE STATE
Tables: [list with row counts]
RLS: [X tables enabled, Y disabled]
Profile trigger: [exists ✅ / missing ❌]
Tables with RLS but no policies: [list or "none ✅"]

📚 PREVIOUS SESSION CONTEXT
[From memory MCP or "First session"]

⚠️ PATTERNS TO WATCH (from learned-patterns.md)
1. [Most relevant mistake to avoid]
2. [Second most relevant]
3. [Third most relevant]

🎯 RECOMMENDED STARTING POINT
Based on the above: [specific first action]
Suggested command: [/fix-auth / /fix-database / /audit-codebase / etc.]

══════════════════════════════════════════════════════════════
```

### Step 7 — Ask one confirming question

After the briefing:
"Does this match your understanding of the project? Any corrections before I start?"

Wait for confirmation. Then proceed.

---

## Why This Matters

Without /load-context:
```
Session 1: You explain the project → Cursor fixes something → session ends
Session 2: Cursor has forgotten everything → you explain again → repeat forever
```

With /load-context:
```
Session 1: /load-context reads everything automatically → full briefing in 30 seconds
Session 2: /load-context again → picks up from memory + learned patterns
Session 50: Cursor walks in knowing the full history of every fix on this project
```

The briefing replaces 10 minutes of re-explaining context at the start of every session.
