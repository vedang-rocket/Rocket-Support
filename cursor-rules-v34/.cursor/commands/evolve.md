# Purpose: Cluster related instincts into a formal reusable skill

## Usage
/evolve [domain] (optional)
Examples:
  /evolve           — analyze all instincts for cluster opportunities
  /evolve auth      — cluster only auth-domain instincts
  /evolve database  — cluster only database-domain instincts

## What I Will Do

1. Read all YAML files in `memory-bank/instincts/`
2. Identify clusters: instincts that fire in similar situations or share a domain
3. For each cluster with 3+ instincts:
   - Propose a new SKILL.md that encodes all clustered instincts as a procedure
   - Show the proposed SKILL.md content
   - Ask for confirmation before writing
4. Write confirmed skills to `.cursor/skills/[skill-name]/SKILL.md`
5. Mark source instincts as `[EVOLVED → skill-name]`

## Cluster Detection Logic

Instincts cluster when they share:
- Same `domain` tag AND similar `trigger` phrases
- Evidence from the same project types
- Complementary actions (step A → step B → step C pattern)

## Example Cluster → Skill

Three auth instincts:
- "when middleware.ts missing" → check root location
- "when getSession() in server code" → replace with getUser()
- "when profile trigger missing" → run backfill SQL

Evolves into: `.cursor/skills/fix-auth-rapid/SKILL.md`
A streamlined skill combining all three checks in sequence.

## Output

```
EVOLUTION ANALYSIS

Cluster 1 — auth (4 instincts, avg confidence: 0.78)
  Instincts: middleware-location, getSession-server, profile-trigger, oauth-localhost
  Proposed skill: fix-auth-rapid/
  Action: [y/n]?

Cluster 2 — database (3 instincts, avg confidence: 0.72)
  Instincts: rls-empty-array, missing-migration, wrong-client
  Proposed skill: fix-database-rapid/
  Action: [y/n]?
```
