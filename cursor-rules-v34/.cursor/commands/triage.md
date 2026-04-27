# /triage — Plain English Problem Solver

## What this does
Takes any plain-English description of a problem, figures out what's wrong, and fixes it.
No technical knowledge required. Just describe what's broken.

## How to use
```
/triage my login isn't working
/triage the dashboard shows nothing after I sign in
/triage I saved data but it keeps disappearing
/triage the checkout button does nothing
/triage my Netlify build failed
/triage the whole app just stopped working
```

---

## STEP 1 — Classify the problem

Read the user's description and map it to one of these categories:

| What they said | Category | First action |
|---|---|---|
| login / sign in / log out / account / session / password / Google login | AUTH | → Step 2A |
| nothing loading / blank / empty / data gone / can't see anything | DATA | → Step 2B |
| save not working / changes lost / submit does nothing | SYNC | → Step 2C |
| payment / checkout / Stripe / subscription / billing / webhook | PAYMENTS | → Step 2D |
| preview / scripts blocked / analytics / GTM / CSP | PREVIEW | → Step 2E |
| build failed / deploy failed / Netlify / works locally not prod | DEPLOY | → Step 2F |
| slow / hangs / takes forever | PERFORMANCE | → Step 2G |
| error message pasted / not sure / general / just broken | UNKNOWN | → Step 2H |

If unclear, go to Step 2H (audit everything first).

---

## STEP 2A — AUTH (Login / Account problems)

**Say this first:**
> "Sounds like a login or account problem. Let me check what's set up in your project."

