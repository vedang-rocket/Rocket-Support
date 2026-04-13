# Purpose: Generate a clean handoff report when returning a fixed project to the user

Run this when you've finished working on a project and are handing it back.
Produces two outputs: a technical summary for your records, and a plain-English summary for the user.

## What I Need Before Writing the Report

I will read from (in order of priority):
1. The current session conversation — what was discussed and changed
2. `memory-bank/fixes-applied.md` — what was fixed this session
3. `memory-bank/active-issues.md` — what's resolved vs still open
4. `.cursor/security-log.md` — if security audit was run
5. `.cursor/agent-log.txt` — which files were edited

**If memory-bank files are empty (common on first session):**
I will ask you 3 questions before writing:
1. "What was the user's reported problem?"
2. "What did you find was actually broken (root cause)?"
3. "What did you fix, and which files changed?"

I will NOT generate a vague report. If I don't have enough information, I ask first.

---

## OUTPUT 1 — Technical Summary (for your records)

```markdown
# Project Technical Handoff
Date: [today]
Project: [folder/project name]
Session duration: [estimate from conversation length]

## What Was Broken (Root Causes)
[Not symptoms — actual root causes identified]
- [Root cause 1] — found via [how: MCP query / code scan / error message]
- [Root cause 2]

## What Was Fixed
| Issue | Root Cause | Files Changed | Verified |
|---|---|---|---|
| [issue] | [cause] | [files] | [yes/no] |

## What Was NOT Fixed (Still Open)
| Issue | Why Not Fixed | Recommended Next Step |
|---|---|---|
| [issue] | [reason] | [what to do] |

## Security Findings
[From /security-audit if run, or "Not audited this session"]

## Performance Findings  
[From /fix-performance if run, or "Not audited this session"]

## Before Going Live — Checklist
[Generated based on what was found/fixed]
□ [Item specific to this project]
□ [Item]

## Supabase State
- Tables confirmed: [list]
- RLS: [status]
- Profile trigger: [exists/missing]
- Migrations: [pushed/pending]

## Env Vars Status
- .env.local: [complete/missing vars]
- Netlify: [configured/not configured]
```

---

## OUTPUT 2 — User-Facing Summary (plain English, no jargon)

```
Hi [user],

Here's a summary of what I did on your project:

✅ FIXED
[Plain English description — what the user will now experience differently]
Example: "Your login with Google now works correctly. Users will be able to sign in with their Google account and be taken to the dashboard."

⚠️ STILL NEEDS ATTENTION
[Things that need action before going live — written for non-developers]
Example: "Before you launch, you'll need to add your Stripe live keys in Netlify. Right now it's set up for testing only."

📋 BEFORE YOU GO LIVE
[Numbered checklist in plain English]
1. [Action the user needs to take]
2. [Action]

💡 ONE THING TO KNOW
[The single most important thing the user should understand about their project]
Example: "Your Supabase project is on the free tier, which pauses after 7 days of no activity. Upgrading to Supabase Pro ($25/month) prevents this."

Let me know if anything isn't working as expected.
```

---

## Hard Constraints
- Technical summary: precise, factual, no padding
- User summary: zero technical jargon — if you must use a technical term, explain it in brackets
- Never mark something as "fixed" unless it was verified (tested or confirmed via MCP)
- "Still needs attention" must include a specific recommended next step — never vague
- The user-facing summary should be readable by someone who has never written code
