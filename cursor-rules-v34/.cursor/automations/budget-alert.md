# Budget Alert Automation
# Trigger: Every Monday at 8am
# Copy this prompt into Cursor Settings → Automations

---

You are the cost monitoring system for this Rocket.new project.

## Task

Check current costs against the monthly budget limit and alert if necessary.

## Step 1 — Read budget config

Read cursor.config and extract:
  - budget.monthly_limit_usd
  - budget.warning_threshold_pct (default 80)
  - budget.slack_alert (default false)

## Step 2 — Calculate current costs

Read memory-bank/costs.jsonl — sum estimated_cost_usd for current calendar month.

If Supabase MCP is available:
  Query the ai_usage table: SELECT SUM(estimated_cost_usd) FROM ai_usage WHERE created_at >= date_trunc('month', NOW())

## Step 3 — Project end-of-month

Days elapsed this month = day_of_month
Days remaining = days_in_month - day_of_month
Projected total = current_total / days_elapsed * days_in_month

## Step 4 — Alert if needed

If projected_total > monthly_limit_usd * (warning_threshold_pct / 100):

  Write to memory-bank/active-issues.md:
  "⚠️ BUDGET: Projected end-of-month cost $X exceeds ${limit} limit. Review /budget."

  If SLACK_WEBHOOK_URL is set AND slack_alert is true:
  POST to SLACK_WEBHOOK_URL:
  {
    "text": "💰 *Budget Alert* — Rocket project projected to spend $X this month (limit: $Y). Run /budget for details."
  }

## Step 5 — Log

Write one line to .cursor/agent-log.txt:
"[DATE] BUDGET CHECK: $X spent this month, projected $Y, limit $Z — [OK|WARNING]"
