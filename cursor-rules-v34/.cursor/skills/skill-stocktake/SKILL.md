---
name: skill-stocktake
description: >
  audit cursor skills quality, review skills and commands, which skills are outdated,
  which skills overlap, which skills should be retired, skill quality review,
  skill inventory check, too many skills remove duplicates, skills not working,
  review all commands quality check, find outdated technical references in skills,
  skills redundant merge, skill coverage gaps
globs: []
alwaysApply: false
---

# Skill: Skill Stocktake — Audit Your Skills System

**When to use**: When the skill library feels bloated, when skills seem outdated, or as a periodic quality check (monthly recommended).

## Phase 1 — Inventory

```bash
# Count all skills
ls .cursor/skills/ | wc -l
echo "Skills:"
ls .cursor/skills/

# Count all commands
ls .cursor/commands/*.md | wc -l
echo "Commands:"
ls .cursor/commands/*.md | xargs -I{} basename {}

# Check last modified dates
ls -la .cursor/skills/*/SKILL.md | sort -k6,7
```

## Phase 2 — Evaluate Each Skill Against This Checklist

For each skill, answer:
```
[ ] Unique value — not covered by AGENTS.md rules or another skill?
[ ] Actionable — has concrete steps, code examples, or commands?
[ ] Current — technical references still work (packages exist, APIs unchanged)?
[ ] Right scope — trigger phrases match when you actually need it?
[ ] No significant overlap with another skill?
```

**Verdict options**:
- **Keep** — useful, current, unique
- **Improve** — worth keeping, specific changes needed (what section, what to change)
- **Merge into [X]** — overlaps substantially with X (specify what content to integrate)
- **Retire** — outdated, superseded, or no unique value

## Phase 3 — V20 Skill Health Check

Current skills that need monitoring:

| Skill | Watch For |
|---|---|
| `fix-auth-flow` | getUser() vs getSession() still current? |
| `fix-supabase-rls` | RLS SQL patterns match current Supabase version? |
| `fix-env-variables` | env var names match current Rocket template? |
| `fix-stripe` | Stripe API / webhook patterns still current? |
| `fix-deployment` | Netlify config patterns current? |
| `implement-feature` | 7-step procedure still matches Rocket stack? |
| `iterative-retrieval` | NEW — verify useful after first 5 projects |
| `search-first` | NEW — verify trigger phrases load correctly |

## Phase 4 — Consolidation

For each **Retire** verdict:
- State what specific problem was found (outdated, overlap, broken reference)
- State what covers the same need instead
- Confirm with user before deleting

For each **Merge** verdict:
- State which content from the retiring skill to integrate into the target
- State which content to discard

For each **Improve** verdict:
- State specifically what to change (line numbers if possible, target size)
- User decides whether to act

## Quality Standards

Good skill properties:
- Under 300 lines (skills are procedures, not encyclopedias)
- At least 3 concrete code examples or commands
- Description has 8+ trigger phrases matching real user language
- `globs` field present for file-type-specific skills
- No content that duplicates `rocket-cursor-behavior.mdc` rules

Red flags:
- Skill description matches no realistic user message
- All content is already in a rule file
- Technical references that haven't been verified in 3+ months
- Over 500 lines with no clear sections
