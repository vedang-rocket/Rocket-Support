# Purpose: View all learned instincts with confidence scores and domain tags

## Usage
/instinct-status

## What I Will Do

1. Read all `.yaml` files in `memory-bank/instincts/`
2. Parse each instinct's frontmatter
3. Display a ranked table sorted by confidence (highest first)
4. Show domains, evidence counts, and promotion readiness
5. Recommend which instincts are ready to promote to permanent rules

## Output Format

```
LEARNED INSTINCTS — [count] total

DOMAIN: auth
  [id] confidence: 0.85 | evidence: 4 | last_seen: 2026-03-15
  Trigger: [trigger phrase]
  Status: [READY TO PROMOTE / DEVELOPING / TENTATIVE]

DOMAIN: database  
  [id] confidence: 0.70 | evidence: 3 | last_seen: 2026-03-18
  Trigger: [trigger phrase]
  Status: DEVELOPING

SUMMARY
  Ready to promote (confidence >= 0.9, evidence >= 5): [count]
  Developing (confidence 0.5-0.9): [count]
  Tentative (confidence < 0.5): [count]
  Total observations in observations.jsonl: [count]
  Sessions with learning data: [count]
```

## If No Instincts Exist Yet

"No instincts captured yet. Run /reflect after a few sessions to begin building your instinct library."

## Next Steps
- Run `/reflect` to extract instincts from recent sessions
- Run `/evolve` to cluster related instincts into a formal skill
- Run `/instinct-export` to share instincts with teammates
