---
description: Generate a full Playwright and/or Vitest acceptance test suite from a user story. Covers happy path, auth protection, empty state, error state, and edge cases. Matches your existing test patterns.
---

# /generate-tests

Generate acceptance tests from a user story.

## Usage

```
/generate-tests As a logged-in user, I want to view my order history so I can track purchases.

/generate-tests Users can upload profile pictures up to 5MB. Non-image files should be rejected.

/generate-tests Admins can delete any user account. Regular users cannot.
```

## What you get

**Playwright e2e tests** (if UI is involved):
  - Happy path (authenticated user sees the feature)
  - Auth redirect (unauthenticated user → /login)
  - Empty state (first-time user with no data)
  - Error state (Supabase returns 500)
  - Permission boundary (user tries to access another user's data)

**Vitest unit tests** (if Server Actions or API routes are involved):
  - Successful response with valid auth
  - 401 for unauthenticated request
  - 403 for insufficient permissions
  - 422/400 for invalid input
  - 500 for database failure

## How test patterns are matched

Before generating, the `test-generator` agent reads `memory-bank/test-patterns.json`
to use YOUR existing Supabase mock pattern, auth helper, and naming conventions.

Run `/learn-test-patterns` first if you haven't — it indexes your existing tests.

## Tips

- Include acceptance criteria in the story for better edge case coverage
- Mention the role ("as an admin", "as a guest") — affects auth test generation
- Mention input fields explicitly for validation test generation
- The more specific the story, the more specific the edge cases

## Related

- `/learn-test-patterns` — refresh the test pattern index from existing tests
- `/generate-feature` — generate the feature first, then /generate-tests for it
