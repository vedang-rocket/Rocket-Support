# Cursor Automations — Background Agent Tasks

Automations are agents that run **without you being in Cursor** — triggered by schedules or events.
Different from hooks (which react to file edits), automations run full agent workflows autonomously.

> ⚠️ Automations require Cursor Pro and are configured in Cursor Settings → Automations.
> The files in this folder are the PROMPTS for each automation — copy them into Cursor's UI.

---

## Available Automations (copy prompts into Cursor Settings → Automations)

| File | Trigger | What It Does |
|---|---|---|
| `weekly-security-sweep.md` | Weekly (Monday 9am) | Scans codebase for new security issues |
| `tech-debt-tracker.md` | Weekly (Friday 5pm) | Identifies and logs growing technical debt |
| `dead-code-detector.md` | On demand | Finds unused exports, components, functions |

---

## How to Set Up an Automation in Cursor

1. Open Cursor → Settings → Automations
2. Click "New Automation"
3. Set trigger (schedule or event)
4. Paste the prompt from the relevant file below
5. Set the working directory to your project root
6. Save and enable

---

## Important Notes

- Automations run in a cloud sandbox — they have access to your codebase files
- They do NOT have MCP access by default (MCP is session-specific)
- Results are delivered as comments, files, or notifications depending on configuration
- Start with one automation, verify it works, then add more
- Each automation should be read-only (analysis only) — never configure automations to auto-apply fixes

---

## The Right Mental Model

Automations are not agents that fix your code.
They are agents that **surface what needs attention** so you can fix it efficiently.

The human stays in the loop at the decision layer.
The automation handles the discovery layer.
