# Purpose: Chain-of-thought root cause analysis for any error in a Rocket.new project

This is a Rocket.new Next.js App Router project using Supabase `@supabase/ssr`.

## Usage
Paste the exact error, then type /debug-error

## Required input — provide all of these
```
Error message: [paste VERBATIM — never paraphrase]
File: [exact path where error occurs]
Trigger: [exactly what action causes this error]
Frequency: [always / sometimes / after X happens]
Relevant files: @[file1] @[file2] @[file3]
```

## My diagnostic process

**Step 1 — Scope lock declaration**
Before I touch anything, I will declare:
- Files I will modify: [list]  
- Files I will NOT touch: [explicit list]
- What I am protecting: [functions/behavior to preserve]

**Step 2 — Reproduce → Isolate → Constrain**

Reproduce: Can I trace exactly how to trigger this error?
Isolate: At which exact point in the call chain does the failure occur?
Constrain: What is the minimal code change needed?

**Step 3 — Chain-of-thought trace (required before any fix)**

I will trace the call chain step by step:
```
1. Entry point: [what triggers the code]
2. [function/component] calls [next thing]
3. [next thing] expects [X] but receives [Y]
4. Failure occurs at: [exact line/function]
5. Root cause: [one sentence]
```
I will NOT propose a fix until this trace is complete.

**Step 4 — Verify the fix hypothesis**
Before writing code:
"The fix is to change [X] in [file] because [reason].
This will not affect [protected behavior] because [reason].
Possible side effects: [list or 'none']."

**Step 5 — Apply minimal fix**
Change only what's needed. Show complete diff. Explain each line.

## Common Rocket error patterns I check first
- `getSession()` in server code → replace with `getUser()`
- `request.json()` in Stripe webhook → replace with `request.text()`
- Browser Supabase client in Server Component → swap to `lib/supabase/server.ts`
- `middleware.ts` inside `/app` → move to project root
- `cookies()` not awaited → add `await` (Next.js 15)
- RLS + no policies → queries return `[]` silently

## Hard constraints
- Fix only the identified root cause — nothing else
- Never "improve" code that wasn't part of the bug
- If the fix requires touching a second file, ask first
- If the fix is unclear, say so and ask for more context — don't guess

## Output format
```
Root cause: [one sentence]
Affected file: [path]
Protected files: [list]
Fix: [description of change]
---
[diff showing exactly what changes]
---
Verify with: [test steps or verification command]
```
