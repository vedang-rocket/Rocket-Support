# Purpose: Autonomous TypeScript error elimination loop — runs until tsc exits 0

## Usage
/test-fix-loop
Runs without interruption until all TypeScript errors are resolved or a blocker is hit.

## Scope lock
I will ONLY fix TypeScript type errors. I will NOT:
- Change function signatures to fix type errors — I fix the types to match the signature
- Modify files that have zero TypeScript errors
- Add `any` as a fix — use `unknown` and narrow, or use proper types
- Suppress errors with `@ts-ignore` or `// eslint-disable`
- Touch test files unless the error is in a test file

---

## Execution sequence

**Step 1 — Baseline capture**
```bash
npx tsc --noEmit 2>&1 | tee /tmp/tsc-baseline.txt
```
Count total errors. Report: `Found N TypeScript errors across M files.`

If 0 errors: report "No TypeScript errors found. Nothing to fix." and stop.

**Step 2 — Prioritize by file**
Group errors by file. Fix files in this order:
1. `lib/` files first — fixing a shared utility fixes downstream errors
2. `app/api/` route handlers
3. `app/(protected)/` pages
4. `components/` files last

**Step 3 — Fix loop (per file)**
For each file with errors:
1. Read the file and all its error messages
2. Fix only the type errors — smallest change that resolves each error
3. Run `npx tsc --noEmit --skipLibCheck 2>&1 | grep [filename]` to verify no regressions in that file
4. Report: `Fixed [filename]: [list of errors resolved]`
5. Move to next file

**Step 4 — After every 3 files**
Stop and report:
- Files fixed and errors resolved
- Files remaining
- Any assumptions made
Wait for "continue" before proceeding.

**Step 5 — Final verification**
```bash
npx tsc --noEmit
```
Expected: exit code 0, zero errors.

---

## Common TypeScript fixes in Rocket projects

```typescript
// Error: Type 'X | null' not assignable to type 'X'
// Fix: add null check
if (!data) return null
// or: data ?? defaultValue

// Error: Property 'x' does not exist on type 'never'  
// Fix: type the Supabase response with generics
const { data } = await supabase.from('table').select<'*', YourType>('*')

// Error: Object is possibly 'undefined'
// Fix: optional chaining + null check
const value = obj?.property ?? fallback

// Error: Type 'string | undefined' not assignable to 'string'
// Fix: assert or provide fallback
const key = process.env.KEY!  // when you know it's set
// or: const key = process.env.KEY ?? ''

// Error: Argument of type 'X' not assignable to parameter of type 'Y'
// Fix: check the expected type, don't cast — add proper type annotation

// Error: await cookies() in Next.js 15
// Fix: const cookieStore = await cookies()  (not: cookies())
```

---

## Stop conditions — report and wait for instruction

Stop immediately and report if:
- Fixing the error requires changing a function signature (callers would break)
- The error is in a `.d.ts` declaration file (do not edit these)
- The same error reappears after fixing (circular type dependency — needs design decision)
- A fix introduces a new error in a different file that wasn't there before

**Report format for blockers:**
```
BLOCKER in [filename]:[line]
Error: [exact error message]
Why I'm stopping: [one sentence]
Options: 
  A) [approach 1 and its tradeoff]
  B) [approach 2 and its tradeoff]
Your decision?
```

---

## Final report format
```
TypeScript fix complete.
Started with: N errors in M files
Resolved: N errors in M files  
Files changed: [list]
Remaining errors: [list or "none"]
tsc exit code: 0 ✅ / [N errors remain] ❌
```
