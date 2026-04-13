-- ============================================================
-- AUTH AUDIT SCRIPT — Rocket.new Next.js + Supabase Projects
-- Run this in Supabase SQL Editor for a full auth diagnostic
-- ============================================================

-- 1. CHECK: Does the profiles table exist?
SELECT 
  CASE WHEN EXISTS (
    SELECT 1 FROM information_schema.tables 
    WHERE table_schema = 'public' AND table_name = 'profiles'
  ) THEN '✅ profiles table exists' 
  ELSE '❌ profiles table MISSING — run migrations' 
  END AS profiles_table_check;

-- 2. CHECK: Profile trigger exists (most common blank dashboard cause)
SELECT 
  CASE WHEN EXISTS (
    SELECT 1 FROM pg_trigger WHERE tgname = 'on_auth_user_created'
  ) THEN '✅ on_auth_user_created trigger exists'
  ELSE '❌ MISSING TRIGGER — users signing up will have blank dashboards'
  END AS profile_trigger_check;

-- 3. CHECK: Users with no profile (broken signups)
SELECT 
  COUNT(*) AS users_without_profiles,
  CASE WHEN COUNT(*) = 0 
    THEN '✅ All users have profiles'
    ELSE '❌ ' || COUNT(*) || ' users have no profile row — run backfill SQL'
  END AS orphan_users_check
FROM auth.users u
WHERE NOT EXISTS (
  SELECT 1 FROM public.profiles p WHERE p.id = u.id
);

-- 4. LIST: Show orphaned users (no profile) for investigation
SELECT 
  u.id,
  u.email,
  u.created_at,
  u.raw_user_meta_data->>'full_name' AS full_name
FROM auth.users u
WHERE NOT EXISTS (
  SELECT 1 FROM public.profiles p WHERE p.id = u.id
)
ORDER BY u.created_at DESC
LIMIT 20;

-- 5. CHECK: RLS enabled on profiles table
SELECT 
  relname AS table_name,
  CASE relrowsecurity 
    WHEN true THEN '✅ RLS enabled' 
    ELSE '❌ RLS DISABLED — all users can read all profiles' 
  END AS rls_status
FROM pg_class
WHERE relname = 'profiles' AND relnamespace = 'public'::regnamespace;

-- 6. LIST: All RLS policies on profiles table
SELECT 
  policyname,
  cmd AS operation,
  qual AS using_expression,
  with_check AS check_expression
FROM pg_policies
WHERE tablename = 'profiles' AND schemaname = 'public'
ORDER BY cmd, policyname;

-- 7. CHECK: Are email confirmations required?
-- (If yes, users must confirm before login works)
SELECT 
  'Email confirmations: check Supabase Dashboard → Auth → Providers → Email → Confirm email toggle' 
  AS note;

-- 8. CHECK: Recent failed auth attempts (last 24 hours)
SELECT 
  COUNT(*) AS recent_signups,
  MAX(created_at) AS latest_signup
FROM auth.users
WHERE created_at > NOW() - INTERVAL '24 hours';

-- 9. LIST: Current Supabase URL configuration
-- (Cannot query redirect URLs via SQL — check in Dashboard)
SELECT 'Check Supabase Dashboard → Auth → URL Configuration for redirect URL list' AS redirect_url_note;

-- 10. CHECK: Column names in profiles table
SELECT 
  column_name,
  data_type,
  is_nullable,
  column_default
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'profiles'
ORDER BY ordinal_position;

-- ============================================================
-- BACKFILL: Run this if check #3 found orphaned users
-- ============================================================
/*
INSERT INTO public.profiles (id, display_name, created_at)
SELECT 
  id, 
  COALESCE(raw_user_meta_data->>'full_name', email),
  created_at
FROM auth.users
WHERE id NOT IN (SELECT id FROM public.profiles)
ON CONFLICT DO NOTHING;
*/

-- ============================================================
-- FIX: Missing profile trigger — run if check #2 failed
-- ============================================================
/*
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO public.profiles (id, display_name, created_at)
  VALUES (
    NEW.id,
    COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.email),
    NOW()
  )
  ON CONFLICT (id) DO NOTHING;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE PROCEDURE public.handle_new_user();
*/
