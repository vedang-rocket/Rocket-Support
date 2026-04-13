# Purpose: Audit the entire .cursor/ configuration for reliability, completeness, and risk

## Usage
/harness-audit

## What I Will Do

Run a comprehensive self-assessment of the configuration system itself.

### Phase 1 — Rules Health
```bash
# Count always-on rules (should be exactly 2)
grep -l "alwaysApply: true" .cursor/rules/*.mdc | wc -l

# Check for rules over 500 lines
wc -l .cursor/rules/*.mdc | sort -rn | head -10

# Check all rules have descriptions
grep -L "^description:" .cursor/rules/*.mdc
```

### Phase 2 — MCP Connection Status
Test each MCP server:
- Supabase: call `list_tables` — confirm tools appear
- Stripe: call `balance.read` — confirm tools appear
- Memory: call `search_nodes` with "test" — confirm tools appear

### Phase 3 — Hooks Verification
```bash
# Confirm hooks scripts are executable
ls -la .cursor/hooks-scripts/*.sh | grep -v "^-rwx"

# Check observations.jsonl exists
ls -la memory-bank/observations.jsonl

# Count total observations
wc -l memory-bank/observations.jsonl 2>/dev/null || echo "0 observations"
```

### Phase 4 — Skills Assessment
```bash
# Count skills
ls .cursor/skills/ | wc -l

# Count instincts
ls memory-bank/instincts/*.yaml 2>/dev/null | wc -l || echo "0 instincts"
```

### Phase 5 — Commands Inventory
```bash
ls .cursor/commands/*.md | wc -l
```

### Phase 6 — Memory Bank Status
```bash
# Check if memory-bank files have been filled in
wc -l memory-bank/project-context.md
wc -l memory-bank/learned-patterns.md
wc -l memory-bank/observations.jsonl
wc -l memory-bank/active-issues.md
```

## Output Format

```
HARNESS AUDIT REPORT — [date]

RULES          [n] total | [n] always-on (should be 2) | [n] over 500 lines
MCP            Supabase: ✅/❌ | Stripe: ✅/❌ | Memory: ✅/❌
HOOKS          [n] scripts | [n] executable | observations: [n] total
SKILLS         [n] skills | [n] instincts learned
COMMANDS       [n] commands
MEMORY BANK    project-context: [filled/empty] | active-issues: [filled/empty]

RISK ASSESSMENT
  🔴 Critical: [issues that break functionality]
  🟡 Important: [issues that reduce effectiveness]
  🟢 Healthy: [things working correctly]

RECOMMENDATIONS
  1. [highest priority action]
  2. [second action]
```
