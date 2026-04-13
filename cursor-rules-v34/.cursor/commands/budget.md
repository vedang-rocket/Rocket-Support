---
description: Show current cost breakdown across Supabase, OpenAI, and Stripe. Compare against your monthly budget limit. View trends and projections.
---

# /budget

Show your current costs, trends, and budget status.

## What it shows

```
Budget Dashboard — [current month]

━━━ Current Costs ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Cursor AI sessions:     $8.20   (from memory-bank/costs.jsonl)
  OpenAI API calls:       $12.40  (from ai_usage table)
  Edge Function calls:    $0.60   (Supabase MCP — invocations × $0.000002)
  Realtime connections:   $0.00   (within free tier — 45 active channels)
  Storage + egress:       $1.20   (Supabase — 14GB stored, 6GB egress)
  Auth MAU:               $0.00   (180 MAU — within free 50K)
  Stripe fees:            $3.10   (from Stripe MCP — 2.9% of $107 processed)

  Total this month:       $23.70
  Budget limit:           $50.00
  Remaining:              $26.30 (53%)

━━━ Trends ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Day 12 of 31 — on track
  Projected end-of-month: ~$61.20 ⚠️  (exceeds budget)
  Largest cost driver: OpenAI API calls (52%)

━━━ Top cost sources ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  1. app/api/chat/route.ts              — $9.80 (GPT-4o-mini, 4.9K calls)
  2. cursor sessions (claude-sonnet)    — $8.20 (this month)
  3. supabase/functions/embed-section/  — $2.60 (text-embedding-3-small)
  4. Realtime channels (from Chat.tsx)  — watching (3 active channels → 0 cost now)
  5. Storage egress (profile-images/)   — $1.20 (6GB × $0.09/GB)

━━━ Budget Settings ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Monthly limit: $50 (set in cursor.config)
  Warning at:    $40 (80%)
  Auto-alert to: Slack (SLACK_WEBHOOK_URL)

  To change: edit cursor.config → "budget" section
```

## How to set your budget

Edit `cursor.config`:

```json
{
  "budget": {
    "monthly_limit_usd": 50,
    "warning_threshold_pct": 80,
    "block_threshold_pct": 100,
    "slack_alert": true
  }
}
```

## Data sources

- Cursor AI costs: `memory-bank/costs.jsonl` (written by sessionEnd hook)
- OpenAI costs: `ai_usage` table in Supabase (written by `trackAIUsage` in `rocket-supabase-observability.mdc`)
- Stripe: Stripe MCP `retrieve_balance` and `list_charges`
- Supabase: Supabase MCP + Dashboard API

## Related

- `/budget` — this command
- The weekly Budget Alert automation sends a Slack message when costs approach the limit
