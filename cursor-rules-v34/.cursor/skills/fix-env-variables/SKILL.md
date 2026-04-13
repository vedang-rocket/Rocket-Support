---
name: fix-env-variables
description: >
    environment variables not loading undefined, API key undefined in production, Supabase URL
  undefined process.env NEXT_PUBLIC_SUPABASE_URL is undefined, app works locally broken in
  production env vars, NEXT_PUBLIC_ variable not accessible in browser, secret key exposed
  in client code accidentally committed, .env.local not working after edit, missing env var
  error cannot read property of undefined, process.env returns undefined at runtime,
  Netlify environment variables not set, service role key vs anon key confusion, wrong Stripe
  key environment test vs live, quotes in env file breaking values, forgot to restart dev server,
  env var change not taking effect in Netlify need to redeploy, .env.local not synced to Netlify
globs: ["**/*.ts", "**/*.tsx", "**/*.js", "**/*.sql"]
---

# Skill: Fix Environment Variables

**The silent killer** — most "works locally, broken in production" issues trace back to env vars.  
**When to use**: Any issue where an API key, URL, or config value is missing or undefined.

---

## Step 1 — Verify Locally First

```bash
# Check .env.local exists (not just .env.example)
ls -la .env.local
# If missing: cp .env.example .env.local  then fill in values

# Check variables are actually loading
node -e "
  require('dotenv').config({path: '.env.local'});
  const vars = [
    'NEXT_PUBLIC_SUPABASE_URL',
    'NEXT_PUBLIC_SUPABASE_ANON_KEY',
    'SUPABASE_SERVICE_ROLE_KEY',
    'STRIPE_SECRET_KEY',
    'STRIPE_WEBHOOK_SECRET',
    'NEXT_PUBLIC_SITE_URL',
  ];
  vars.forEach(v => console.log(v + ':', process.env[v] ? '✅ set' : '❌ MISSING'));
"

# After editing .env.local, ALWAYS restart the dev server
# Ctrl+C → npm run dev
# Next.js does NOT hot-reload env var changes
```

---

## Step 2 — Understand the Rules

### Rule 1: `NEXT_PUBLIC_` = Browser-Accessible
```bash
# Accessible in browser AND server code
NEXT_PUBLIC_SUPABASE_URL=https://xxx.supabase.co      ✅ OK for browser
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...                  ✅ OK for browser (it's the public key)
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_test_...        ✅ OK for browser
NEXT_PUBLIC_SITE_URL=https://your-app.netlify.app      ✅ OK for browser

# ❌ NEVER put secrets with NEXT_PUBLIC_ prefix
NEXT_PUBLIC_STRIPE_SECRET_KEY=sk_test_...             ❌ EXPOSED TO BROWSER — security risk
NEXT_PUBLIC_SUPABASE_SERVICE_ROLE_KEY=eyJ...          ❌ GIVES FULL DB ACCESS TO ANYONE
```

### Rule 2: No prefix = Server-Only
```bash
# Only accessible in: Server Components, Route Handlers, Server Actions, middleware
STRIPE_SECRET_KEY=sk_test_...                          ✅ server only
STRIPE_WEBHOOK_SECRET=whsec_...                        ✅ server only
SUPABASE_SERVICE_ROLE_KEY=eyJ...                       ✅ server only
RESEND_API_KEY=re_...                                  ✅ server only
OPENAI_API_KEY=sk-...                                  ✅ server only
```

### Rule 3: `.env.local` is NEVER pushed to Netlify
```
.env.local → local development only
Netlify → must be added manually via dashboard
Every variable in .env.local must ALSO exist in Netlify
```

---

## Step 3 — Complete Variable Reference

```bash
# ============================================
# REQUIRED IN BOTH .env.local AND NETLIFY
# ============================================

# Supabase
NEXT_PUBLIC_SUPABASE_URL=https://[project-id].supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=eyJ...               # anon/public key from Supabase API settings
SUPABASE_SERVICE_ROLE_KEY=eyJ...                   # service_role key — server only

# Stripe (if payments enabled)
STRIPE_SECRET_KEY=sk_test_...                      # sk_live_... in production
NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY=pk_test_...     # pk_live_... in production
STRIPE_WEBHOOK_SECRET=whsec_...                    # unique per endpoint + environment
STRIPE_PRICE_ID=price_...                          # must be recreated in live mode for prod

# App URL
NEXT_PUBLIC_SITE_URL=http://localhost:3000         # https://your-app.netlify.app in prod

# Email (if Resend enabled)
RESEND_API_KEY=re_...

# AI (if OpenAI/Anthropic enabled)
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
```

---

## Step 4 — How to Add to Netlify

```
1. Netlify Dashboard → your site → Site Configuration → Environment Variables
2. Click "Add a variable"
3. Key = variable name (e.g., STRIPE_SECRET_KEY)
4. Value = the value (no quotes needed)
5. Select: "Same value for all deploy contexts"
   OR: set different values for Production vs Deploy Preview
6. Save

AFTER ADDING ALL VARIABLES:
→ Deploys → Trigger deploy → "Clear cache and deploy"
⚠️ Just saving env vars does NOT redeploy automatically
⚠️ The new values only take effect after a fresh deploy
```

---

## Step 5 — Common Mistakes + Fixes

