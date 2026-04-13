---
description: Scan your existing test files to learn how you mock Supabase, handle auth, and structure tests. Updates memory-bank/test-patterns.json used by /generate-tests.
---

# /learn-test-patterns

Analyse existing tests to build the test pattern library.

## What it does

Scans `tests/`, `__tests__/`, `*.test.ts`, `*.spec.ts` and extracts:
  - How Supabase client is mocked (vi.mock pattern)
  - How authenticated users are simulated in e2e tests
  - Describe block naming conventions
  - Whether project uses Playwright, Vitest, Jest, or Cypress
  - Common setup/teardown patterns

Writes to `memory-bank/test-patterns.json` — used by `/generate-tests` to
match generated tests to your existing style.

## Run this first

Run `/learn-test-patterns` before your first `/generate-tests` to ensure
generated tests follow your conventions rather than generic defaults.
