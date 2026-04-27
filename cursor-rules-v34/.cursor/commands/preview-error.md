# /preview-error — Fix Preview Not Loading (CSP Headers)

## When to use
Preview blank, scripts blocked, Rocket preview iframe not loading, GTM/analytics not firing,
Supabase realtime blocked, `Refused to load script` in console, `Content Security Policy` errors.

## What this command does
1. Finds `next.config.ts` or `next.config.js` at the project root
2. Checks for an existing `headers()` function with Content-Security-Policy
3. Adds or updates the three directives that Rocket preview requires:
   - `script-src` — allows Rocket, GTM, GA, AdSense scripts
   - `script-src-elem` — same allowlist for `<script>` elements
   - `connect-src` — allows Supabase, OpenAI, BioID, Terra, Rocket analytics

## Steps

### Step 1 — Read next.config.ts (or next.config.js)

```
Read next.config.ts at the project root.
If it doesn't exist, read next.config.js.
If neither exists, create next.config.ts with the full template below.
```

### Step 2 — Check for existing headers() function

```
Search for: async headers()
If found → locate the Content-Security-Policy header entry → go to Step 3b
If not found → go to Step 3a
```

### Step 3a — Add headers() block (no existing CSP)

Add the following `headers()` function inside the `nextConfig` object.
If `nextConfig` already has other keys, append `headers` alongside them.

```typescript
async headers() {
  return [
    {
      source: '/(.*)',
      headers: [
        {
          key: 'Content-Security-Policy',
          value: [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://www.googletagmanager.com https://www.google-analytics.com https://pagead2.googlesyndication.com https://static.rocket.new",
            "script-src-elem 'self' 'unsafe-inline' 'unsafe-eval' https://www.googletagmanager.com https://www.google-analytics.com https://pagead2.googlesyndication.com https://static.rocket.new",
            "connect-src 'self' https://*.supabase.co wss://*.supabase.co https://api.openai.com https://bws.bioid.com https://*.bioid.com https://api.tryterra.co https://appanalytics.rocket.new",
            "img-src 'self' data: blob: https:",
            "font-src 'self' data: https://fonts.gstatic.com",
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
            "frame-src 'self' https://static.rocket.new",
            "worker-src 'self' blob:",
          ].join('; '),
        },
      ],
    },
  ]
},
```

### Step 3b — Update existing CSP (already has headers())

Find the `Content-Security-Policy` value string and replace ONLY these three directives
(leave all other directives untouched):

```
script-src → 'self' 'unsafe-inline' 'unsafe-eval' https://www.googletagmanager.com https://www.google-analytics.com https://pagead2.googlesyndication.com https://static.rocket.new
script-src-elem → 'self' 'unsafe-inline' 'unsafe-eval' https://www.googletagmanager.com https://www.google-analytics.com https://pagead2.googlesyndication.com https://static.rocket.new
connect-src → 'self' https://*.supabase.co wss://*.supabase.co https://api.openai.com https://bws.bioid.com https://*.bioid.com https://api.tryterra.co https://appanalytics.rocket.new
```

If any of the three directives are missing from the existing CSP string, append them.

### Step 4 — Verify

```bash
# Confirm the directives are in the built config
grep -A 20 "Content-Security-Policy" next.config.ts | grep -E "script-src|connect-src|rocket.new"
```

Expected output should contain `static.rocket.new` and `appanalytics.rocket.new`.

---

## Full next.config.ts template (use when file doesn't exist)

```typescript
import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  async headers() {
    return [
      {
        source: '/(.*)',
        headers: [
          {
            key: 'Content-Security-Policy',
            value: [
              "default-src 'self'",
              "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://www.googletagmanager.com https://www.google-analytics.com https://pagead2.googlesyndication.com https://static.rocket.new",
              "script-src-elem 'self' 'unsafe-inline' 'unsafe-eval' https://www.googletagmanager.com https://www.google-analytics.com https://pagead2.googlesyndication.com https://static.rocket.new",
              "connect-src 'self' https://*.supabase.co wss://*.supabase.co https://api.openai.com https://bws.bioid.com https://*.bioid.com https://api.tryterra.co https://appanalytics.rocket.new",
              "img-src 'self' data: blob: https:",
              "font-src 'self' data: https://fonts.gstatic.com",
              "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
              "frame-src 'self' https://static.rocket.new",
              "worker-src 'self' blob:",
            ].join('; '),
          },
        ],
      },
    ]
  },
}

export default nextConfig
```

---

## IF STILL BROKEN

1. Open DevTools → Console → look for `Refused to load` errors — the blocked URL tells you which directive to extend
2. Supabase realtime blocked? Check `wss://*.supabase.co` is in `connect-src`
3. Rocket preview iframe blocked? Ensure `frame-src` includes `https://static.rocket.new`
4. After config change: restart dev server (`npm run dev`) — headers are not hot-reloaded
