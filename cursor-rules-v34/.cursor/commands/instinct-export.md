# Purpose: Export your learned instincts to a shareable file

## Usage
/instinct-export

## What I Will Do

1. Read all YAML files in `memory-bank/instincts/`
2. Filter to instincts with confidence >= 0.5 (tentative or stronger)
3. Bundle them into a single `instincts-export-[date].yaml` file
4. Save to project root for sharing

## Export Format

```yaml
# ECC Instinct Export
# Generated: [date]
# Source: [project type / workflow context]
# Confidence threshold: 0.5+

instincts:
  - id: [id]
    trigger: "[trigger]"
    confidence: [score]
    domain: [domain]
    evidence_count: [n]
    action: |
      [what to do]
    
  - id: [id2]
    ...
```

## Output

"Exported [n] instincts to `instincts-export-[date].yaml`
Share this file with teammates who run /instinct-import to load your learned patterns."

## Sharing Workflow
1. You run `/instinct-export` → get `instincts-export-2026-03-19.yaml`
2. Share that file with teammate
3. Teammate runs `/instinct-import instincts-export-2026-03-19.yaml`
4. Teammate's system now has your proven patterns instantly
