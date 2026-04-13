# Purpose: Diagnose and fix Netlify deployment failures for Rocket.new Next.js projects

## Usage
/fix-deployment
Then paste the Netlify build log error (or describe what's broken).

## Step 1 — Read the build log first
If you haven't already: Netlify Dashboard → your site → Deploys → failed deploy → build log.
Find the FIRST red line. Everything after it is usually cascading failure.
Paste it here.

## Step 2 — Run local reproduction
```bash
# This replicates the Netlify build environment
npm run build
# If this fails locally → TS errors or missing deps (fix locally first)
# If this succeeds locally → env vars or Netlify config issue
```

## Step 3 — I will diagnose against these 8 failure patterns

**Pattern A — TypeScript errors**
Signs: `Type error:`, `TS2xxx:`, `error TS`
```bash
npx tsc --noEmit  # fix every error before redeploying
```

**Pattern B — Module not found**
Signs: `Cannot find module`, `Module not found`
```bash
grep -r "from 'missing-module'" ./app ./components ./lib
# Move from devDependencies to dependencies in package.json
```

**Pattern C — Missing environment variables**
Signs: app works locally, crashes/breaks in production
All `.env.local` variables must be added manually to:
Netlify Dashboard → Site Configuration → Environment Variables
After adding: trigger "Clear cache and deploy" (not just "Deploy")

**Pattern D — Next.js 15 async APIs**
Signs: `cookies() should be awaited`, `headers() should be awaited`
```typescript
const cookieStore = await cookies()   // ✅
const cookieStore = cookies()         // ❌
```

**Pattern E — Wrong API route location**
Signs: API routes return 404 in production
Must be: `app/api/[name]/route.ts` with exports `GET`, `POST`, etc.
NOT: `pages/api/` (Pages Router — not used in Rocket projects)

**Pattern F — Image domain not configured**
Signs: `Invalid src prop ... hostname not configured`
```typescript
// next.config.ts
images: { remotePatterns: [{ protocol: 'https', hostname: '*.supabase.co' }] }
```

**Pattern G — SPA routing 404 on refresh** (React/Vite only)
Fix: create `public/_redirects` containing: `/*  /index.html  200`

**Pattern H — Build succeeds but runtime broken**
Almost always: env vars missing in Netlify, or Supabase redirect URLs missing production domain.

## Hard constraints
- Never set `ignoreBuildErrors: true` as a permanent fix — only as a temporary unblock
- Never remove TypeScript strict mode to fix type errors — fix the types
- Env var changes in Netlify require a fresh deploy — "save" alone does nothing

## Output format
```
Pattern identified: [A/B/C/D/E/F/G/H]
Root cause: [one sentence]
Fix:
[code or config change]
Verification: [what to check after redeploying]
```
