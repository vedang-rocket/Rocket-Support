---
description: Generate a complete Next.js feature from a plain-text description or image URL. Produces a server component, client components, server actions, a DB migration, and a test stub — all wired to your existing component library.
---

# /generate-feature

Generate a production-ready feature from a description.

## Usage

```
/generate-feature A user profile page showing avatar, name, bio, and edit button

/generate-feature An order history table with pagination and status filter

/generate-feature https://your-figma-export.png
```

## What you get

- **Server component** — fetches data from Supabase, handles auth redirect
- **Client component(s)** — interactive UI with Tailwind, reuses your existing components from `components.json`
- **Server actions** — mutations with Zod validation and `revalidatePath`
- **DB migration** — timestamped SQL with RLS enabled and policies
- **Test stub** — Vitest/Playwright stubs for render, auth, and data tests

## How it works

1. The `feature-generator` agent reads your project's existing pages, `components.json`, and conventions
2. Proposes a file plan for your approval
3. Generates all files with correct patterns (getUser, force-dynamic, await params)
4. Writes files directly to the correct paths

## Tips

- The more specific the description, the better the output
- If you have a Figma export URL, include it — the agent will describe the layout then generate
- After generation: `supabase db push` then `npm test` to verify the stub passes
- The generator reuses components in `components.json` — run `/index-components` first to ensure it's current

## Related

- `/index-components` — refresh the component library index
- `/generate-tests` — generate tests for an existing feature
- `/risk-scan` — check the generated files for risk patterns
