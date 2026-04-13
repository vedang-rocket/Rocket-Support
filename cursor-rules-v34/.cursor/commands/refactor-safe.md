# Purpose: Safe refactor with explicit scope-lock — zero breaking changes to callers

This is a Rocket.new Next.js App Router project using Supabase `@supabase/ssr`.

## CHECKPOINT PROTOCOL

After every 3 files changed, STOP and output:
- Files changed so far + one-line summary of each change
- Current understanding of remaining work
- Any assumptions made that need your verification

Do not proceed until you explicitly say "continue".

Rationale: Accuracy degrades ~2% per reasoning step. At 20 steps, failure rate compounds to ~40%. Checkpoints reset context and keep changes reviewable.

---


## Usage
/refactor-safe [what to refactor]
Example: /refactor-safe the createClient function in lib/supabase/server.ts
Example: /refactor-safe the useAuthUser hook to remove the useEffect

## Required input
```
Target: [exact file path and function/component name]
Goal: [what it should look like after — one sentence]
Relevant callers: @[file that imports this] @[another caller]
```

## My refactoring protocol — I follow this every time

**Step 1 — Audit callers before touching anything**
```bash
# Find everything that imports from the target file
grep -rn "from '@/[target-path]'" ./app ./components ./lib
grep -rn "from '../[target-path]'" ./app ./components ./lib
```
I will list every caller. I will NOT touch them.

**Step 2 — Explicit preservation contract**

I will preserve EXACTLY:
- Export name(s): [list all exports that must stay the same]
- Function signature(s): params, return type
- Error handling behavior
- All external-facing behavior

I will NOT:
- Rename any export
- Change any function signature
- Modify any file that imports from the target
- Add new functionality (separate PR/task for that)
- Reformat code that isn't part of the change

**Step 3 — Show the change in isolation**

I will show ONLY the target file diff first.
You confirm it looks correct before I do anything else.
Then I check all callers still compile correctly.

**Step 4 — TypeScript verification**
```bash
npx tsc --noEmit
```
No new TypeScript errors = refactor is safe.

## Hard constraints
- One file change at a time, confirmed before continuing
- If callers need updates due to the refactor, I will ask — not auto-update them
- If preserving the signature is impossible and callers MUST change, I will stop and report this before proceeding — never silently update callers
- Zero behavior changes — if the refactor accidentally changes behavior, I will flag it

## Output format
```
Callers found: [list with file paths]
Preservation contract:
  - Export: [name] (unchanged)
  - Signature: [signature] (unchanged)
  - Behavior: [description] (unchanged)

Change to [target file]:
[diff]

Callers requiring updates: [none / list]
TypeScript check: [pending — run after confirmation]
```
