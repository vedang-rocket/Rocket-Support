"""
Seed brain.db with real-world support patterns observed in Rocket.new projects.
Run: python3 engine/seed_real_patterns.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from db import save_fix

PATTERNS = [
    dict(
        pattern="Redirect loop after login — dashboard infinite loading",
        error_signature="after login user redirected back to login or dashboard keeps loading forever",
        category="AUTH",
        fix_diff="Check middleware.ts — add: import { updateSession } from '@/lib/supabase/middleware' and return await updateSession(request)",
        verified=1,
        project_type="SaaS",
    ),
    dict(
        pattern="RLS blocking authenticated user INSERT on table",
        error_signature="new row violates row-level security policy for table",
        category="SUPABASE",
        fix_diff="CREATE POLICY 'Users can insert own data' ON table_name FOR INSERT WITH CHECK (auth.uid() = user_id);",
        verified=1,
        project_type="SaaS",
    ),
    dict(
        pattern="Hydration mismatch blank screen after login",
        error_signature="hydration failed server rendered HTML did not match client",
        category="UI",
        fix_diff="Add export const dynamic = 'force-dynamic' after imports in affected page. Check for Date.now() or Math.random() in render.",
        verified=1,
        project_type="SaaS",
    ),
    dict(
        pattern="Stripe subscription not updating in database after payment",
        error_signature="payment successful in stripe but subscription table not updated user still on free tier",
        category="STRIPE",
        fix_diff="Webhook handler using request.json() instead of request.text() — change: const body = await request.text(). Verify STRIPE_WEBHOOK_SECRET env var is set.",
        verified=1,
        project_type="SaaS",
    ),
    dict(
        pattern="Build failing silently no output",
        error_signature="build never finishes or blank screen no visible errors",
        category="BUILD",
        fix_diff="Run bun run type-check to find TypeScript errors. Check all process.env references have fallbacks.",
        verified=1,
        project_type="SaaS",
    ),
    dict(
        pattern="CORS error blocking preview or API calls",
        error_signature="access control allow origin header blocked by CORS policy",
        category="BUILD",
        fix_diff="Add CORS headers in next.config.js async headers(). Check NEXT_PUBLIC_SUPABASE_URL matches actual Supabase project URL.",
        verified=1,
        project_type="SaaS",
    ),
    dict(
        pattern="Language translation showing raw variable names in UI",
        error_signature="translation key shown instead of translated text variable name visible",
        category="UI",
        fix_diff="Check locale JSON files exist for all languages in next.config.js i18n.locales array. Verify key paths match exactly.",
        verified=1,
        project_type="SaaS",
    ),
    dict(
        pattern="Email not sending Resend or SendGrid silently failing",
        error_signature="email not received no error in logs email silently failing",
        category="BUILD",
        fix_diff="Verify RESEND_API_KEY or SENDGRID_API_KEY in .env. Check sender domain is verified in dashboard.",
        verified=1,
        project_type="SaaS",
    ),
    dict(
        pattern="Navigation pages redirecting to dashboard unexpectedly",
        error_signature="support health login pages all redirect to dashboard",
        category="AUTH",
        fix_diff="Middleware matcher too broad. Fix config.matcher to exclude public routes: '/((?!login|signup|_next|favicon).*)' ",
        verified=1,
        project_type="SaaS",
    ),
    dict(
        pattern="createClient from supabase-js used in server component",
        error_signature="createClient supabase-js in server component route handler API route",
        category="SUPABASE",
        fix_diff="Replace: import { createClient } from '@supabase/supabase-js' with: import { createServerClient } from '@supabase/ssr' in all server files",
        verified=1,
        project_type="SaaS",
    ),
    dict(
        pattern="APK crash on launch Flutter app",
        error_signature="flutter app crashes immediately on launch android APK",
        category="BUILD",
        fix_diff="Check flutter/dart version compatibility. Run flutter clean && flutter pub get. Check AndroidManifest.xml permissions.",
        verified=1,
        project_type="Flutter",
    ),
    dict(
        pattern="Preview not loading blank screen in app",
        error_signature="preview blank white screen loading spinner never stops",
        category="UI",
        fix_diff="Check browser console for errors. Common causes: missing env vars, failed Supabase connection, uncaught runtime error. Add error boundary to root layout.",
        verified=1,
        project_type="SaaS",
    ),
]


def main():
    print(f"Seeding {len(PATTERNS)} real-world patterns into brain.db...\n")
    for p in PATTERNS:
        fix_id = save_fix(
            pattern=p["pattern"],
            error_signature=p["error_signature"],
            category=p["category"],
            fix_diff=p["fix_diff"],
            project_type=p["project_type"],
            verified=p["verified"],
        )
        print(f"  [{p['category']:8s}] {p['pattern'][:60]}  → {fix_id}")
    print(f"\nDone. {len(PATTERNS)} patterns saved.")


if __name__ == "__main__":
    main()
