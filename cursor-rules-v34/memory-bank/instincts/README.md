# Instincts Directory

Auto-generated YAML instinct files from the continuous learning system.
Each instinct is extracted from observations.jsonl by the /reflect command.

## Instinct File Format

```yaml
---
id: unique-instinct-id
trigger: "when [specific situation occurs]"
confidence: 0.7
domain: "auth|database|stripe|deployment|code-patterns|performance"
source: "session-observation"
created: "YYYY-MM-DD"
last_seen: "YYYY-MM-DD"
evidence_count: 3
---

# Instinct Title

## Action
[What to do when this trigger fires]

## Evidence
- [Session date + project type]: [what happened]

## Counter-evidence
- [Any contradicting observations — reduces confidence]
```

## Confidence Scale
0.9+ = Rock solid | 0.7-0.9 = Strong | 0.5-0.7 = Developing | 0.3-0.5 = Tentative | <0.3 = Weak

## Promotion
When confidence >= 0.9 AND evidence_count >= 5 → promote to rocket-error-fixes.mdc via /reflect
