# Purpose: Extract deep learnings from this session and write them permanently to the knowledge base

This is the most important command in the system.
Run it at the end of any session where something interesting happened.
It turns your experience into permanent intelligence.

## What I Will Do

1. Review everything that happened in this conversation
2. Extract every mistake I made and every correction you gave me
3. Extract every pattern that worked well
4. Write actionable patterns as YAML instinct files to `memory-bank/instincts/[id].yaml`
5. Write session summary to `memory-bank/learned-patterns.md`
6. Check if any YAML instincts have confidence >= 0.9 + evidence >= 5 → auto-promote to permanent rules
7. Check if any markdown `[MISTAKE]` entries have COUNT: 3 → promote to rules
8. Update the stats in learned-patterns.md

**Prefer YAML instincts for specific, actionable patterns.**
Use `memory-bank/learned-patterns.md` for general session summaries and soft observations.

---

## YAML Instinct Format (write this for actionable patterns)

```yaml
---
id: [slug-from-trigger-phrase]
trigger: "when [specific situation]"
confidence: 0.5
domain: "auth|database|stripe|deployment|code-patterns|performance"
source: "session-observation"
created: "[today YYYY-MM-DD]"
last_seen: "[today YYYY-MM-DD]"
evidence_count: 1
---

# [Instinct Title]

## Action
[Exactly what to do when this trigger fires]

## Evidence
- [today] [project-type]: [what was observed that supports this]
```

Write each instinct to: `memory-bank/instincts/[id].yaml`
If the instinct file already exists: increment `evidence_count`, update `last_seen`,
add new evidence line, recalculate confidence (more evidence = higher confidence).

## My Reflection Process

### Step 1 — Scan this conversation for learning signals

I will look for:
```
- Any time you said "no", "that's wrong", "not like that", "use X instead"
  → This is a MISTAKE to capture

- Any time you said "yes", "perfect", "exactly", "that worked"
  → This is a PATTERN to reinforce

- Any error that was found and fixed
  → Root cause + fix to capture

- Any MCP query that revealed something the code didn't show
  → MCP insight to capture

- Any Rocket-specific quirk discovered in this codebase
  → Project-specific pattern to capture
```

### Step 2 — Write MISTAKE entries

For each mistake found:
```markdown
### [YYYY-MM-DD] [project-type] — [short title]
[MISTAKE] I suggested: [exact wrong suggestion]
[CORRECT] Right answer: [what was actually right]
[WHY] I got this wrong because: [root cause of my error]
[CONTEXT] When this applies: [scenario/project type]
[COUNT: 1]
```

### Step 3 — Write PATTERN entries

For each confirmed working pattern:
```markdown
### [pattern name]
[PATTERN] [what works and why]
[APPLIES TO] [all Rocket projects / SaaS only / specific scenario]
[EVIDENCE] Worked in: [project name/type]
[COUNT: 1]
```

If this pattern already exists in the file, increment its COUNT.

### Step 4 — Write Session Summary

```markdown
### [YYYY-MM-DD] Session — [project name] ([project type])
**Fixed**: [what was broken and what fixed it]
**Root cause**: [the actual underlying cause]
**Key insight**: [the one thing worth remembering from this session]
**MCP value**: [what the live database revealed that code analysis couldn't]
**Mistakes avoided** (from previous sessions): [list if any]
**New mistakes captured**: [count]
**Patterns reinforced**: [count]
```

### Step 5 — Check for promotions

After writing all entries, scan for any pattern with COUNT: 3 or more.

For each one ready for promotion:
1. Run `/capture-convention` with the pattern
2. The rule gets added to `rocket-error-fixes.mdc` permanently
3. Update the entry: add `[PROMOTED: rocket-error-fixes.mdc — YYYY-MM-DD]`
4. Add to PROMOTION LOG section

### Step 6 — Update stats

```
Sessions recorded: [increment by 1]
Mistakes captured: [increment by new mistakes]
Patterns confirmed: [increment by new patterns]
Rules promoted: [increment if any promoted]
Last updated: [today's date]
```

### Step 7 — Run promotion check script

```bash
sh .cursor/hooks-scripts/promote-to-rule.sh
```

Report what was found.

---

## Output Format

After completing all steps, report:

```
✅ Session learning captured

Mistakes captured: X new
Patterns reinforced: X
Session summary: written
Patterns ready for promotion: X

memory-bank/learned-patterns.md updated.
Total sessions recorded: N
Total mistakes in knowledge base: N
Total patterns confirmed: N
Total rules auto-promoted: N

[If any promotions happened]:
🚀 PROMOTED to rocket-error-fixes.mdc:
  - "[pattern name]" — seen X times across X projects
```

---

## Hard Constraints

- Never delete existing entries — only add and increment counts
- Never write vague entries — every mistake needs the exact wrong suggestion and exact right answer
- Never skip the stats update — the counters matter for promotion tracking
- If nothing interesting happened this session — write "Session [date]: No new patterns. Reviewed [X] files." and exit
