# Purpose: Save current session context to memory-bank/ for the next session

## Usage
/update-memory
Run this at the end of any session where you fixed something or made a decision.

---

## What I Will Do

I will update the following files based on everything that happened in this conversation:

### Step 0 — Check if /reflect should run first

If this session had significant learning opportunities (mistakes corrected, new patterns found),
suggest running `/reflect` or `/learn-eval` BEFORE `/update-memory` to capture instincts.

`/update-memory` = saves WHAT was done (fixes, decisions, context)
`/reflect` = saves WHAT WAS LEARNED (patterns, mistakes, instincts)

Both are valuable. Run `/reflect` first if the session was learning-rich.

### Step 1 — Update `memory-bank/fixes-applied.md`

For each significant fix or change made in this session, I will prepend an entry:

```markdown
### [today's date] — [short title]
**Problem**: [what was broken]
**Root cause**: [why it was broken]
**Files changed**: [list]
**Fix**: [what was done]
**Verified**: [yes/no — how]
**Watch out**: [gotchas for next session]
```

### Step 2 — Update `memory-bank/active-issues.md`

- Mark any resolved issues as `[x]` with a one-line fix summary
- Add any NEW issues discovered during this session
- Add a "Notes for Next Session" entry with current stopping point

### Step 3 — Update `memory-bank/patterns-discovered.md`

If this session revealed anything specific to THIS codebase — non-standard column names, unusual component structure, custom patterns — add it here.

### Step 4 — Update `memory-bank/project-context.md`

If the project's state changed significantly (new tables, deployed to production, custom domain added), update the relevant sections.

---

## Output Format

After updating all 4 files, I will output a brief summary:

```
Memory Bank Updated ✅

Fixes logged: [count]
Issues resolved: [count]
Issues remaining: [count]
New patterns documented: [count or "none"]

Next session should start by reading:
- memory-bank/active-issues.md — [count] open issues
- memory-bank/patterns-discovered.md — [any new entries]
```

---

## Constraint
I will only write facts from this conversation.
I will not invent context or make assumptions about things not discussed.
