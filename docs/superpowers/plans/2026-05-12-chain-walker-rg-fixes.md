# Chain Walker + rg Memory Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix chain_walker falsely reporting a violation after the deterministic middleware rewriter succeeds, and cap rg memory usage in probe_scanner.

**Architecture:** Two surgical fixes in two files. Bug 1: `_walk_chain()` in chain_walker.py must accept the inline SSR canonical form (`supabase.auth.getUser` + `createServerClient`) as a valid alternative to `updateSession` for the middleware check. Bug 2: `_run_rg()` in probe_scanner.py must cap rg output with `--max-count 100` before the subprocess writes to stdout, preventing large repos from buffering gigabytes of rg output into RAM.

**Tech Stack:** Python 3, pytest, ripgrep (rg)

---

## Files Modified

| File | Change |
|---|---|
| `engine/chain_walker.py` | Add `_middleware_passes(content)` helper; call from `_walk_chain` |
| `engine/probe_scanner.py` | Add `"--max-count", "100"` to `_run_rg()` argv + `results[:100]` slice |
| `tests/engine/test_chain_walker.py` | Add test for inline SSR pattern |
| `tests/engine/test_probe_scanner.py` | Add test that `_run_rg` includes `--max-count` |

Test runner: `engine/.venv/bin/python -m pytest tests/ -v 2>&1 | tail -8`

---

## Task 1: chain_walker — accept inline SSR middleware pattern

**Files:**
- Modify: `engine/chain_walker.py` (around lines 91–96 and 260–262)
- Test: `tests/engine/test_chain_walker.py`

### Root cause

`_walk_chain()` line 261 calls `_first_missing(content, ["updateSession"])`. The deterministic rewriter writes `_MIDDLEWARE_CANONICAL_INLINE` when no lib helper exists — that template contains `supabase.auth.getUser()` and `createServerClient` but **never the string "updateSession"**. So chain_walker always reports a violation after the inline rewrite.

### Step 1: Write the failing test

- [ ] Add to `tests/engine/test_chain_walker.py`:

```python
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
```

- [ ] Run test to confirm it fails:

```bash
engine/.venv/bin/python -m pytest tests/engine/test_chain_walker.py::test_middleware_inline_ssr_pattern_passes -v
```

Expected: `FAILED` — `mw_breaks` contains the AUTH violation.

### Step 2: Add `_middleware_passes()` helper to chain_walker.py

- [ ] In `engine/chain_walker.py`, add the helper directly after `_first_missing()` (after line 96):

```python
def _middleware_passes(content: str) -> bool:
    """
    Return True if content satisfies the middleware auth-refresh requirement.
    Accepts two canonical forms:
      1. updateSession import/call pattern (lib helper approach)
      2. Inline SSR pattern: createServerClient + supabase.auth.getUser
    """
    if "updateSession" in content or "updatesession" in content.lower():
        return True
    if (
        ("createServerClient" in content or "createserverclient" in content.lower())
        and ("supabase.auth.getUser" in content or "supabase.auth.getuser" in content.lower())
    ):
        return True
    return False
```

### Step 3: Use `_middleware_passes()` in `_walk_chain()`

- [ ] In `engine/chain_walker.py`, find the section inside `_walk_chain()` that calls `_first_missing` (around line 261). The current block:

```python
        if "__REQUIRES_LOCALSTORAGE_FALLBACK__" in needles:
            # Only enforce fallback when createBrowserClient is actually used.
            if "createBrowserClient" not in content and "createbrowserclient" not in content.lower():
                continue
            if "localStorage" not in content and "localstorage" not in content.lower():
                missing = "localStorage fallback"
            else:
                missing = None
        else:
            missing = _first_missing(content, needles)
```

Replace with:

```python
        if "__REQUIRES_LOCALSTORAGE_FALLBACK__" in needles:
            # Only enforce fallback when createBrowserClient is actually used.
            if "createBrowserClient" not in content and "createbrowserclient" not in content.lower():
                continue
            if "localStorage" not in content and "localstorage" not in content.lower():
                missing = "localStorage fallback"
            else:
                missing = None
        elif "updateSession" in needles and (
            rel_path.endswith("middleware.ts") or rel_path.endswith("middleware.js")
        ):
            # Accept either the updateSession import pattern or the inline SSR canonical form.
            missing = None if _middleware_passes(content) else "updateSession"
        else:
            missing = _first_missing(content, needles)
```

### Step 4: Run test to confirm it passes

- [ ] Run:

```bash
engine/.venv/bin/python -m pytest tests/engine/test_chain_walker.py -v
```

Expected: all chain_walker tests PASS including the new one.

### Step 5: Run full suite

- [ ] Run:

```bash
engine/.venv/bin/python -m pytest tests/ -v 2>&1 | tail -8
```

Expected: all 27+ tests pass.

### Step 6: Commit

- [ ] Run:

```bash
git add engine/chain_walker.py tests/engine/test_chain_walker.py
git commit -m "$(cat <<'EOF'
fix: chain_walker accepts inline SSR middleware pattern

_middleware_passes() accepts either updateSession import OR
createServerClient + supabase.auth.getUser inline pattern.
Fixes false violation after deterministic rewriter succeeds.

Co-Authored-By: claude-flow <ruv@ruv.net>
EOF
)"
```

---

## Task 2: probe_scanner — cap rg output with --max-count 100

