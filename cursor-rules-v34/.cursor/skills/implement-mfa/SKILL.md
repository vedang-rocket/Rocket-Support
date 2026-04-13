---
name: implement-mfa
description: >
  add MFA to supabase nextjs, multi factor authentication supabase setup,
  TOTP two factor auth supabase, mfa.enroll mfa.challenge mfa.verify nextjs,
  authenticator app QR code supabase, supabase MFA not working fix,
  require MFA for all users, optional MFA supabase, mfa.getAuthenticatorAssuranceLevel,
  aal1 aal2 supabase, enforce second factor RLS, add google authenticator supabase
globs: ["**/*.ts", "**/*.tsx"]
alwaysApply: false
---

# Skill: Implement MFA (Multi-Factor Authentication)

**Stack**: Next.js App Router + Supabase Auth MFA (TOTP)
**When to use**: Adding two-factor authentication to any Rocket.new project.
Free on all Supabase plans. No configuration needed — enabled by default.

---

## The 3-Part Implementation

MFA has three distinct parts. Build them in this order.

### Part 1 — Enrollment Component (user sets up MFA)

Place this in your settings/profile page so users can enable MFA.

```typescript
// app/(protected)/settings/mfa/page.tsx
'use client'
import { useState, useEffect } from 'react'
import { createClient } from '@/lib/supabase/client'

export default function MFASetupPage() {
  const [qrCode, setQrCode] = useState('')
  const [factorId, setFactorId] = useState('')
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const [enrolled, setEnrolled] = useState(false)
  const supabase = createClient()

  useEffect(() => {
    // Start enrollment — generates QR code for authenticator app
    supabase.auth.mfa.enroll({ factorType: 'totp' }).then(({ data, error }) => {
      if (error) { setError(error.message); return }
      setQrCode(data!.totp.qr_code)     // SVG string
      setFactorId(data!.id)
    })
  }, [])

  const verifyAndEnable = async () => {
    setError('')
    // Step 1: Create a challenge
    const { data: challengeData, error: challengeError } =
      await supabase.auth.mfa.challenge({ factorId })
    if (challengeError) { setError(challengeError.message); return }

    // Step 2: Verify the code from the authenticator app
    const { error: verifyError } = await supabase.auth.mfa.verify({
      factorId,
      challengeId: challengeData.id,
      code: code.trim(),
    })
    if (verifyError) { setError('Invalid code. Try again.'); return }

    setEnrolled(true)  // MFA is now active
  }

  if (enrolled) return <p>MFA enabled successfully! Your account is now secured.</p>

  return (
    <div>
      <h2>Set up two-factor authentication</h2>
      <p>Scan this QR code with Google Authenticator, Authy, or 1Password:</p>
      {qrCode && <img src={qrCode} alt="MFA QR Code" width={200} />}
      <input
        type="text"
        placeholder="Enter 6-digit code"
        value={code}
        onChange={e => setCode(e.target.value)}
        maxLength={6}
      />
      <button onClick={verifyAndEnable}>Enable MFA</button>
      {error && <p style={{ color: 'red' }}>{error}</p>}
    </div>
  )
}
```

### Part 2 — Challenge Wrapper (enforce MFA after login)

Wrap your dashboard/protected layout to intercept users who have MFA set up but haven't verified it yet.

```typescript
// app/(protected)/layout.tsx — ADD this check to your existing protected layout
import { redirect } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'
import { MFAChallengeGate } from '@/components/MFAChallengeGate'

export default async function ProtectedLayout({ children }: { children: React.ReactNode }) {
  const supabase = await createClient()
  const { data: { user }, error } = await supabase.auth.getUser()
  if (error || !user) redirect('/login')

  return <MFAChallengeGate>{children}</MFAChallengeGate>
}
```

```typescript
// components/MFAChallengeGate.tsx — client component that checks MFA status
'use client'
import { useState, useEffect } from 'react'
import { createClient } from '@/lib/supabase/client'

export function MFAChallengeGate({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<'loading' | 'mfa-required' | 'ready'>('loading')
  const [code, setCode] = useState('')
  const [error, setError] = useState('')
  const supabase = createClient()

  useEffect(() => {
    supabase.auth.mfa.getAuthenticatorAssuranceLevel().then(({ data }) => {
      if (data?.nextLevel === 'aal2' && data.nextLevel !== data.currentLevel) {
        setState('mfa-required')  // Has MFA factor but hasn't verified it this session
      } else {
        setState('ready')
      }
    })
  }, [])

  const verify = async () => {
    setError('')
    const { data: factors } = await supabase.auth.mfa.listFactors()
    const factor = factors?.totp[0]
    if (!factor) return

    const { data: challenge, error: challengeErr } =
      await supabase.auth.mfa.challenge({ factorId: factor.id })
    if (challengeErr) { setError(challengeErr.message); return }

    const { error: verifyErr } = await supabase.auth.mfa.verify({
      factorId: factor.id,
      challengeId: challenge.id,
      code: code.trim(),
    })
    if (verifyErr) { setError('Invalid code. Please try again.'); return }
    setState('ready')
  }

  if (state === 'loading') return <div>Loading...</div>

  if (state === 'mfa-required') {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', marginTop: '10rem' }}>
        <h2>Two-factor authentication required</h2>
        <p>Enter the 6-digit code from your authenticator app:</p>
        <input
          type="text"
          value={code}
          onChange={e => setCode(e.target.value)}
          maxLength={6}
          autoFocus
        />
        <button onClick={verify}>Verify</button>
        {error && <p style={{ color: 'red' }}>{error}</p>}
      </div>
    )
  }

  return <>{children}</>
}
```

### Part 3 — Enforce via RLS (optional — adds DB-level enforcement)

```sql
-- Only allow access to sensitive data for users who completed MFA
CREATE POLICY "mfa_required_for_sensitive"
ON sensitive_records FOR ALL
USING (
  (SELECT auth.jwt() ->> 'aal') = 'aal2'
);
```

---

## Manage Existing Factors

```typescript
// List user's MFA factors (in settings page)
const { data: { totp, phone } } = await supabase.auth.mfa.listFactors()

// Remove a factor (user must be aal2 to unenroll)
await supabase.auth.mfa.unenroll({ factorId: totp[0].id })
```

---

## Verification

```typescript
// Check if user has MFA set up
const { data } = await supabase.auth.mfa.getAuthenticatorAssuranceLevel()
const hasMFA = data?.nextLevel === 'aal2'
const verifiedMFA = data?.currentLevel === 'aal2'
```

---

## Common Mistakes

| Mistake | Fix |
|---|---|
| `mfa.enroll()` called multiple times | Call it once in `useEffect` — each call creates a new (duplicate) factor |
| Code expired | MFA challenges expire in 5 minutes — create a new challenge on each attempt |
| Missing `await` on `getAuthenticatorAssuranceLevel` | It returns a Promise — always await |
| Calling MFA APIs in Server Components | MFA APIs (`enroll`, `challenge`, `verify`) are client-side only |
