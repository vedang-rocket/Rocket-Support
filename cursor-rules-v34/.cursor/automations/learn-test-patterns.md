# Test Pattern Learner Automation
# Trigger: Weekly on Saturday at 11pm
# Copy this prompt into Cursor Settings → Automations

---

You are a test pattern analyser for a Rocket.new project.

## Task

Scan all test files in this project and update memory-bank/test-patterns.json
with the current patterns so /generate-tests stays in sync with the codebase.

## Step 1 — Find test files

Glob: **/*.test.ts, **/*.test.tsx, **/*.spec.ts, tests/e2e/**/*.spec.ts
Exclude: node_modules/, .next/

## Step 2 — Detect framework

Check package.json devDependencies for: vitest, jest, playwright, cypress
Record all that are present.

## Step 3 — Extract patterns from first 5 test files

For each of the 5 most recently modified test files, record:
- The vi.mock or jest.mock pattern used for @/lib/supabase/server
- The auth setup pattern (beforeEach sign-in, factory function, mock user object)
- The describe block naming style
- How errors are typically asserted

## Step 4 — Write test-patterns.json

Update memory-bank/test-patterns.json with findings.

## Step 5 — Log

Write one line to .cursor/agent-log.txt:
"[DATE] TEST PATTERNS: N test files analysed → memory-bank/test-patterns.json"
