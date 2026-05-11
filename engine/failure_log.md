# Agent Failure Log

Every entry = one real failure + permanent fix applied to harness.
This is a ratchet. System never makes the same mistake twice.

## How to add an entry
When a fix goes wrong:
1. Document what Claude did wrong (exactly)
2. Document what rule prevents it next time
3. Document where that rule now lives
4. Apply the rule immediately — do not wait

## Entry format
---
Date: YYYY-MM-DD
Ticket: <threadId or DC-XXX>
Confidence: HIGH/MED/LOW
Category: AUTH/STRIPE/SUPABASE/BUILD/ENV

What Claude did wrong:
<exact description — be specific, not vague>

Example of bad output:
<paste the actual bad code Claude generated>

What it should have done:
<paste what correct output looks like>

Root cause of failure:
<why did Claude make this mistake — context too wide / prompt too loose / wrong file / etc>

Permanent fix applied:
<what was changed in harness to prevent this>

Where rule now lives:
[ ] claude_agent.py prompt
[ ] probe_scanner.py new rule
[ ] chain_walker.py new chain
[ ] CLAUDE.md hard rule
[ ] agent_loop.py constraint
[ ] Other: ___

Verified: does system no longer make this mistake? YES/NO
---

## Known failures so far

---
Date: 2026-05-11
Ticket: general observation
Confidence: ALL
Category: ALL

What Claude did wrong:
Applied multi-line changes when only one line needed changing.
Reformatted surrounding code. Changed variable names. Added comments.
Fix looked correct but broke other parts of file.

What it should have done:
Changed exactly one line. Left everything else identical.

Root cause of failure:
Prompt said "change only broken lines" but Claude interprets
"broken" loosely and makes additional "helpful" changes.

Permanent fix applied:
- Added 7-line minimal context window (_extract_minimal_context)
- Added _verify_change_safe() pre-apply check
- Prompt now says "old field must be EXACT content of broken line"
- Maximum 3 changes total enforced in prompt

Where rule now lives:
[x] claude_agent.py prompt
[x] claude_agent.py _verify_change_safe()
[x] claude_agent.py _extract_minimal_context()

Verified: YES — implemented in current codebase
---
