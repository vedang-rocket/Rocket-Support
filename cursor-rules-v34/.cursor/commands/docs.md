# Purpose: Search and retrieve documentation for Rocket.new, Supabase, Next.js, or Stripe

## Usage
/docs [query]
Examples:
  /docs supabase RLS policies
  /docs next.js server actions
  /docs stripe webhook setup
  /docs rocket.new commands

## What I Will Do

1. Search across all relevant documentation sources for the query
2. Prioritize official docs over community resources
3. Return the most relevant sections with source URLs
4. Provide a concise practical summary focused on the Rocket.new use case

## Documentation Sources (priority order)

1. **Rocket.new docs**: https://docs.rocket.new/
2. **Supabase docs**: https://supabase.com/docs
3. **Next.js docs**: https://nextjs.org/docs
4. **Stripe docs**: https://stripe.com/docs
5. **Tailwind docs**: https://tailwindcss.com/docs

## Search Strategy

For Rocket-specific questions:
→ Check docs.rocket.new first
→ Then supplement with Supabase/Next.js docs

For Supabase questions:
→ Always check for @supabase/ssr specific docs (not older auth-helpers docs)
→ Look for Next.js App Router specific examples

For Stripe questions:
→ Always look for webhook-specific docs
→ Check for Next.js App Router route handler examples

## Output Format

```
DOCS SEARCH: [query]

SOURCE: [url]
RELEVANT SECTION: [section name]

[concise practical summary with code example if applicable]

---
RELATED DOCS:
  - [url] — [brief description]
  - [url] — [brief description]

ROCKET-SPECIFIC NOTE: [any caveats for the Rocket.new stack]
```
