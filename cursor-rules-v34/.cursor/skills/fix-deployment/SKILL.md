---
name: fix-deployment
description: >
    Netlify build fails, deployment broken, app works locally not in production, module not found
  on Netlify, TypeScript error blocking build Type error cannot find name, environment variables
  undefined in production, 404 on page refresh direct URL, build log error, deploy stuck spinning,
  Next.js build error, cannot find module missing dependency, static generation failed,
  image optimization error Invalid src prop hostname not configured, API route 404 production,
  cookies should be awaited build error Next.js 15, SPA routing 404, Netlify deploy succeeded
  but app broken at runtime, TypeScript ignoreBuildErrors, missing package.json dependency
globs: ["**/*.ts", "**/*.tsx", "**/*.js", "**/*.sql"]
---

# Skill: Fix Deployment

**Stack**: Next.js App Router → Netlify  
**When to use**: Any Netlify deployment failure or "works locally, broken in production"

---

## Step 1 — Read the Build Log First

Every answer is in the build log. Never guess before reading it.

```
Netlify Dashboard → your site → Deploys → click the failed deploy → scroll to build log
Look for: the FIRST red line — that's the root cause
Everything after it is usually cascading failures from the first error
```

---

## Step 2 — Identify Error Type → Follow Branch

### Branch A: TypeScript Build Errors
**Signs**: `Type error:`, `TS2xxx:`, `error TS`  
**Key fact**: Next.js treats ALL TypeScript errors as build failures in production

```bash
# Reproduce locally first
npx tsc --noEmit
# Fix every error shown before attempting to redeploy
```

**Common TS errors in Rocket projects:**

```typescript
// Error: Type 'X | null' is not assignable to type 'X'
// Fix: add null check
const profile = data ?? null  // or: data!  (if you're sure it exists)

// Error: Property 'user' does not exist on type '{ user: User | null }'
// Fix: type the Supabase response
const { data: { user } } = await supabase.auth.getUser()
if (!user) redirect('/login')
// Now TypeScript knows user is not null below this line

// Error: Argument of type 'string | undefined' not assignable to 'string'
// Fix: assert or provide fallback
const key = process.env.STRIPE_SECRET_KEY!  // assert non-null
// OR: const key = process.env.STRIPE_SECRET_KEY ?? ''
```

**Emergency unblock** (fix TS errors properly afterward):
```typescript
// next.config.ts — temporary only, remove after fixing type errors
const nextConfig = {
  typescript: { ignoreBuildErrors: true },
  eslint: { ignoreDuringBuilds: true },
}
```

---

### Branch B: Module Not Found
**Signs**: `Cannot find module 'X'`, `Module not found: Error`

```bash
# Find what's importing the missing module
grep -r "from 'missing-module'" ./app ./components ./lib

# Check if it's in package.json
grep "missing-module" package.json

# Fix: install it
npm install missing-module
# Then commit package.json AND package-lock.json
```

**Common cause**: Package used in code but only in `devDependencies` in package.json.  
Move it to `dependencies`:
```json
{
  "dependencies": {
    "missing-module": "^1.0.0"  // move from devDependencies
  }
}
```

---

### Branch C: Environment Variables Not Loading in Production
**Signs**: App works locally, `undefined` errors in prod, Supabase/Stripe fails only on Netlify

```
Root cause: .env.local is NEVER pushed to Netlify automatically
Every variable must be added manually to Netlify dashboard

Fix:
1. Netlify Dashboard → Site → Site Configuration → Environment Variables
2. Add ALL variables from .env.local one by one
3. After adding: Deploys → Trigger deploy → "Clear cache and deploy"

⚠️ After adding env vars, you MUST trigger a new deploy
   Netlify does NOT auto-redeploy when env vars change
```

**Variables that must exist in Netlify (not just .env.local):**
```
NEXT_PUBLIC_SUPABASE_URL
NEXT_PUBLIC_SUPABASE_ANON_KEY
SUPABASE_SERVICE_ROLE_KEY
STRIPE_SECRET_KEY               ← use sk_live_ in production
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY  ← use pk_live_ in production
STRIPE_WEBHOOK_SECRET           ← live endpoint's secret, not test
STRIPE_PRICE_ID                 ← live mode price ID
NEXT_PUBLIC_SITE_URL            ← https://your-app.netlify.app
RESEND_API_KEY                  ← if using email
```

---

### Branch D: 404 on Page Refresh (React Vite only)
**Signs**: Direct URL works, but refreshing the page returns 404  
**Not a Next.js issue** — only affects React/Vite (SPA) builds

```
Fix: Create public/_redirects with this content:
/*  /index.html  200
```

```bash
# Create the file
echo "/*  /index.html  200" > public/_redirects
```

---

### Branch E: Next.js App Router API Routes Return 404 in Production
**Signs**: API routes work locally, return 404 on Netlify

```
Cause: Route file in wrong location or wrong export name
App Router API routes MUST follow this pattern:
  app/api/[route-name]/route.ts
  Exports: GET, POST, PUT, DELETE, PATCH (capitalized)

NOT:
  pages/api/   ← Pages Router, not used by Rocket
  app/api/handler.ts  ← wrong filename (must be route.ts)
```

---

### Branch F: `next/image` Error — Unoptimized Remote Images
**Signs**: `Error: Invalid src prop ... hostname "x.x.x" is not configured`

```typescript
// next.config.ts — add Supabase storage domain
const nextConfig = {
  images: {
    remotePatterns: [
      {
        protocol: 'https',
        hostname: '*.supabase.co',
        pathname: '/storage/v1/object/public/**',
      },
      // Add other remote image domains here
    ],
  },
}
```

---

### Branch G: `cookies()` / `headers()` Errors in Build
**Signs**: `Error: cookies() should be awaited` during build

```typescript
// Fix: await all dynamic functions in Next.js 15
const cookieStore = await cookies()   // not: cookies()
const headersList = await headers()   // not: headers()

// If these cause issues in static routes, force dynamic:
export const dynamic = 'force-dynamic'
// Add to any page.tsx that uses cookies/headers/auth
```

---

### Branch H: Build Succeeds but App is Broken in Production
**Signs**: Netlify shows "Published" but the app has errors at runtime

```
This is almost always one of:
1. Missing env vars (Branch C above)
2. Supabase redirect URLs missing production domain
3. Stripe test keys in production
4. API routes returning wrong data

Debug:
- Open browser DevTools → Console → look for errors
- Open browser DevTools → Network → look for failed API calls (red)
- Check Netlify Function logs: Site → Functions → click a function → logs
```

---

## Step 3 — Quick Fixes Checklist

```bash
# Before redeploying, always run:
npx tsc --noEmit          # fix all TypeScript errors
npm run build             # test the production build locally
# If npm run build succeeds locally but fails on Netlify → env var issue
```

```
After any env var change in Netlify:
□ Trigger deploy → "Clear cache and deploy" (not just "Deploy site")
□ Wait for deploy to complete (2-3 min)
□ Hard refresh browser (Cmd+Shift+R) to bypass browser cache
```

---

## Step 4 — Verify Deployment

```bash
# Check the deployed URL directly
curl -I https://your-app.netlify.app
# Should return: HTTP/2 200

# Check API routes work
curl https://your-app.netlify.app/api/health
# (if you have a health endpoint)

# Check Supabase connection works in production
# Navigate to a protected page while logged in
# If it loads → Supabase env vars are correct
# If it redirects to login → redirect URL issue
```