**Run these checks silently (don't ask the user to run them):**
```bash
# Is middleware in the right place?
ls middleware.ts 2>/dev/null || ls src/middleware.ts 2>/dev/null || echo "⚠️ NO MIDDLEWARE FILE FOUND"

# Does it use the old broken pattern?
grep -rn "getSession()" app/ src/ lib/ 2>/dev/null | grep -v ".next" | head -5

# Is the login callback route there?
ls app/auth/callback/route.ts 2>/dev/null || ls src/app/auth/callback/route.ts 2>/dev/null || echo "⚠️ NO CALLBACK ROUTE"

# Deprecated package?
grep "auth-helpers-nextjs" package.json 2>/dev/null && echo "⚠️ DEPRECATED PACKAGE"
```

**Map findings to plain-language explanations:**
- No middleware file → "The file that keeps you logged in between pages is missing"
- `getSession()` found → "A function that has a known bug is being used to check your login"
- No callback route → "The page that completes your login after clicking a link is missing"
- Deprecated package → "An old version of the login library is installed"

**Apply the fix using the `/fix-auth` workflow.**

**Explain the fix like this:**
> "Here's what was wrong: [plain English]. I fixed it by [plain English description of change].
> To check it works: go to your login page and try signing in."

---

## STEP 2B — DATA (Nothing loading / blank state)

**Say this first:**
> "Sounds like your data isn't appearing. Let me figure out where it's getting stuck."

**Identify which data pattern this project uses:**
```bash
# Client-side data fetching (CRM / Dashboard apps)?
ls src/contexts/AuthContext.tsx 2>/dev/null || ls src/hooks/useCRM.ts 2>/dev/null

# Server-side data fetching?
grep -rn "createClient" app/ src/app/ 2>/dev/null | grep -v ".next" | head -5
```

- If `AuthContext.tsx` or `useCRM.ts` found → this is a dashboard app → run `/fix-data-sync`
- Otherwise → run `/fix-database`

**Translate findings:**
- RLS blocking → "Your database has a security rule that's preventing you from reading the data"
- null user at fetch time → "The page is trying to load your data before confirming you're logged in"
- Wrong Supabase client → "The wrong database connection is being used on this page"
- Table doesn't exist → "The database table hasn't been set up yet"
- Project paused → "Your database was switched off because it wasn't used for a while — it needs to be restarted"

---

## STEP 2C — SYNC (Data not saving / changes lost)

**Say this first:**
> "Sounds like saves or changes aren't sticking. Let me trace where they're getting lost."

**Run the `/fix-data-sync` workflow.**

**Translate findings:**
- No user guard → "The save is trying to run before confirming you're logged in"
- camelCase mismatch → "There's a naming mismatch between your app and your database"
- Batch failing → "When saving lots of records at once, some are silently failing"
- Optimistic update drift → "The page shows a fake 'saved' state but doesn't actually confirm with the database"

---

## STEP 2D — PAYMENTS (Stripe / Checkout broken)

**Say this first:**
> "Sounds like a payment issue. Let me check your Stripe setup."

**Run these checks silently:**
```bash
# Is the webhook using the right method?
grep -rn "request.json()" app/api/webhooks/ src/app/api/webhooks/ 2>/dev/null | head -5

# Is the webhook route there?
ls app/api/webhooks/stripe/route.ts 2>/dev/null || ls src/app/api/webhooks/stripe/route.ts 2>/dev/null || echo "⚠️ NO WEBHOOK ROUTE"

# Is it using test keys in production?
grep "STRIPE_SECRET_KEY" .env.local 2>/dev/null | grep "sk_test" | head -1
```

**Translate findings:**
- `request.json()` in webhook → "There's a small but critical bug in how payments are received — one word needs to change"
- No webhook route → "The page that receives payment confirmations from Stripe is missing"
- Test keys → "Your app is using test payment settings — real payments won't work until you switch to live keys"

**Apply the fix using the `/fix-stripe` workflow.**

---

## STEP 2E — PREVIEW (Preview blank / scripts blocked)

**Say this first:**
> "Sounds like scripts or the preview aren't loading. Let me check your security settings."

**Run the `/preview-error` workflow.**

**Translate findings:**
- CSP missing → "Your app is missing a security setting that tells the browser which scripts are allowed to run"
- Missing domains → "The preview or analytics scripts aren't on the allowed list"

---

## STEP 2F — DEPLOY (Build/deploy failing)

**Say this first:**
> "Sounds like the deployment failed. Let me find the first error in the build log."

**Run the `/fix-deployment` workflow.**

**Translate findings:**
- TypeScript error → "There's a code mistake that's stopping the build — this needs to be fixed before deploying"
- Missing env var → "A secret setting is missing from your Netlify dashboard — it exists locally but wasn't added to the live environment"
- Module not found → "A package your project needs isn't in the right section of your package list"
- Works locally not prod → "Almost always: a secret setting is missing in Netlify, OR your database URLs aren't configured for the production domain"

---

## STEP 2G — PERFORMANCE (App is slow)

**Say this first:**
> "Sounds like something is making the app slow. Let me find the bottleneck."

**Run the `/fix-performance` workflow.**

**Translate findings:**
- Missing index → "Your database is scanning every row to find data instead of using a shortcut — adding an index is like adding a book's index"
- N+1 queries → "The app is making one database call per item in a list instead of one call for the whole list"
- Uncached images → "Large images are being loaded without optimization"

---

## STEP 2H — UNKNOWN (Not sure what's wrong)

**Say this first:**
> "Let me run a full health check on your project and tell you what I find."

**Run `/audit-codebase` and report ALL findings in plain language.**

Use the jargon translation table from `rocket-natural-language.mdc`.
Never output raw grep results, TypeScript errors, or SQL — translate everything.

**Example output:**
> ✅ Your database is set up correctly — all tables exist and access rules are in place.
> ⚠️ Found a login bug: a function with a known security issue is being used in 2 files. I'll fix both.
> ✅ Your payment setup looks correct.
> ⚠️ Two files are missing the header that helps the AI understand what they do.
>
> I'll fix the login issue first since that's the most likely cause of your problem.

---

## OUTPUT FORMAT (always use this)

```
🔍 What's happening:
[One or two plain sentences. No acronyms. No code references.]

🛠 What I'll change:
[Plain English — "I'll update the login file to use the correct function"]

📁 Files I'll touch: [filename1, filename2]
📁 Files I won't touch: [everything else]

[Apply the fix]

✅ To check it's fixed:
[Simple human steps — "Open your app, go to the login page, and try signing in"]

💬 Why this works:
[One plain sentence explaining the root cause and why the fix solves it]
```

---

## RULES FOR THIS COMMAND

- Never tell the user to run a command themselves — run it yourself and translate the output
- Never output raw error messages — explain what they mean in plain language  
- Never use: middleware, RLS, SSR, hydration, token, webhook, env var, migration, CORS, anon key, getUser(), cookies(), auth callback — use the plain-language equivalents from `rocket-natural-language.mdc`
- If the first fix doesn't resolve the issue, automatically escalate to `/audit-codebase`
- Keep the user informed at each step: "Checking your login setup..." → "Found the issue..." → "Applying the fix..." → "Done — here's how to verify"
