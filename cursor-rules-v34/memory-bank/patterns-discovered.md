# Codebase-Specific Patterns Discovered

> NOT general Rocket.new knowledge — things unique to THIS project's generated code.
> General patterns live in .cursor/rules/. This file is for THIS codebase's quirks.

## Auth Specifics
<!-- e.g. "Profile trigger is missing — must be run manually" -->
<!-- e.g. "Uses 'username' not 'display_name' in profiles table" -->

## Database Specifics
<!-- e.g. "subscriptions table uses 'tier' column not 'status'" -->
<!-- e.g. "users table has extra 'company_id' column not in standard schema" -->

## Component Structure
<!-- e.g. "Navigation is in components/layout/header.tsx not navbar.tsx" -->
<!-- e.g. "Uses Zustand for state, not Context API" -->

## Environment / Config
<!-- e.g. "Uses custom NEXT_PUBLIC_APP_URL not NEXT_PUBLIC_SITE_URL" -->
<!-- e.g. "Netlify site ID: [id]" -->

## Known Fragile Areas — Do Not Touch Without Testing
<!-- e.g. "The checkout route uses a custom Stripe pattern — do not refactor without testing" -->
<!-- e.g. "The auth middleware has a custom bypass for /api/public/ — do not remove it" -->

## Non-Standard Patterns This Project Uses
<!-- e.g. "Uses react-query for client-side data fetching instead of Server Components" -->
<!-- e.g. "Has a custom useAuth hook that wraps Supabase auth" -->
