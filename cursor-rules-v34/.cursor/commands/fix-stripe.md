# Purpose: Diagnose and fix Stripe payment, webhook, and subscription issues

This is a Rocket.new Next.js App Router project using Stripe + Supabase.

## CHECKPOINT PROTOCOL

After every 3 files changed, STOP and output:
- Files changed so far + one-line summary of each change
- Current understanding of remaining work
- Any assumptions made that need your verification

Do not proceed until you explicitly say "continue".

---

## Step 0 — MCP Live Diagnostics (run BEFORE touching any code)

If Stripe MCP is connected, run these immediately and report results:

```
1. webhooks.read
   → Does an endpoint exist pointing to /api/webhooks/stripe?
   → What events is it subscribed to?
   → What do the last 5 delivery attempts show?

2. If user reports payment succeeded but app not updated:
   charges.read → find charge by date/amount → check metadata.user_id is set

3. If subscription status is wrong in the app:
   subscriptions.read → read actual Stripe subscription status
   → Compare to what's stored in Supabase subscriptions table

4. If "no such price" error:
   prices.read → verify the price ID exists in current mode (test vs live)
```

Report all findings before touching a single file. This replaces manually opening Stripe Dashboard.
If MCP is not connected, skip to Step 1.

---

## Step 1 — Scope lock

I will ONLY touch files related to the Stripe issue.
I will NOT modify: auth logic, unrelated API routes, UI components, database schema.

---

## Step 2 — Shell checks

```bash
# A. Raw body used in webhook? (most common failure)
grep -n "request.json()" app/api/webhooks/stripe/route.ts
# ANY result = BROKEN — must be request.text()

# B. Webhook route exists
ls app/api/webhooks/stripe/route.ts && echo "✅" || echo "❌ MISSING"

# C. Key environment check
grep "STRIPE_SECRET_KEY" .env.local
# Dev: sk_test_ | Prod: sk_live_
```

---

## Step 3 — Identify the symptom

### Symptom A: `StripeSignatureVerificationError`
**Cause**: `request.json()` instead of `request.text()`
```typescript
// ❌ BROKEN
const body = await request.json()

// ✅ FIX
const body = await request.text()  // raw bytes preserved for HMAC
const sig = request.headers.get('stripe-signature')!
const event = stripe.webhooks.constructEvent(body, sig, process.env.STRIPE_WEBHOOK_SECRET!)
```

### Symptom B: Webhook not firing at all
```
✅ Fix checklist:
□ Stripe Dashboard → Developers → Webhooks → endpoint exists?
□ Endpoint URL = production URL (NOT localhost)
□ For local testing: stripe listen --forward-to localhost:3000/api/webhooks/stripe
□ Subscribed events include: checkout.session.completed, customer.subscription.deleted
```

### Symptom C: Payment succeeds, database not updated
```
Root cause: webhook not processing OR metadata.user_id not set on checkout session
Fix 1: Check webhook deliveries (Stripe MCP: webhooks.read)
Fix 2: Verify checkout session sets metadata: { user_id: user.id }
Fix 3: Verify webhook handler uses service role key (bypasses RLS)
```

### Symptom D: `"No such price: price_xxx"` in production
```
Test mode and live mode are FULLY ISOLATED.
Fix: recreate products/prices in Stripe LIVE mode
     update STRIPE_PRICE_ID in Netlify env vars to live mode ID
     update STRIPE_SECRET_KEY to sk_live_
     update NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY to pk_live_
     update STRIPE_WEBHOOK_SECRET to live endpoint secret
```

### Symptom E: Webhook secret mismatch
```
Each endpoint has a UNIQUE signing secret.
Test endpoints ≠ live endpoints ≠ CLI forwarding — all different secrets.
Fix: Stripe Dashboard → Developers → Webhooks → [endpoint] → Signing secret → copy fresh
     Update STRIPE_WEBHOOK_SECRET in Netlify → trigger fresh deploy
```

---

## Hard constraints
- ALWAYS `request.text()` not `request.json()` in webhook handlers
- ALWAYS use service role key (not anon key) in webhook handler for DB writes
- ALWAYS set `metadata: { user_id: user.id }` when creating checkout sessions
- NEVER hardcode price IDs — use `process.env.STRIPE_PRICE_ID`
- Test and live environments are completely isolated — never mix keys

---

## Output format
```
MCP findings: [webhook endpoint status, recent delivery results]
Root cause: [one sentence]
Files to change: [list]
Files NOT touched: [list]
Fix: [diff shown file by file]
Verification: [how to confirm it's fixed]
```
