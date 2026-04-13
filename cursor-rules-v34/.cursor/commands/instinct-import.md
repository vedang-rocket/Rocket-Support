# Purpose: Import instincts from a teammate or exported file

## Usage
/instinct-import [filename]
Example: /instinct-import instincts-export-2026-03-19.yaml

## What I Will Do

1. Read the provided YAML export file
2. Check for conflicts with existing instincts (same id)
3. For conflicts: keep the one with higher confidence, or ask if equal
4. Write each instinct as a separate `.yaml` file in `memory-bank/instincts/`
5. Mark imported instincts with `source: "imported"` in frontmatter
6. Report what was imported, skipped, and merged

## Output Format

```
IMPORT RESULTS from [filename]

Imported: [n] new instincts
  + [id] (confidence: [score], domain: [domain])
  + [id] (confidence: [score], domain: [domain])

Skipped (already have higher-confidence version): [n]
  ~ [id] (yours: 0.85 > import: 0.70 — keeping yours)

Merged (same id, averaged confidence): [n]
  ≈ [id] (0.80 + 0.75 → 0.78)

Total instincts now: [n]
```

## Safety
- Never overwrites a higher-confidence instinct with a lower one
- Never deletes existing instincts
- Always additive — worst case is a new instinct that doesn't match your workflow