**Files:**
- Modify: `engine/probe_scanner.py` (lines 96–115, the `_run_rg()` function)
- Test: `tests/engine/test_probe_scanner.py`

### Root cause

`_run_rg()` calls `subprocess.run(..., capture_output=True)` which buffers rg's entire stdout into a single Python string before any parsing. For large repos with thousands of matching lines, this materialises gigabytes into RAM. Adding `--max-count 100` to rg's argv causes rg itself to stop writing output after 100 matches per file, keeping the subprocess buffer small.

### Step 1: Write the failing test

- [ ] Add to `tests/engine/test_probe_scanner.py`:

```python
def test_run_rg_includes_max_count():
    """_run_rg must pass --max-count 100 to rg to cap memory usage."""
    import probe_scanner
    import unittest.mock as mock

    captured_args = []

    original_run = probe_scanner.subprocess.run

    def fake_run(args, **kwargs):
        captured_args.extend(args)
        # Return empty output so the rest of _run_rg completes normally
        result = mock.MagicMock()
        result.stdout = ""
        result.returncode = 0
        return result

    with mock.patch.object(probe_scanner.subprocess, "run", side_effect=fake_run):
        # Temporarily disable tracer path so we hit the subprocess.run branch
        original_logger = probe_scanner._tracer.get_logger
        probe_scanner._tracer.get_logger = lambda: None
        try:
            probe_scanner._run_rg(["-n", "somepattern", "/tmp"])
        finally:
            probe_scanner._tracer.get_logger = original_logger

    assert "--max-count" in captured_args, (
        f"_run_rg must pass --max-count to rg; got args: {captured_args}"
    )
    idx = captured_args.index("--max-count")
    assert captured_args[idx + 1] == "100", (
        f"--max-count value must be '100', got '{captured_args[idx + 1]}'"
    )
```

- [ ] Run test to confirm it fails:

```bash
engine/.venv/bin/python -m pytest tests/engine/test_probe_scanner.py::test_run_rg_includes_max_count -v
```

Expected: `FAILED` — `--max-count` not in captured args.

### Step 2: Add `--max-count 100` to `_run_rg()`

- [ ] In `engine/probe_scanner.py`, find `_run_rg()` (lines 96–115). Current implementation:

```python
def _run_rg(args: List[str]) -> List[Dict]:
    """Run rg --json and return parsed match objects."""
    if _tracer.get_logger() is not None:
        return _tracer.trace_rg(args)
    try:
        r = subprocess.run(
            [_RG, "--json"] + args,
            capture_output=True, text=True, timeout=10,
        )
        results = []
        for line in r.stdout.splitlines():
            try:
                obj = json.loads(line)
                if obj.get("type") == "match":
                    results.append(obj["data"])
            except Exception:
                pass
        return results
    except Exception:
        return []
```

Replace with:

```python
def _run_rg(args: List[str]) -> List[Dict]:
    """Run rg --json and return parsed match objects. Capped at 100 results."""
    if _tracer.get_logger() is not None:
        return _tracer.trace_rg(args)
    try:
        r = subprocess.run(
            [_RG, "--json", "--max-count", "100"] + args,
            capture_output=True, text=True, timeout=10,
        )
        results = []
        for line in r.stdout.splitlines():
            try:
                obj = json.loads(line)
                if obj.get("type") == "match":
                    results.append(obj["data"])
            except Exception:
                pass
        return results[:100]
    except Exception:
        return []
```

### Step 3: Run test to confirm it passes

- [ ] Run:

```bash
engine/.venv/bin/python -m pytest tests/engine/test_probe_scanner.py::test_run_rg_includes_max_count -v
```

Expected: `PASSED`.

### Step 4: Run full suite

- [ ] Run:

```bash
engine/.venv/bin/python -m pytest tests/ -v 2>&1 | tail -8
```

Expected: all tests pass.

### Step 5: Commit

- [ ] Run:

```bash
git add engine/probe_scanner.py tests/engine/test_probe_scanner.py
git commit -m "$(cat <<'EOF'
fix: cap rg output at 100 matches in _run_rg() to reduce memory

Adds --max-count 100 to rg argv so rg stops writing after 100
matches per file; keeps subprocess buffer small on large repos.
Backstop: results[:100] slice in parser loop.

Co-Authored-By: claude-flow <ruv@ruv.net>
EOF
)"
```

---

## Verification

After both commits:

```bash
# 1. All tests pass
engine/.venv/bin/python -m pytest tests/ -v 2>&1 | tail -8

# 2. chain_walker accepts inline template
engine/.venv/bin/python -c "
import sys; sys.path.insert(0,'engine')
import chain_walker
result = chain_walker._middleware_passes(
    'import { createServerClient } from \"@supabase/ssr\"\n'
    'await supabase.auth.getUser()\n'
)
print('inline SSR passes:', result)
result2 = chain_walker._middleware_passes(
    'import { updateSession } from \"@/lib/supabase/middleware\"\n'
)
print('updateSession passes:', result2)
result3 = chain_walker._middleware_passes(
    'import { something } from \"somewhere\"\n'
)
print('empty middleware passes (should be False):', result3)
"
# Expected:
# inline SSR passes: True
# updateSession passes: True
# empty middleware passes (should be False): False

# 3. rkt-trace on the failing ticket
rkt-trace 69e1d0ddd486e40014029a88
# Expected: [4/4] validating... chain_walker clean
```
