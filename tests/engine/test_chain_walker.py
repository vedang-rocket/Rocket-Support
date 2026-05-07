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
