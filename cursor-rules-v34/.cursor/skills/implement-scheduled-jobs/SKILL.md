---
name: implement-scheduled-jobs
description: >
  schedule recurring job supabase, pg_cron schedule task database,
  run function every day supabase, clean up old data automatically postgres,
  trigger edge function on schedule supabase, pg_net call edge function cron,
  background job supabase nextjs, delete expired records automatically,
  send scheduled email from database, cron job not running supabase debug,
  pgmq background queue jobs postgres, schedule task every hour supabase
globs: ["**/*.sql", "**/*.ts"]
alwaysApply: false
---

# Skill: Implement Scheduled Jobs (pg_cron + pg_net)

**Stack**: Supabase pg_cron + pg_net + Edge Functions
**When to use**: Any recurring task — cleanup, notifications, sync, background processing.

---

## Supabase Cron Dashboard Module (Recommended)

Supabase Cron is now a first-class Dashboard module — use it instead of raw SQL when possible.

```
Dashboard → Integrations → Cron → Add New Job

Four job types:
1. SQL Snippet     — run any SQL directly
2. DB Function     — call a Postgres function
3. Edge Function   — HTTP call to your Edge Function
4. Remote Webhook  — HTTP POST to any external URL

Natural language schedule: "every day at 9am" → auto-converts to cron syntax
Cron syntax: standard 5-field (*/5 * * * *) OR sub-minute (*/10 * * * * *)
```

## Sub-Minute Scheduling (New in 2024)

```sql
-- Standard 5-field cron: minimum = every minute
-- 6-field cron with seconds: minimum = every 1 second

-- Every 10 seconds
SELECT cron.schedule('process-queue', '*/10 * * * * *', $$ SELECT 1; $$);

-- Every 30 seconds
SELECT cron.schedule('sync-cache', '*/30 * * * * *', $$ SELECT 1; $$);

-- Every 5 seconds (fastest practical rate — max 8 concurrent jobs)
SELECT cron.schedule('embedding-worker', '*/5 * * * * *', $$ SELECT 1; $$);
```

---

## Enable Required Extensions

```sql
-- pg_cron is pre-installed on all Supabase projects
-- pg_net may need enabling:
CREATE EXTENSION IF NOT EXISTS pg_net WITH SCHEMA extensions;
```

---

## Pattern A — Simple SQL Job (no Edge Function needed)

Best for: deleting old records, updating status fields, aggregating data.

```sql
-- Delete sessions older than 30 days, runs every day at 3am UTC
SELECT cron.schedule(
  'cleanup-expired-sessions',     -- unique job name
  '0 3 * * *',                    -- cron expression
  $$
  DELETE FROM user_sessions
  WHERE expires_at < NOW() - INTERVAL '30 days';
  $$
);

-- More examples:
-- Archive old notifications (move to archive table)
SELECT cron.schedule('archive-old-notifications', '0 2 * * *', $$
  INSERT INTO notifications_archive SELECT * FROM notifications WHERE created_at < NOW() - INTERVAL '90 days';
  DELETE FROM notifications WHERE created_at < NOW() - INTERVAL '90 days';
$$);

-- Reset daily usage counters at midnight
SELECT cron.schedule('reset-daily-counters', '0 0 * * *', $$
  UPDATE users SET daily_api_calls = 0;
$$);
```

---

## Pattern B — Trigger an Edge Function on Schedule

Best for: sending emails, calling external APIs, complex business logic.

