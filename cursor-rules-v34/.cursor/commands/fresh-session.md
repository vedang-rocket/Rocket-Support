# Purpose: Save current session state and start fresh — eliminates context noise from long conversations

After 10+ exchanges, conversation history becomes the biggest token consumer.
Each turn adds 500-2K tokens. A 20-turn session spends 40K tokens on history alone.
/fresh-session captures what matters and discards the noise.

## When to Use
- Session has gone 10+ exchanges
- Agent is giving worse answers than it did earlier (context drift)
- Switching from debugging to a completely different task
- Agent went off-rails and you've reverted
- You feel like you're re-explaining things you already said

## What I Will Do

### Step 1 — Write session summary to `memory-bank/session-summary.md`

```markdown
# Session Summary — [YYYY-MM-DD HH:MM]

## What We Were Working On
[project name] — [project type]

## What Was Fixed This Session
[bullet list of each fix with file names]

## Root Causes Found
[what was actually broken and why]

## Current State
[what's working now, what's still broken]

## Files Changed
[list of every file edited]

## What To Do Next
[the specific next step — what to start the fresh session with]

## Patterns Discovered
[anything worth adding to learned-patterns.md]

## Open Questions
[anything unresolved that needs attention]
```

### Step 2 — Write to learned-patterns.md if any patterns discovered

If this session revealed a new pattern → write it to `memory-bank/learned-patterns.md` now, before the context is lost.

### Step 3 — Output the fresh session starter

After writing the summary, output this exact block:

```
╔══════════════════════════════════════════╗
║         FRESH SESSION READY              ║
╚══════════════════════════════════════════╝

Session summary saved to: memory-bank/session-summary.md

To start fresh, open a new chat and paste this opener:
─────────────────────────────────────────
Rocket.new Next.js project. Continuing from previous session.

Context: @memory-bank/session-summary.md

Current task: [EXACT NEXT STEP FROM SUMMARY]

Relevant files: @[file1] @[file2]
─────────────────────────────────────────

Token savings from this reset: ~[estimate based on conversation length]K tokens
```

---

## Token Savings Estimate

| Conversation Length | Tokens Saved by Reset |
|---|---|
| 10 exchanges | ~15K tokens |
| 20 exchanges | ~35K tokens |
| 30 exchanges | ~60K tokens |
| 50+ exchanges | ~100K+ tokens |

The summary is ~500 tokens. The history it replaces is 15-100K tokens.
**That's 30-200x compression of the same essential information.**

---

## Hard Constraints
- Never lose information — write everything important to session-summary.md BEFORE recommending fresh start
- The fresh session opener must be specific enough to continue without re-explaining
- If patterns were discovered → write them to learned-patterns.md NOW (not "I'll do it later")
- The summary must answer: "If a different AI read only this file, could it continue the work?" If no → add more detail
