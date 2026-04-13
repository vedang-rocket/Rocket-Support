---
name: iterative-retrieval
description: >
  subagent context problem too much context too little context wrong context,
  spawning subagent that needs codebase context, context too large missing context agent task,
  how to give subagent the right files, progressive context refinement multi-agent workflow,
  agent doesn't know which files are relevant, optimize token usage agent orchestration,
  find relevant files before giving to subagent, RAG retrieval for code exploration
globs: []
alwaysApply: false
---

# Skill: Iterative Retrieval Pattern

**When to use**: Before spawning any subagent that needs codebase context it cannot predict upfront.

The fundamental problem: subagents are spawned with limited context. They don't know which files are relevant, what patterns exist, what terminology the project uses. Standard approaches fail — send everything (exceeds limits), send nothing (agent lacks critical info), guess (often wrong).

## The 4-Phase Loop (max 3 cycles)

```
DISPATCH → EVALUATE → REFINE → LOOP
               ↑                  |
               └──────────────────┘
        Stop when: 3+ files score ≥ 0.7 AND no critical gaps
```

### Phase 1 — DISPATCH: Broad initial query

```typescript
// Start with high-level intent, not specific file names
const initialQuery = {
  patterns: ['app/**/*.ts', 'lib/**/*.ts'],
  keywords: ['authentication', 'user', 'session'],
  excludes: ['*.test.ts', '*.spec.ts']
};
```

### Phase 2 — EVALUATE: Score each file 0.0–1.0

- **0.8–1.0**: Directly implements target functionality → keep
- **0.5–0.7**: Contains related patterns or types → keep
- **0.2–0.4**: Tangentially related → maybe
- **0.0–0.2**: Not relevant → exclude immediately

For each file, identify: relevance score + reason + what context is still missing.

### Phase 3 — REFINE: Update search based on gaps

```typescript
// Add terminology discovered in high-relevance files
// Add specific patterns found in codebase (project may use "throttle" not "rate-limit")
// Exclude confirmed irrelevant paths
// Target specific identified gaps
```

### Phase 4 — LOOP: Repeat (max 3 cycles)

Stop early if: 3+ high-relevance files found AND no critical gaps identified.
After 3 cycles: proceed with best context found, noting gaps.

## Rocket.new Application

For a broken Rocket.new project, use this before `/fix-auth` or `/fix-database`:

```
Cycle 1: grep for "getSession\|middleware\|updateSession" → evaluate relevance
Cycle 2: refine to found patterns, search for callers → evaluate
Cycle 3: target specific missing pieces (e.g., the actual callback route)
Result: 4-5 files, all high-relevance, agent has complete picture
```

## Inject into subagent prompts

```
When retrieving context for this task:
1. Start with broad keyword search across app/ and lib/
2. Score each file's relevance 0-1
3. Identify what context is still missing
4. Refine search and repeat (max 3 cycles)
5. Only include files scoring >= 0.7
```

## Why this matters

Without iterative retrieval: agent reads 50 files, 80% irrelevant, burns 40K tokens, misses key file.
With iterative retrieval: agent reads 5 files, all relevant, burns 5K tokens, has complete picture.

**Token savings: 8x typical. Accuracy improvement: significant.**