### Step 1 — Create the Edge Function
```typescript
// supabase/functions/daily-digest/index.ts
import { createClient } from 'jsr:@supabase/supabase-js@2'

Deno.serve(async (req: Request) => {
  // Use service role to bypass RLS for admin operations
  const supabase = createClient(
    Deno.env.get('SUPABASE_URL')!,
    Deno.env.get('SUPABASE_SERVICE_ROLE_KEY')!
  )

  // Get users who want daily digest
  const { data: users } = await supabase
    .from('profiles')
    .select('id, email')
    .eq('daily_digest_enabled', true)

  for (const user of users ?? []) {
    // Send digest email via Resend / your email provider
    await fetch('https://api.resend.com/emails', {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${Deno.env.get('RESEND_API_KEY')}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        from: 'digest@yourdomain.com',
        to: user.email,
        subject: 'Your Daily Digest',
        html: '<p>Here is your digest...</p>',
      }),
    })
  }

  return new Response(JSON.stringify({ processed: users?.length ?? 0 }), {
    headers: { 'Content-Type': 'application/json' },
  })
})
```

```bash
# Deploy
supabase functions deploy daily-digest --project-ref [YOUR_REF]
```

### Step 2 — Schedule it with pg_cron
```sql
-- Runs every day at 8am UTC
SELECT cron.schedule(
  'send-daily-digest',
  '0 8 * * *',
  $$
  SELECT net.http_post(
    url := 'https://[PROJECT_REF].functions.supabase.co/daily-digest',
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'Authorization', 'Bearer [YOUR_ANON_KEY]'
    ),
    body := jsonb_build_object('triggered_by', 'cron', 'time', NOW()::TEXT)
  ) AS request_id;
  $$
);
```

---

## Cron Expression Reference

```
* * * * *
│ │ │ │ └── day of week (0=Sun, 6=Sat)
│ │ │ └──── month (1-12)
│ │ └────── day of month (1-31)
│ └──────── hour (0-23) — always UTC!
└────────── minute (0-59)

Common patterns:
'* * * * *'       every minute
'*/5 * * * *'     every 5 minutes
'0 * * * *'       every hour (on the hour)
'0 */6 * * *'     every 6 hours
'0 3 * * *'       every day at 3am UTC
'0 9 * * 1'       every Monday at 9am UTC
'0 0 1 * *'       1st of every month at midnight
'0 0 * * 0'       every Sunday at midnight
```

> Supabase Dashboard shortcut: Integrations → Cron → "natural language" input

---

## Manage Jobs

```sql
-- List all scheduled jobs
SELECT jobid, jobname, schedule, command FROM cron.job ORDER BY jobid;

-- Check recent run history (success/fail)
SELECT job_id, status, start_time, end_time, return_message
FROM cron.job_run_details
WHERE start_time > NOW() - INTERVAL '24 hours'
ORDER BY start_time DESC;

-- Pause a job (keeps it but stops running)
UPDATE cron.job SET active = false WHERE jobname = 'my-job-name';

-- Resume
UPDATE cron.job SET active = true WHERE jobname = 'my-job-name';

-- Delete a job permanently
SELECT cron.unschedule('my-job-name');
```

---

## Debugging a Job That Isn't Running

```sql
-- 1. Check the job exists
SELECT * FROM cron.job WHERE jobname = 'your-job-name';

-- 2. Check recent failures
SELECT status, return_message, start_time
FROM cron.job_run_details
WHERE status = 'failed'
ORDER BY start_time DESC LIMIT 10;

-- 3. Confirm pg_cron worker is running
SELECT pid, state FROM pg_stat_activity WHERE application_name = 'pg_cron_scheduler';
-- If no row: go to Dashboard → Settings → Restart database

-- 4. Test the job command manually in SQL Editor
-- Copy the $$ ... $$ command from cron.job and run it directly
```

---

## Limits
- Max 8 jobs running at the same time
- Each job max runtime: 10 minutes
- Minimum interval: 1 second (use `* * * * * *` for seconds)
- Always UTC timezone — convert in your app if displaying to users
- Max 8 jobs running CONCURRENTLY across all scheduled jobs
- Max job runtime: 10 minutes (pg_cron kills the job after this)
- Sub-minute jobs (seconds syntax) share the same 8-job concurrency limit
- If 8 jobs are running and a 9th triggers → it is SKIPPED (not queued)
- Monitor skipped jobs: SELECT * FROM cron.job_run_details WHERE status = 'failed' ORDER BY end_time DESC
