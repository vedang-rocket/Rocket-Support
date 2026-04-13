---
description: Manually trigger a full codebase risk scan. Runs the risk-scanner agent to produce memory-bank/risk-map.json scored by complexity, churn, coupling, and past bug history.
---

# /risk-scan

Run a complete predictive bug-risk analysis of this codebase.

## What this command does

1. Invokes the `risk-scanner` agent
2. Agent scans every source file for: change frequency, conditional complexity, async patterns, TypeScript any-casts, and past bug history from `fixes-applied.md`
3. Scores each file 0–100 and classifies as high / medium / low risk
4. Writes results to `memory-bank/risk-map.json`
5. Prints a summary of the top 10 risky files

## When to run

- Before starting a large refactor
- After a cluster of bugs in the same area
- As part of sprint planning to identify fragile areas
- Weekly (also runs automatically via the Risk Scan automation)

## Output

After running, you will see:

```
Risk scan complete. N high-risk files identified.

Top 10 risky files:
  82/100 app/api/webhooks/stripe/route.ts  [bug-history]
  74/100 lib/auth/session.ts               [high-churn]
  68/100 components/checkout/PaymentForm.tsx [async-heavy]
  ...
```

The `beforeEdit` hook will now warn you inline when you open any HIGH risk file.

## Risk factors explained

| Factor | Weight | What it means |
|---|---|---|
| bug-history | 25% | File appears in `fixes-applied.md` entries |
| high-churn | 25% | File changed in many commits (high coupling) |
| complex-logic | 20% | High ratio of conditionals to lines |
| async-heavy | 15% | Many `useEffect` hooks or nested async calls |
| type-unsafe | 15% | Uses `as any` or `: any` casts |
