---
name: fix-stripe
description: >
    Stripe payment not working, webhook not firing no events received, stripe signature verification
  failed StripeSignatureVerificationError, subscription not created after payment succeeds,
  no such customer error cus_ ID, no such price error price_ ID, checkout session creation fails,
  payment succeeds but database not updated subscription status wrong, going live Stripe switch
  to production keys, webhook secret mismatch whsec_, invoice payment failed not handled,
  customer portal broken, test card not working, 4242 card declined, stripe publishable key
  invalid, checkout redirect not working success_url cancel_url, products not in live mode
globs: ["**/*.ts", "**/*.tsx", "**/*.js", "**/*.sql"]
---

# Skill: Fix Stripe

**Stack**: Stripe + Next.js App Router Route Handlers  
**When to use**: Any Stripe payment, checkout, or webhook issue

---

## Step 1 — Run the Verification Script

```bash
# scripts/verify-webhook.js validates your Stripe setup before debugging
# Run: node .cursor/skills/fix-stripe/scripts/verify-webhook.js
```

Then check these manually:

```bash
# A. Is request.json() used in the webhook? (most common webhook failure)
grep -n "request.json()" app/api/webhooks/stripe/route.ts
# Any result = BROKEN — webhook signature will fail silently

# B. Are the correct key environments used?
grep "STRIPE_SECRET_KEY" .env.local
# Dev: starts with sk_test_
# Prod: starts with sk_live_

# C. Webhook route exists
ls app/api/webhooks/stripe/route.ts 2>/dev/null && echo "✅ exists" || echo "❌ MISSING"
```

---

## Step 2 — Identify the Symptom

### Symptom A: `StripeSignatureVerificationError` — webhook fails immediately
**Cause**: `request.json()` used instead of `request.text()` — destroys raw bytes needed for HMAC  
**Fix**:
```typescript
// app/api/webhooks/stripe/route.ts — EXACT pattern required
import { NextResponse } from 'next/server'
import Stripe from 'stripe'

const stripe = new Stripe(process.env.STRIPE_SECRET_KEY!)

export async function POST(request: Request) {
  const body = await request.text()           // ← MUST be .text() not .json()
  const sig = request.headers.get('stripe-signature')!

  let event: Stripe.Event
  try {
    event = stripe.webhooks.constructEvent(
      body,
      sig,
      process.env.STRIPE_WEBHOOK_SECRET!      // ← must match this endpoint's secret
    )
  } catch (err) {
    console.error('Webhook signature failed:', err)
    return NextResponse.json({ error: 'Invalid signature' }, { status: 400 })
  }

  // Handle events
  switch (event.type) {
    case 'checkout.session.completed': { /* ... */ break }
    case 'customer.subscription.deleted': { /* ... */ break }
    case 'invoice.payment_failed': { /* ... */ break }
  }

  return NextResponse.json({ received: true })
}
```

### Symptom B: Webhook not firing at all (no logs in Stripe dashboard)
```
Cause: Endpoint URL is wrong or not registered in Stripe
Fix checklist:
□ Stripe Dashboard → Developers → Webhooks → check endpoint exists
□ Endpoint URL = https://your-production-url.com/api/webhooks/stripe
  (NOT localhost — Stripe cannot reach localhost)
□ For local testing: stripe listen --forward-to localhost:3000/api/webhooks/stripe
□ Subscribed events include: checkout.session.completed,
  customer.subscription.updated, customer.subscription.deleted,
  invoice.payment_succeeded, invoice.payment_failed
```

### Symptom C: Webhook fires but STRIPE_WEBHOOK_SECRET is wrong
```
Each endpoint has a UNIQUE signing secret.
Test mode and live mode have DIFFERENT secrets.
After going live: the secret changes — update it in Netlify env vars.

Fix:
1. Stripe Dashboard → Developers → Webhooks → click your endpoint
2. Under "Signing secret" → click Reveal
3. Copy it → update STRIPE_WEBHOOK_SECRET in Netlify → redeploy
```

### Symptom D: `"No such price: 'price_xxx'"` in production
**Cause**: Test mode price IDs don't exist in live mode  
```
Test and live modes are COMPLETELY ISOLATED:
- Products/prices/customers/subscriptions DON'T transfer
- Every Stripe ID (price_xxx, cus_xxx, sub_xxx) is environment-specific

Fix — go-live checklist:
□ Create products/prices in Stripe LIVE mode dashboard
□ Copy new price ID → update STRIPE_PRICE_ID env var
□ Update STRIPE_SECRET_KEY to sk_live_...
□ Update NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY to pk_live_...
□ Create new webhook endpoint with production URL
□ Update STRIPE_WEBHOOK_SECRET to live endpoint's secret
□ Update all 4 Stripe vars in Netlify Environment Variables
□ Trigger fresh Netlify deploy
```

### Symptom E: Payment succeeds but subscription not created in database
**Cause**: Webhook not processing `checkout.session.completed`  
**Fix**: Add event handler and use service role key for upsert (bypasses RLS):
```typescript
case 'checkout.session.completed': {
  const session = event.data.object as Stripe.CheckoutSession

  // Use service role to bypass RLS — webhook is not a logged-in user
  const supabase = createServiceClient()  // import from lib/supabase/service.ts

  await supabase.from('subscriptions').upsert({
    user_id: session.metadata?.user_id,   // set metadata.user_id when creating session
    stripe_customer_id: session.customer as string,
    stripe_subscription_id: session.subscription as string,
    status: 'pro',
  })
  break
}
```

### Symptom F: Checkout session creation returns 401
**Cause**: User not authenticated when creating checkout session  
```typescript
// app/api/stripe/checkout/route.ts
export async function POST(request: Request) {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })

  const session = await stripe.checkout.sessions.create({
    customer_email: user.email,
    metadata: { user_id: user.id },  // ← CRITICAL: needed in webhook to find the user
    // ...
  })
  return NextResponse.json({ url: session.url })
}
```

### Symptom G: Stripe form not loading (blank iframe)
**Cause**: Publishable key wrong or missing  
```bash
grep "NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY" .env.local
# Dev: must start with pk_test_
# Prod: must start with pk_live_
# Never use secret key (sk_) as publishable key
```

---

## Step 3 — Local Webhook Testing

```bash
# Install Stripe CLI: https://stripe.com/docs/stripe-cli
stripe login

# Forward webhooks to local dev server
stripe listen --forward-to localhost:3000/api/webhooks/stripe

# Trigger a test event
stripe trigger checkout.session.completed
stripe trigger customer.subscription.deleted
stripe trigger invoice.payment_failed

# The CLI shows: ✅ or ❌ for each forwarded event
```

---

## Step 4 — Verify

```bash
# 1. Check webhook recent deliveries in Stripe Dashboard
# Developers → Webhooks → [endpoint] → Recent deliveries
# Look for: ✅ 200 OK or ❌ error codes

# 2. Test card numbers
# Success: 4242 4242 4242 4242
# Insufficient funds: 4000 0000 0000 9995
# 3D Secure required: 4000 0025 0000 3155
# Any future expiry date, any 3-digit CVC

# 3. Check database after test payment
# Supabase SQL Editor:
# SELECT * FROM subscriptions ORDER BY created_at DESC LIMIT 5;
```

---

## Reference Files
- `scripts/verify-webhook.js` — automated environment check