### Mistake 1: Quotes in `.env.local` values
```bash
# ❌ Wrong — quotes become part of the value
STRIPE_SECRET_KEY="sk_test_abc123"

# ✅ Correct — no quotes
STRIPE_SECRET_KEY=sk_test_abc123

# ✅ OK if value has spaces or special chars
NEXT_PUBLIC_APP_NAME="My App Name"
```

### Mistake 2: Accessing server-only var in a Client Component
```typescript
// ❌ Will be undefined at runtime in browser
'use client'
const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!)  // undefined!

// ✅ Server-only vars in Server Components or Route Handlers only
// app/api/stripe/checkout/route.ts (Route Handler — server only)
const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!)  // works
```

### Mistake 3: Forgot to restart dev server after `.env.local` change
```bash
# Environment variables are loaded ONCE at server start
# Edit .env.local → Ctrl+C → npm run dev
# No hot reload for env vars — must restart
```

### Mistake 4: Wrong variable in Netlify for production
```bash
# Dev .env.local:
STRIPE_SECRET_KEY=sk_test_abc123      # test mode

# Netlify Production should be:
STRIPE_SECRET_KEY=sk_live_xyz456      # live mode — DIFFERENT key

# Common mistake: copying test keys to Netlify
# Then payments appear to work but no real money moves
```

### Mistake 5: Using Supabase anon key as service role key
```bash
# Supabase has TWO keys — both in Dashboard → Settings → API
NEXT_PUBLIC_SUPABASE_ANON_KEY  = anon/public key  (starts with eyJ, shorter)
SUPABASE_SERVICE_ROLE_KEY      = service_role key  (starts with eyJ, longer)

# They look similar but do VERY different things:
# Anon key = respects RLS — limited access
# Service role = bypasses ALL RLS — full database access
# Never mix them up
```

### Mistake 6: Variable works in dev, undefined in Netlify function
```
Netlify has TWO places for env vars:
1. Site Configuration → Environment Variables (for Next.js build + runtime)
2. Functions → Environment (for Netlify Functions only)

For Next.js App Router projects, use #1 only.
After adding, trigger "Clear cache and deploy" — not just "Deploy site"
```

---

## Step 6 — Debug Undefined in Production

```typescript
// Add this to a Server Component temporarily to debug
// app/(protected)/debug/page.tsx (delete after debugging)
export default async function DebugPage() {
  // This runs server-side — safe to log server vars
  console.log('ENV CHECK:', {
    supabaseUrl: !!process.env.NEXT_PUBLIC_SUPABASE_URL,
    supabaseAnon: !!process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
    serviceRole: !!process.env.SUPABASE_SERVICE_ROLE_KEY,
    stripeSecret: !!process.env.STRIPE_SECRET_KEY,
    siteUrl: process.env.NEXT_PUBLIC_SITE_URL,
  })
  return <div>Check Netlify function logs</div>
}
// Then: Netlify Dashboard → Site → Functions → check logs
```

---

## Step 7 — Verify

```bash
# After fixing and redeploying:

# 1. Check Supabase connection (server-side var)
# Navigate to a protected page while logged in
# If it loads with data → SUPABASE vars correct

# 2. Check Stripe (live mode)
# Try a test checkout with live keys + test card 4242 4242 4242 4242
# Should process → check Stripe Dashboard for the payment

# 3. Check site URL (affects OAuth redirects, Stripe redirects)
# Complete an OAuth login → should redirect back to app, not localhost
```

---

## Step 8 — Email (Resend) Issues

Email is the most common "works in dev, broken in prod" issue that isn't Stripe or Supabase.

### Symptom A: Confirmation emails not sending at all
```bash
# Check RESEND_API_KEY is set (server-only — never NEXT_PUBLIC_)
node -e "require('dotenv').config({path:'.env'}); console.log('RESEND:', !!process.env.RESEND_API_KEY)"
```

If key is set but emails still not sending:
1. Go to Resend Dashboard → check Logs for delivery attempts
2. Check if domain is verified in Resend (unverified domains are rejected)
3. Test with Resend's test email: `delivered@resend.dev` — always succeeds

### Symptom B: "from" address rejected / domain not authorized
```
Error: The from address must use a verified domain
```
**Fix**: In Resend Dashboard → Domains → add and verify your domain
Until domain is verified, use: `from: "onboarding@resend.dev"` (Resend's test domain)

### Symptom C: Emails go to spam
Common causes:
- Using `onboarding@resend.dev` in production (not your domain)
- Domain DNS records not configured (SPF, DKIM, DMARC)

**Fix**:
1. Add your domain to Resend
2. Add the DNS records Resend provides (SPF, DKIM) to your domain registrar
3. Set `from: "noreply@yourdomain.com"` in your Resend calls

### Supabase Auth Emails vs Resend Emails
These are TWO different email systems:

| Emails | System | Config |
|---|---|---|
| Signup confirmation, password reset, magic links | Supabase Auth | Supabase Dashboard → Auth → Email Templates |
| Transactional (receipts, notifications) | Resend via your code | `RESEND_API_KEY` in .env |

For Supabase auth emails in production: Supabase Dashboard → Settings → Auth → SMTP → add Resend SMTP credentials.

### Env vars needed for email
```bash
RESEND_API_KEY=re_...                    # Server-only (never NEXT_PUBLIC_)
NEXT_PUBLIC_SITE_URL=https://yourapp.com # Used in email templates for links
```
