# Purpose: Security and correctness review of the current diff before accepting any agent change

## Usage
/review-diff
Run this after an agent proposes changes, before you accept them.
Paste the diff or describe what was changed.


## ⚠️ KNOWN CURSOR BUGS — CHECK THESE FIRST (March 2026)

### Bug 1: Lazy Delete — Silent Code Destruction
Cursor sometimes replaces large code blocks with `// ... existing code ...` during refactors.
If you accept this diff, that code is **permanently deleted**.

**Scan the diff right now:**
```bash
grep -r "\.\.\. existing code\|// \.\.\. rest\|# \.\.\. existing\|<!-- \.\.\. -->" .
```
If ANY result found → **REJECT IMMEDIATELY**. Never accept a diff containing this pattern.

### Bug 2: Zombie Revert — Changes Silently Disappear
After applying a fix, Cursor sometimes silently reverts your changes due to:
- Agent Review Tab conflict (most common)
- Cloud sync conflict
- Format On Save conflict

**Prevention checklist before accepting any diff:**
- [ ] Close the Agent Review Tab (X button in the review panel)
- [ ] Disable Format On Save: Settings → Editor → Format On Save → OFF
- [ ] If using iCloud/Dropbox sync: exclude project folder from sync

**Verification after accepting:** run `git diff` to confirm changes actually persisted.
If the file looks unchanged after accepting → Zombie Revert occurred. Close Agent Review Tab and retry.

---

## My 9-point review checklist

I will evaluate every changed file against all 9 points.
For each point: ✅ pass / ❌ fail / ⚠️ needs discussion

---

**Point 1 — Scope creep**
Did the agent modify files that weren't in the original request?
- List every file changed
- Flag any file not explicitly mentioned in the task

**Point 2 — New dependencies**
Were any packages added to `package.json`?
- If yes: are they necessary? Are they maintained? Do they add attack surface?

**Point 3 — Auth patterns (critical)**
- Any `getSession()` in server-side code? → must be `getUser()`
- Any browser Supabase client in a Server Component? → must be server client
- Any new route without auth protection that should have it?
- Any weakening of existing auth checks?

**Point 4 — Stripe webhook safety**
- Any new Stripe webhook handler using `request.json()`? → must be `request.text()`
- Any change to existing webhook signature verification?

**Point 5 — RLS and data access**
- Any new table without RLS enabled?
- Any RLS policy change that could expose data to wrong users?
- Any query using service role key where anon key should be used?
- Any new table without policies (silent empty-result trap)?

**Point 6 — Secrets and environment variables**
- Any hardcoded secret, API key, or URL? → must be env var
- Any `NEXT_PUBLIC_` prefix on a secret that should be server-only?
- Any secret accidentally logged to console?

**Point 7 — Breaking changes to callers**
- Did any function signature change?
- Did any export name change?
- Did any component's required props change?
- Are all callers of modified functions still valid?

**Point 8 — Intent vs implementation**
Does the change actually solve what was asked?
- Re-read the original request
- Does the implementation match the intent or just match the literal words?
- Are there edge cases the implementation misses?

**Point 9 — TypeScript correctness**
```bash
npx tsc --noEmit
```
- Any new `any` types introduced?
- Any type assertions (`as X`) that could hide runtime errors?
- Any non-null assertions (`!`) on values that could actually be null?

---

## Verdict format

```
Scope: ✅ / ❌ [files changed beyond scope: list]
New deps: ✅ / ⚠️ [list any new packages]
Auth: ✅ / ❌ [issues found]
Stripe: ✅ / N/A [issues found]
RLS: ✅ / ❌ [issues found]
Secrets: ✅ / ❌ [issues found]
Breaking changes: ✅ / ❌ [what broke]
Intent match: ✅ / ⚠️ [gaps in implementation]
TypeScript: ✅ / ❌ [type errors]

DECISION: ACCEPT / REJECT / REQUEST CHANGES
Reason: [one sentence if reject or request changes]
```

---

## INTERACTIVE ROUTING (After Verdict)

After delivering the verdict, prompt for the next action:

```
If ACCEPT → reply "accept" and I will confirm the changes are safe to apply.

If REJECT → reply with one of:
  "revert and fix [issue]"   → I will revert the change and fix the specific problem
  "revert and retry"         → I will revert and re-run the original task with tighter constraints
  "revert only"              → You will handle the fix manually

If REQUEST CHANGES → I will describe exactly what needs to change and wait for "retry".

Waiting for your decision.
```

If any point is ❌: always recommend REJECT and describe the exact fix needed before re-running.
