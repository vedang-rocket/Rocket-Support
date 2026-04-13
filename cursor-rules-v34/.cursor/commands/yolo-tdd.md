# Purpose: Fully autonomous Test-Driven Development loop — write tests first, then implement, then iterate until green

This is the highest-leverage command in the system.
With YOLO mode enabled, the agent writes code, runs tests, fixes failures, reruns —
completely autonomously until all tests pass. You come back to green.

## BEFORE RUNNING THIS COMMAND

### Step 1 — Enable YOLO Mode
```
Cursor Settings → Features → Agent → Enable YOLO Mode ✅
```
Without YOLO mode, the agent stops and asks permission before every terminal command.
With YOLO mode, it runs autonomously. This is intentional for this command.

### Step 2 — Prevent Zombie Revert bug
```
- Close the Agent Review Tab if open
- Disable Format On Save: Settings → Editor → Format On Save → OFF
```

### Step 3 — Commit current state
```bash
git add -A && git commit -m "checkpoint before yolo-tdd: [feature name]"
```
This gives you a safe rollback point. Non-negotiable before running autonomous loops.

---

## Usage
/yolo-tdd [what to build]

Example: /yolo-tdd user profile update endpoint
Example: /yolo-tdd RLS policies for the projects table
Example: /yolo-tdd Stripe webhook handler for subscription events

---

## My Autonomous Loop Protocol

### Phase 1 — Write the test FIRST (no implementation yet)

```typescript
// I will create: __tests__/[feature].test.ts
// Tests define the contract — implementation must satisfy the tests
// Not the other way around

// Example test structure for a Rocket.new API route:
describe('[feature]', () => {
  it('should [expected behavior 1]', async () => {
    // arrange
    // act
    // assert
  })

  it('should reject unauthenticated requests', async () => {
    // always test auth protection
  })

  it('should handle edge case: [empty/null/invalid]', async () => {
    // always test edge cases
  })
})
```

I will show you the tests and wait for your approval before writing any implementation.

### Phase 2 — Confirm tests make sense

Before running: "Do these tests correctly define what success looks like?"

If yes → proceed to Phase 3.
If no → revise tests until they accurately define the requirement.

### Phase 3 — Autonomous implementation loop

Once tests are approved:

```
LOOP:
  1. Write minimal implementation to pass tests
  2. Run: npm test -- --testPathPattern=[feature] (or equivalent)
  3. If PASS → done, report results
  4. If FAIL → read error output
             → identify which assertion failed and why
             → fix only what failed (minimal change)
             → go to step 2
  
  Max iterations: 10
  If still failing at iteration 10 → STOP and report blocker
```

### Phase 4 — Regression check

After all tests pass:
```bash
npm test  # run full test suite
npx tsc --noEmit  # TypeScript check
```

If any existing tests break → fix the regression before declaring done.

### Phase 5 — Report

```
✅ TDD Loop Complete

Feature: [name]
Tests written: X
Implementation files: [list]
Iterations needed: N
Final test result: X/X passing
TypeScript: clean
Regressions introduced: none

Files changed:
  [list with one-line description each]
```

---

## Rocket.new Specific Test Patterns

### Test an API route with auth
```typescript
import { createClient } from '@supabase/supabase-js'

describe('POST /api/[route]', () => {
  it('returns 401 for unauthenticated requests', async () => {
    const res = await fetch('/api/[route]', { method: 'POST' })
    expect(res.status).toBe(401)
  })

  it('returns 200 with valid data for authenticated user', async () => {
    // Use test user credentials
    const res = await fetch('/api/[route]', {
      method: 'POST',
      headers: { Authorization: `Bearer ${testToken}` },
      body: JSON.stringify({ /* valid data */ })
    })
    expect(res.status).toBe(200)
  })
})
```

### Test RLS policies
```sql
-- Run via Supabase MCP execute_sql
-- Test as specific user
SET LOCAL role authenticated;
SET LOCAL "request.jwt.claims" = '{"sub": "test-user-uuid"}';
SELECT * FROM your_table;  -- should only return this user's rows
RESET role;
```

### Test Stripe webhook
```typescript
import { constructEvent } from 'stripe'

it('processes checkout.session.completed correctly', async () => {
  const payload = JSON.stringify({ type: 'checkout.session.completed', ... })
  const signature = stripe.webhooks.generateTestHeaderString({ payload, secret })
  
  const res = await fetch('/api/webhooks/stripe', {
    method: 'POST',
    headers: { 'stripe-signature': signature },
    body: payload  // raw text, not JSON
  })
  expect(res.status).toBe(200)
})
```

---

## Hard Constraints

- NEVER skip the git commit in Step 3 — autonomous loops need a rollback point
- NEVER accept a diff containing `// ... existing code` — this is a Cursor bug that deletes code
- NEVER run more than 10 iterations without stopping — infinite loops burn credits
- ALWAYS write tests before implementation — if you write implementation first, this command's value disappears
- ALWAYS run the full test suite at the end — regressions are worse than the original bug
