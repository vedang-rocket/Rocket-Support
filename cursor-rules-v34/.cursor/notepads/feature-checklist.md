# Notepad: Feature Implementation Checklist
# Reference with: @notepad-feature-checklist

Use this before starting any new feature implementation.

```
PRE-IMPLEMENTATION
  [ ] Wrote TypeScript type/interface for the data
  [ ] Designed database schema (tables, columns, constraints)
  [ ] Planned RLS policies for every table
  [ ] Listed all files to create and modify
  [ ] Identified what must NOT change (protected code)
  [ ] Confirmed with /spec-feature or plan.md

IMPLEMENTATION ORDER (never skip steps)
  [ ] 1. SQL migration written and pushed to Supabase
  [ ] 2. TypeScript types defined in lib/types.ts
  [ ] 3. Supabase queries written in API route or Server Action
  [ ] 4. UI component created (Server Component by default)
  [ ] 5. Auth protection added (getUser() + redirect)
  [ ] 6. Error handling added (try/catch + user-facing message)
  [ ] 7. TypeScript check: npx tsc --noEmit

VERIFICATION
  [ ] Feature works end-to-end in browser
  [ ] Auth check works (redirect when logged out)
  [ ] RLS works (user can only see their own data)
  [ ] No console.log left in production code
  [ ] /review-diff run and approved
```
