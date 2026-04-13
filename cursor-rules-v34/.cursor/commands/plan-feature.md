# Purpose: Generate a complete plan.md for a feature BEFORE writing any code

## Usage
/plan-feature [feature name]
Example: /plan-feature team workspaces
Example: /plan-feature PDF export
Example: /plan-feature admin dashboard

## CHECKPOINT PROTOCOL

After every 3 files changed, STOP and output:
- Files changed so far + one-line summary of each change
- Current understanding of remaining work
- Any assumptions made that need your verification

Do not proceed until you explicitly say "continue".

Rationale: Accuracy degrades ~2% per reasoning step. At 20 steps, failure rate compounds to ~40%. Checkpoints reset context and keep changes reviewable.

---


## Rule: No code until plan is confirmed
This command outputs ONLY a plan. Zero implementation code.
Implementation starts only after you confirm the plan with "looks good" or request changes.

---

## My planning process

**Step 1 — Research phase (I do this before writing the plan)**

I will ask: what existing code is relevant?
- What tables already exist? (check supabase/migrations/)
- What auth patterns are already implemented?
- What components can be reused?
- What would this feature break if done wrong?

Provide these files if helpful: @supabase/migrations/ @lib/types.ts @app/(protected)/

**Step 2 — Output plan.md**

I will produce a structured plan with these exact sections:

```markdown
# Feature Plan: [name]

## Summary
[2-3 sentences: what this does and why]

## TypeScript Types
[All new types needed — complete definitions]

## Database Changes
### New tables
[CREATE TABLE SQL with all constraints]
### New indexes
[CREATE INDEX SQL]  
### RLS policies
[All CRUD policies for each new table]
### Migrations to existing tables (if any)
[ALTER TABLE SQL]

## Files to Create
[full path] — [one-line purpose]
[full path] — [one-line purpose]

## Files to Modify
[full path] — [exactly what changes and why]

## Implementation Phases
### Phase 1: Data layer
[What gets built — no UI yet]
### Phase 2: API layer
[Route handlers]
### Phase 3: UI layer
[Components and pages]
### Phase 4: Integration and protection
[Auth, edge cases, testing]

## Protected (must not change)
[Existing files/behavior that must be preserved]

## Risks and open questions
[What could go wrong, what needs clarification]

## Estimated complexity
[Low / Medium / High — and why]
```

**Step 3 — Wait for confirmation**

After outputting the plan, I will say:
"Review this plan. Reply 'confirmed' to start Phase 1, or tell me what to change."

I will not write any code until I receive confirmation.

## Hard constraints in the planning phase
- Every new table must have RLS — if I omit it, flag it as a risk
- Every new table referencing auth.users needs `ON DELETE CASCADE`
- Every new table needs an index on `user_id`
- Protected routes must use server-side `getUser()` — never client-side only
- Plan must explicitly list what existing code will NOT change

## What makes a good plan
- Specific enough that implementation is deterministic (no guessing)
- Small enough that each phase is reviewable independently
- Explicit about ripple effects (what else this change touches)
- Honest about uncertainty (asks questions instead of guessing)
