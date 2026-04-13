# Purpose: Convert a discovered mistake or pattern into a properly formatted rule block — ready to paste into rocket-cursor-behavior.mdc

Every mistake Cursor makes is a future prevention if captured immediately.
The friction of formatting stops most developers from doing this. This command removes that friction.

## Usage
/capture-convention [describe what went wrong or what pattern was discovered]

Examples:
/capture-convention Cursor used createClient from client.ts in a Server Action
/capture-convention Cursor added a console.log with the user object including sensitive fields
/capture-convention Cursor generated a new table without an index on user_id
/capture-convention Cursor used .single() instead of .maybeSingle() on a query that might return null

---

## What I Will Do

1. Understand what happened (ask one clarifying question if needed)
2. Identify the root pattern (not just the symptom)
3. Generate a properly formatted rule block
4. Tell you exactly which file to add it to and where

---

## Output Format

I will produce a ready-to-paste MDC rule block in this exact format:

```markdown
### ❌ NEVER [short description of forbidden pattern]
**Why**: [one sentence — the consequence of doing this]
**Context**: [when this applies — Server Component / webhook / etc.]

```typescript
// ❌ FORBIDDEN — [why it's wrong]
[exact code pattern to never write]

// ✅ ALWAYS — [why this is correct]
[exact correct code pattern]
```

**Add to**: `rocket-cursor-behavior.mdc` → HARD FORBIDDEN PATTERNS section
```

---

## Examples of What This Produces

**Input**: "Cursor used client.ts in a Server Action"

**Output**:
```markdown
### ❌ NEVER import browser Supabase client in Server Actions
**Why**: Server Actions run server-side — the browser client cannot access server-side cookies, causing silent auth failures.
**Context**: Any file with `'use server'` directive

```typescript
// ❌ FORBIDDEN in Server Actions
import { createClient } from '@/lib/supabase/client'  // browser client

// ✅ ALWAYS in Server Actions
import { createClient } from '@/lib/supabase/server'   // server client
```

**Add to**: `rocket-cursor-behavior.mdc` → HARD FORBIDDEN PATTERNS section (after rule #3)
```

---

**Input**: "Cursor generated a new table without an index on user_id"

**Output**:
```markdown
### ❌ NEVER create a table that queries by user_id without an index
**Why**: Without an index, every query scans the entire table — catastrophic at scale.
**Context**: Any new Supabase table with a user_id column

```sql
-- ❌ FORBIDDEN — missing index causes full table scan
CREATE TABLE posts (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id),
  content TEXT
);

-- ✅ ALWAYS — index every foreign key you filter by
CREATE TABLE posts (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id UUID REFERENCES auth.users(id),
  content TEXT
);
CREATE INDEX posts_user_id_idx ON posts(user_id);
```

**Add to**: `rocket-cursor-behavior.mdc` → CODE STYLE RULES section
```

---

## Hard Constraints
- One rule per convention — never combine two patterns into one rule
- The ❌ example must be the exact pattern that just caused the problem
- The ✅ example must be immediately copy-pasteable
- Never write a vague rule ("always be careful with auth") — every rule must be specific and binary
- Always specify which file and which section to add it to
