---
description: Refresh the digital twin style profile by analysing your 20 most recently edited files. Updates memory-bank/style-profile.json which powers the pair-programmer suggestions in the afterFileEdit hook.
---

# /learn-style

Analyse your recent code to update the pair-programmer style profile.

## What it does

1. Reads your 100 most recently edited files from `.cursor/agent-log.txt`
2. Analyses the 20 most recently modified `.ts`/`.tsx` files for coding patterns
3. Identifies preferences: arrow functions, error boundaries, auth checks, Zod usage
4. Notes recurring mistakes from `memory-bank/fixes-applied.md`
5. Writes the profile to `memory-bank/style-profile.json`

## Activating pair-programmer suggestions

After running `/learn-style`, set your hook profile to strict:

```bash
export ECC_HOOK_PROFILE=strict
```

Then the `afterFileEdit` hook will compare each edit against your style profile and
warn you if you're deviating from your own patterns.

## Example output

```
Style profile updated from 18 files.

Patterns detected:
  ✅ Always uses arrow functions
  ✅ Always calls getUser() in routes
  ⚠️  Sometimes forgets ErrorBoundary on pages (seen in 3/18 files)
  ⚠️  Recurring mistake: await params not used in 2 recent page components

The pair-programmer hook will now flag these when you edit .ts/.tsx files.
```
