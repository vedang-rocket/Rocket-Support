# Purpose: Add file headers to all files missing them — improves Cursor's codebase understanding before any fixing begins

Run this on messy projects BEFORE running any fix commands.
File headers are not documentation — they are embedding index signals.
Files without headers get misidentified by Cursor's semantic search, causing edits to wrong files.

## Why This Matters
Cursor uses vector embeddings to find relevant files. Without a clear purpose declaration in the first few lines, the model guesses what a file does based on its code. That guess is often wrong. Adding headers takes 2 minutes and improves every subsequent agent action in the session.

## SCOPE
I will ONLY add JSDoc comment headers to files that are missing them.
I will NOT change any logic, imports, exports, or existing code.
I will process files one at a time and show each header before writing it.

## CHECKPOINT PROTOCOL
After every 5 files, stop and output:
- Files processed so far
- Any files I'm uncertain about (will ask before writing)

---

## What I Will Add to Each File

```typescript
/**
 * @file [filename]
 * @purpose [One sentence: what this file does]
 * @exports [Named exports — functions, components, types]
 * @dependencies [Key imports this file relies on]
 * @do-not-modify [What must NOT be changed here — e.g. "cookie handling logic"]
 */
```

---

## Files to Process (in this order)

**Priority 1 — Files Cursor most often confuses:**
```bash
# Find all .ts and .tsx files missing a header
find ./lib ./app/api ./middleware.ts -name "*.ts" -o -name "*.tsx" 2>/dev/null | while read f; do
  if ! grep -qE "@file|@purpose|@module" "$f" 2>/dev/null; then
    echo "$f"
  fi
done
```

**Priority 2 — Components:**
```bash
find ./components -name "*.tsx" 2>/dev/null | while read f; do
  if ! grep -qE "@file|@purpose" "$f" 2>/dev/null; then
    echo "$f"
  fi
done
```

---

## Headers I Will Write (Examples)

```typescript
// lib/supabase/server.ts
/**
 * @file supabase/server.ts
 * @purpose Server-side Supabase client for Next.js App Router
 * @exports createClient() — async factory, returns typed SupabaseClient
 * @dependencies @supabase/ssr, next/headers
 * @do-not-modify Cookie handling logic — changing this breaks SSR session persistence
 */

// lib/supabase/client.ts
/**
 * @file supabase/client.ts
 * @purpose Browser-side Supabase client for use client components only
 * @exports createClient() — returns browser SupabaseClient
 * @dependencies @supabase/ssr
 * @do-not-modify Do NOT import this in Server Components — use server.ts instead
 */

// middleware.ts
/**
 * @file middleware.ts (ROOT LEVEL)
 * @purpose Refresh Supabase auth session on every request
 * @exports middleware, config
 * @dependencies lib/supabase/middleware → updateSession()
 * @do-not-modify Matcher pattern and updateSession call — removing breaks auth refresh
 */

// app/auth/callback/route.ts
/**
 * @file auth/callback/route.ts
 * @purpose Handle OAuth and magic link code exchange after Supabase redirect
 * @exports GET handler
 * @dependencies lib/supabase/server, next/server
 * @do-not-modify exchangeCodeForSession call — removing this breaks all OAuth flows
 */

// app/api/webhooks/stripe/route.ts
/**
 * @file api/webhooks/stripe/route.ts
 * @purpose Handle Stripe payment events and sync subscription status to Supabase
 * @exports POST handler
 * @dependencies stripe, lib/supabase/server
 * @do-not-modify request.text() body parsing — request.json() breaks Stripe signature verification
 */
```

---

## Hard Constraints
- ONLY add the header block — never change anything else in the file
- If a file already has any kind of header comment, skip it
- If unsure what a file does, read it first, then write a precise header — never write a vague one
- Headers must be accurate — a wrong header is worse than no header

## Output format per file
```
Adding header to: [filepath]
Header:
[show the header]
Writing... ✅
```

Report total at end: "Added headers to X files. Skipped Y files (already had headers)."
