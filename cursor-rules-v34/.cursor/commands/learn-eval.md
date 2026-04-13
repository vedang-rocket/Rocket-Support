# Purpose: Extract patterns from this session, evaluate quality before saving

## Usage
/learn-eval

This is the quality-gated version of /reflect.
/reflect saves everything. /learn-eval evaluates first.

## What I Will Do

### Step 1 — Extract raw patterns
Scan this conversation for:
- Corrections you gave me ("no, not that way")
- Accepted fixes (what actually worked)
- MCP queries that revealed something important
- Rocket-specific patterns discovered

### Step 2 — Evaluate each pattern against quality criteria

For each candidate pattern, score it:
```
Quality Criteria:
  [ ] Generalizable? (applies to 2+ projects, not just this one)
  [ ] Specific? (can be acted on — not vague advice)
  [ ] Verified? (was actually tested and confirmed working)
  [ ] New? (not already in rocket-error-fixes.mdc or learned-patterns.md)
  [ ] Rocket-specific? (not generic Next.js knowledge anyone would know)

Score: [count of checked boxes] / 5
```

**Only patterns scoring 3+ get saved.**

### Step 3 — Save approved patterns as instincts

For each approved pattern, create a YAML instinct file:
```yaml
---
id: [slug-from-trigger]
trigger: "[exact trigger phrase]"
confidence: [0.3 for first occurrence / 0.5 if seen twice / scale up]
domain: [auth|database|stripe|deployment|code-patterns|performance]
source: "session-observation"
created: "[today]"
last_seen: "[today]"
evidence_count: 1
---

# [Instinct Title]

## Action
[What to do]

## Evidence
- [today] [project-type]: [what was observed]
```

### Step 4 — Report

```
LEARN-EVAL RESULTS

Candidates found: [n]
Approved (3+/5): [n]
Rejected: [n]

Approved instincts written:
  + [id] → memory-bank/instincts/[id].yaml
  
Rejected (reason):
  - [pattern] → too vague
  - [pattern] → already in rules
```
