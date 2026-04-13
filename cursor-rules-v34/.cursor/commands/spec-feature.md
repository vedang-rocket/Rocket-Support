# Purpose: Write and lock a feature specification BEFORE plan.md or any code is written

The most expensive bugs are the ones built correctly to the wrong specification.
This command exists to catch wrong direction at the spec layer — where it costs nothing to fix —
instead of at the code layer where it costs hours.

## Rule: Zero code until spec is LOCKED
This command outputs a spec document only.
Plan.md comes after. Code comes after plan.md. Not before.

## Usage
/spec-feature [feature name]

Example: /spec-feature user notifications
Example: /spec-feature team workspace invitations
Example: /spec-feature subscription upgrade flow

---

## My Specification Process

### Step 1 — Ask clarifying questions FIRST (before writing anything)

I will ask these questions and wait for answers before writing the spec:

```
1. What problem does this solve for the user?
   (not "what should it do" — WHY does the user need it)

2. What does SUCCESS look like?
   (describe the user experience when the feature works perfectly)

3. What does FAILURE look like?
   (what happens if it breaks — what is the worst case)

4. Who can use this feature?
   (all users / authenticated users only / specific roles / admins)

5. What existing features does this touch?
   (auth, payments, specific tables, specific pages)

6. What must NOT change?
   (existing behaviour that must be preserved exactly)

7. What are the edge cases?
   (empty state, single item, large dataset, unauthenticated access attempt)
```

I will NOT write the spec until these are answered.

---

### Step 2 — Write the locked specification

```markdown
# Feature Specification: [name]
Version: 1.0 | Status: DRAFT → LOCKED
Date: [today]

## Problem Statement
[Why this exists — the user pain being solved]

## Success Criteria (Acceptance Tests)
These are the exact conditions that must be true for the feature to be considered complete:
- [ ] [Specific, testable condition 1]
- [ ] [Specific, testable condition 2]
- [ ] [Specific, testable condition 3]
(Each criterion must be binary — either true or false, no ambiguity)

## User Stories
As a [user type], I want to [action] so that [outcome].
(Write one per distinct user interaction)

## Scope: What This Feature IS
[Precise description of what is included]

## Scope: What This Feature IS NOT
[Explicit list of what is excluded — prevents scope creep]

## Access Control
- Who can access: [all / authenticated / role-restricted]
- What data is visible: [own data only / shared / public]
- What actions are permitted: [read / write / delete]

## Data Requirements
- New data needed: [yes / no — describe if yes]
- Existing data affected: [tables/columns that change]
- Data that must NOT change: [protected fields]

## Integration Points
- Auth: [how auth is involved]
- Payments: [Stripe involvement — yes/no/how]
- Email: [email sent — yes/no/when]
- External APIs: [any third-party calls]

## Error States
- [Error condition] → [what the user sees]
- [Error condition] → [what the user sees]

## Edge Cases
- Empty state: [what shows when there's no data]
- Single item: [any special handling]
- Concurrent users: [any race conditions]
- Unauthenticated access attempt: [what happens]

## Performance Requirements
- Expected data volume: [rows/files/users]
- Acceptable load time: [< X seconds]
- Real-time requirements: [yes/no]

## What Must NOT Change
[List existing features/behaviour that must be preserved exactly]

## Open Questions
[Anything unclear that needs a decision before implementation]

---
SPEC STATUS: DRAFT
```

---

### Step 3 — Spec review

After outputting the spec, I will say:

```
Review this specification carefully.

Before approving, confirm:
□ Success criteria are specific and testable (not vague)
□ Scope boundaries are clear — what's IN and what's OUT
□ "Must NOT change" list is complete
□ All edge cases are handled
□ No open questions remain

Reply "SPEC LOCKED" to proceed to /plan-feature.
Reply with changes to revise the spec.

Do NOT proceed to plan.md until you say "SPEC LOCKED".
```

---

## Hard Constraints
- Never skip the clarifying questions — vague specs produce wrong implementations
- Never proceed to plan.md without explicit "SPEC LOCKED" confirmation
- Acceptance criteria must be binary (testable) — never vague ("works well", "looks good")
- The "must NOT change" section is not optional — scope creep starts when this is empty
- One feature per spec — if the feature naturally splits into two, write two specs
