# Skill: estimate-cost

Estimate the monthly cost impact of code changes before committing them.
Pulls real usage from Supabase metrics, Stripe, and OpenAI, then analyses
the diff for 12 cost-impacting patterns to predict monthly delta.

---

## When to use

Triggered automatically by `beforeShellExecution` on `git commit` or `git push`.
Also callable manually via `/budget`.

---

## Step 1 — Fetch current usage

### Supabase (via Supabase MCP)
```sql
SELECT
  pg_size_pretty(pg_database_size(current_database())) AS db_size,
  pg_database_size(current_database())                 AS db_bytes,
  (SELECT count(*) FROM pg_stat_activity)              AS active_connections
```
Also fetch from Dashboard API if SUPABASE_ACCESS_TOKEN is set:
  - Edge Function invocations this month
  - Storage GB used + egress GB
  - Auth MAU count

### OpenAI costs
Sum `estimated_cost_usd` from `memory-bank/costs.jsonl` for the current calendar month.
Also query the `ai_usage` table via Supabase MCP if accessible.

### Stripe revenue (context only)
If Stripe MCP is available: fetch MRR and transaction fees this month.

---

## Step 2 — Analyse the diff

Run `git diff --cached` (pre-commit) or `git diff HEAD~1` (post-commit) to get the diff.

Scan for these 12 cost-impacting patterns (baseline: 1,000 MAU, 10 actions/user/day = ~300K req/month):

### LLM / AI patterns

| Pattern | Detection | Monthly delta estimate |
|---|---|---|
| New OpenAI chat call | `openai.chat.completions.create` or `generateText\|streamText` import | +$1–15/1K calls depending on model |
| Model upgrade | `gpt-4o` or `claude-opus` replacing cheaper model | +3–10× per call — HIGH IMPACT |
| New embedding call | `embeddings.create` or `generateEmbedding` | +$0.02/1M tokens (negligible at small scale) |

### Supabase patterns

| Pattern | Detection | Monthly delta estimate |
|---|---|---|
| New query without index | `supabase.from(` without matching `CREATE INDEX` in diff | +latency cost — recommend index |
| New Realtime channel | `.channel(` or `supabase.channel` | +1 concurrent connection per active user |
| New Storage upload | `.storage.` + `.upload(` | +$0.021/GB/month + $0.09/GB egress |
| New auth signup path | `supabase.auth.signUp` in a publicly accessible route | +potential MAU increase → tier change |
| Large batch upsert | `.upsert([` with array literal >100 items | high write amplification — consider chunking |

### Infrastructure patterns

| Pattern | Detection | Monthly delta estimate |
|---|---|---|
| New Edge Function invocation | `supabase.functions.invoke(` | +$0.000002/invocation (~$0.60/300K calls) |
| New API route | new `export async function` in `app/api/` | +N function invocations/month |
| New `cron.schedule` job | `cron.schedule(` in SQL or Supabase CLI | +fixed invocations/month based on interval |
| Removing a pattern | any of the above being deleted | cost reduction — note as savings |

---

## Step 3 — Produce the cost delta report

```
━━━ Cost Impact Analysis — [timestamp] ━━━━━━━━━━━━━━━━━━━━━

Current monthly (estimated):
  Cursor AI sessions:    $8.20   (costs.jsonl, this month)
  OpenAI API:            $12.40  (ai_usage table)
  Supabase:              $0.00   (free tier — 180MB / 500MB, 45K / 500K fn invocations)
  Stripe fees:           $3.10   (2.9% of $107 processed)
  ──────────────────────────────
  Total current:         ~$23.70/month

Changes detected in diff:
  + NEW: supabase.functions.invoke('embed-section') in app/api/ingest/route.ts
    Pattern: edge-function-invocation
    Estimate: ~$0.60/month at 300K invocations
    Confidence: medium

  + NEW: supabase.channel('room:') in components/Chat.tsx
    Pattern: realtime-subscription
    Estimate: +1 connection per active user — watch Supabase Realtime limits
    Confidence: high

  + MODEL UPGRADE: gpt-4o replacing gpt-4o-mini in app/api/chat/route.ts
    Pattern: model-upgrade
    Estimate: ~+$45.00/month (15× cost increase at current volume)
    Confidence: high  ⚠️ SIGNIFICANT INCREASE

  - REMOVED: Old embedding call in lib/search.ts
    Pattern: embedding-removed
    Saving: ~$0.10/month

Projected new total: ~$69.00/month
Budget limit:        $50/month
Budget headroom:     -$19.00  ⚠️ OVER BUDGET

━━━ Recommendation ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

The model upgrade from gpt-4o-mini to gpt-4o will push costs 38% over budget.
Consider: keeping gpt-4o-mini for most calls, using gpt-4o only for complex tasks.
Pass --no-cost-check to git commit/push to skip this check.
```

---

## Step 4 — Budget threshold check

Read `cursor.config` for budget settings:
```json
{
  "budget": {
    "monthly_limit_usd": 50,
    "warning_threshold_pct": 80,
    "block_threshold_pct": 100
  }
}
```

- Projected > warning_threshold (default $40): print yellow `⚠️ Approaching budget`
- Projected > block_threshold (default $50): print red `❌ OVER BUDGET` with specific recommendation
- Significant single-pattern increase (>$20/month): always flag regardless of threshold

---

## Output

Return the full cost delta report as a string.
Append a JSONL row to `memory-bank/costs.jsonl`:
```json
{
  "timestamp": "2026-03-01T09:00:00Z",
  "event": "commit-estimate",
  "delta_usd": 45.30,
  "projected_total_usd": 69.00,
  "patterns_found": ["edge-function-invocation", "realtime-subscription", "model-upgrade"],
  "over_budget": true
}
```
