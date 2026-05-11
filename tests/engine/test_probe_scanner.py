import sys, os, tempfile, shutil
sys.path.insert(0, os.path.expanduser("~/rocket-support/engine"))
import probe_scanner


def _write_ts(content: str) -> str:
    f = tempfile.NamedTemporaryFile(suffix=".ts", mode="w", delete=False)
    f.write(content)
    f.close()
    return f.name


# ── Rule 9: headers() without await ──────────────────────────────────────────

def test_scan_headers_without_await_detects():
    path = _write_ts("const headersList = headers()\n")
    findings = probe_scanner.scan_headers_without_await([path])
    assert len(findings) == 1
    assert findings[0]["check_id"] == "headers-without-await"


def test_scan_headers_without_await_ignores_awaited():
    path = _write_ts("const headersList = await headers()\n")
    findings = probe_scanner.scan_headers_without_await([path])
    assert len(findings) == 0


# ── Rule 11: 'use client' + server import ────────────────────────────────────

def test_scan_use_client_server_import_detects():
    path = _write_ts(
        "'use client'\n"
        "import { createServerClient } from '@supabase/ssr'\n"
        "export default function Page() { return null }\n"
    )
    with tempfile.TemporaryDirectory() as repo:
        shutil.copy(path, os.path.join(repo, "page.tsx"))
        findings = probe_scanner.scan_use_client_server_import(repo)
    assert len(findings) >= 1
    assert findings[0]["check_id"] == "use-client-server-import"


def test_scan_use_client_server_import_ignores_browser():
    path = _write_ts(
        "'use client'\n"
        "import { createBrowserClient } from '@supabase/ssr'\n"
    )
    with tempfile.TemporaryDirectory() as repo:
        shutil.copy(path, os.path.join(repo, "page.tsx"))
        findings = probe_scanner.scan_use_client_server_import(repo)
    assert len(findings) == 0


# ── Rule 12: Server Action missing revalidatePath ─────────────────────────────

def test_scan_missing_revalidate_detects():
    path = _write_ts(
        "'use server'\n"
        "export async function updateProfile(data) {\n"
        "  const supabase = createServerClient(...)\n"
        "  await supabase.from('profiles').update(data)\n"
        "}\n"
    )
    findings = probe_scanner.scan_missing_revalidate([path])
    assert len(findings) == 1
    assert findings[0]["check_id"] == "server-action-missing-revalidate"


def test_scan_missing_revalidate_ignores_with_revalidate():
    path = _write_ts(
        "'use server'\n"
        "import { revalidatePath } from 'next/cache'\n"
        "export async function updateProfile(data) {\n"
        "  await supabase.from('profiles').update(data)\n"
        "  revalidatePath('/dashboard')\n"
        "}\n"
    )
    findings = probe_scanner.scan_missing_revalidate([path])
    assert len(findings) == 0


def test_run_rg_includes_max_count():
    """_run_rg must pass --max-count 100 to rg to cap memory usage on large repos."""
    import unittest.mock as mock

    captured_args = []

    def fake_run(args, **kwargs):
        captured_args.extend(args)
        result = mock.MagicMock()
        result.stdout = ""
        result.returncode = 0
        return result

    # Disable tracer path so we hit the subprocess.run branch
    original_get_logger = probe_scanner._tracer.get_logger
    probe_scanner._tracer.get_logger = lambda: None
    try:
        with mock.patch.object(probe_scanner.subprocess, "run", side_effect=fake_run):
            probe_scanner._run_rg(["-n", "somepattern", "/tmp"])
    finally:
        probe_scanner._tracer.get_logger = original_get_logger

    assert "--max-count" in captured_args, (
        f"_run_rg must pass --max-count to rg; got args: {captured_args}"
    )
    idx = captured_args.index("--max-count")
    assert captured_args[idx + 1] == "100", (
        f"--max-count value must be '100', got '{captured_args[idx + 1]}'"
    )
