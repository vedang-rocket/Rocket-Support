import sys, os, tempfile, json
sys.path.insert(0, os.path.expanduser("~/rocket-support/engine"))
import chain_walker


def _make_repo(files: dict) -> str:
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "package.json"), "w") as f:
        json.dump({"dependencies": {"@supabase/ssr": "0.4.0", "stripe": "14.0.0"}}, f)
    for rel, content in files.items():
        path = os.path.join(d, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
    return d


def test_env_production_missing_key():
    """Missing SUPABASE_SERVICE_ROLE_KEY in .env.production (no .env.local) is detected."""
    repo = _make_repo({
        ".env.production": "NEXT_PUBLIC_SUPABASE_URL=https://x.supabase.co\n",
        "middleware.ts": "import { updateSession } from '@/lib/supabase/middleware'\n",
    })
    findings = chain_walker.walk(repo)
    env_breaks = [f for f in findings if f["chain"] == "ENV"]
    assert len(env_breaks) > 0, "Should detect missing SUPABASE_SERVICE_ROLE_KEY in .env.production"


def test_env_local_still_detected():
    """Missing SUPABASE_SERVICE_ROLE_KEY in .env.local still detected."""
    repo = _make_repo({
        ".env.local": "NEXT_PUBLIC_SUPABASE_URL=https://x.supabase.co\n",
        "middleware.ts": "import { updateSession } from '@/lib/supabase/middleware'\n",
    })
    findings = chain_walker.walk(repo)
    env_breaks = [f for f in findings if f["chain"] == "ENV"]
    assert len(env_breaks) > 0, "Should detect missing SUPABASE_SERVICE_ROLE_KEY in .env.local"


def test_middleware_inline_ssr_pattern_passes():
    """Inline SSR canonical form (no updateSession import) must pass chain_walker."""
    inline_middleware = (
        "import { createServerClient } from '@supabase/ssr'\n"
        "import { NextResponse, type NextRequest } from 'next/server'\n"
        "\n"
        "export async function middleware(request: NextRequest) {\n"
        "  let supabaseResponse = NextResponse.next({ request })\n"
        "  const supabase = createServerClient(\n"
        "    process.env.NEXT_PUBLIC_SUPABASE_URL!,\n"
        "    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,\n"
        "    { cookies: { getAll() { return request.cookies.getAll() }, setAll() {} } }\n"
        "  )\n"
        "  await supabase.auth.getUser()\n"
        "  return supabaseResponse\n"
        "}\n"
        "\n"
        "export const config = { matcher: ['/((?!_next).*)'] }\n"
    )
    repo = _make_repo({"middleware.ts": inline_middleware})
    findings = chain_walker.walk(repo)
    auth_breaks = [f for f in findings if f["chain"] == "AUTH"]
    mw_breaks = [f for f in auth_breaks if "middleware" in f.get("broken_at", "")]
    assert len(mw_breaks) == 0, (
        f"Inline SSR pattern should pass middleware check, got: {mw_breaks}"
    )


def test_middleware_missing_both_patterns_fails():
    """middleware.ts with neither updateSession nor inline SSR must still fail."""
    repo = _make_repo({
        "middleware.ts": "export function middleware(request) { return NextResponse.next() }\n",
    })
    findings = chain_walker.walk(repo)
    auth_breaks = [f for f in findings if f["chain"] == "AUTH"]
    mw_breaks = [f for f in auth_breaks if "middleware" in f.get("broken_at", "")]
    assert len(mw_breaks) > 0, "Empty middleware must still trigger AUTH violation"
