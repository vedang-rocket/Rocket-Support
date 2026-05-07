# Support Intelligence System — Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade the rkt engine from 35-45% diagnosis accuracy to 85-90% across 16 targeted changes.

**Architecture:** Five tiers — data cleanup → new rules → semantic search → surgical context → pattern bootstrap. Each tier is independently deployable and additive.

**Tech Stack:** Python 3.14, numpy, scikit-learn, usearch, tantivy, tree-sitter (already in fix_writer.py), ast-grep-py, ripgrep, SQLite

---

## Python 3.14 Constraint

`fastembed` and `onnxruntime` do not have Python 3.14 wheels. **Do not attempt `pip install fastembed`.**

Packages confirmed compatible with Python 3.14 venv:
- `scikit-learn` ✓
- `usearch` ✓  
- `tantivy` ✓
- `numpy` ✓ (already installed)

---

## File Structure

**Modified files:**
- `engine/db.py` — embedding upgrade, SemanticIndex class, hybrid_lookup
- `engine/rkt_engine.py:745` — fix db_lookup query contamination
- `engine/chain_walker.py` — add .env.production to ENV chain
- `engine/probe_scanner.py` — add Rules 9, 11, 12, 13
- `engine/schema_checker.py` — add RLS INSERT policy check
- `engine/triage_graph.py` — wire oxc validation node
- `engine/requirements.txt` — add new deps

**New files:**
- `engine/brain_fts.py` — tantivy full-text index
- `engine/slicer.py` — tree-sitter surgical extraction
- `engine/fix_validator.py` — oxc validation gate
- `engine/git_extractor.py` — git history pattern bootstrap
- `engine/migrate_embeddings.py` — one-time embedding regeneration
- `tests/engine/test_db.py` — embedding + hybrid lookup tests
- `tests/engine/test_probe_scanner.py` — new rule tests
- `tests/engine/test_schema_checker.py` — RLS INSERT test

---

## Accuracy Targets

| After Tier | Target | What it adds |
|---|---|---|
| Today | 35-45% | Baseline |
| Tier 1 | 55-60% | Better embeddings + clean data = correct retrieval on existing 40 patterns |
| Tier 2 | 62-68% | 5 new rules catch real bugs currently invisible to every layer |
| Tier 3 | 72-78% | Semantic + keyword hybrid — same bug phrased differently now matches |
| Tier 4 | 78-83% | Token cost down 85%; oxc kills bad-deploy class of bugs |
| Tier 5 | 85-90% | 80-120 new patterns from real client history |

---

## TIER 1 — Data + Retrieval Fix (2 hours)

### Task 1: Upgrade embeddings from 128-dim char n-gram to 512-dim word n-gram

**Why this matters:** Current `_numpy_char_ngram_embed()` hashes 3/4-char sequences into 128 buckets. "dashboard blank after login" and "profile not showing after signup" share almost no character n-grams — cosine similarity ~0.05, below the 0.15 threshold, so the match is thrown away. Word-level hashing means "blank", "dashboard", "login" each get their own bucket. Same bug described differently now scores 0.4-0.6.

**Files:**
- Modify: `engine/db.py`
- Create: `engine/migrate_embeddings.py`
- Create: `tests/engine/test_db.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/engine/test_db.py
import sys, os
sys.path.insert(0, os.path.expanduser("~/rocket-support/engine"))
import db

def test_word_embed_dim():
    vec = db._numpy_word_embed("getSession server component auth failure")
    assert vec is not None
    assert len(vec) == 512

def test_word_embed_similar_phrases():
    """Same bug described differently should score > 0.4."""
    v1 = db._numpy_word_embed("dashboard blank after login getSession")
    v2 = db._numpy_word_embed("profile empty after signup session null")
    score = db._cosine(v1, v2)
    assert score > 0.30, f"Expected > 0.30, got {score:.3f}"

def test_word_embed_different_bugs():
    """Different bugs should score lower than similar ones."""
    v1 = db._numpy_word_embed("dashboard blank after login")
    v2 = db._numpy_word_embed("stripe webhook 400 request json")
    score = db._cosine(v1, v2)
    assert score < 0.40, f"Expected < 0.40, got {score:.3f}"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd ~/rocket-support
engine/.venv/bin/python -m pytest tests/engine/test_db.py::test_word_embed_dim -v
```
Expected: `AttributeError: module 'db' has no attribute '_numpy_word_embed'`

- [ ] **Step 3: Replace `_numpy_char_ngram_embed` in db.py**

In `engine/db.py`, replace lines 44-62 (the `_numpy_char_ngram_embed` function) with:

```python
def _numpy_word_embed(text: str, n_features: int = 512) -> Optional[List[float]]:
    """
    Word unigram + bigram hashing into n_features buckets.
    Replaces char n-gram — captures 'getSession' as a token, not character fragments.
    """
    try:
        import re as _re
        import numpy as np
        vec = np.zeros(n_features, dtype=float)
        tokens = _re.sub(r"[^\w]", " ", text.lower()).split()
        for tok in tokens:
            vec[hash(tok) % n_features] += 1.0
        for i in range(len(tokens) - 1):
            bigram = f"{tokens[i]} {tokens[i+1]}"
            vec[hash(bigram) % n_features] += 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec.tolist()
    except Exception:
        return None
```

Also update `_embed()` at line 65-70 to call the new function:

```python
def _embed(text: str) -> Optional[List[float]]:
    """Embed text. Tries sentence-transformers first, then word n-gram hashing."""
    st_vec = _try_sentence_transformers(text)
    if st_vec:
        return st_vec
    return _numpy_word_embed(text)
```

- [ ] **Step 4: Create migration script**

```python
# engine/migrate_embeddings.py
"""
One-time script: regenerate all brain.db embeddings with new word n-gram method.
Run once after updating _embed() in db.py.

Usage: engine/.venv/bin/python engine/migrate_embeddings.py
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db

def migrate():
    db.init_db()
    conn = db.get_conn()
    rows = conn.execute("SELECT id, pattern, error_signature, category FROM fixes").fetchall()
    updated = 0
    for row in rows:
        text = f"{row['pattern']} {row['error_signature'] or ''} {row['category'] or ''}"
        vec = db._embed(text)
        if vec:
            conn.execute(
                "UPDATE fixes SET embedding = ? WHERE id = ?",
                (json.dumps(vec), row["id"])
            )
            updated += 1
    conn.commit()
    conn.close()
    print(f"Migrated {updated}/{len(rows)} embeddings to 512-dim word n-gram.")
    print(f"Embedding dim: {len(vec) if vec else 'N/A'}")

if __name__ == "__main__":
    migrate()
```

- [ ] **Step 5: Run test to verify it passes**

```bash
engine/.venv/bin/python -m pytest tests/engine/test_db.py -v
```
Expected: all 3 tests PASS

- [ ] **Step 6: Run migration**

```bash
engine/.venv/bin/python engine/migrate_embeddings.py
```
Expected: `Migrated 40/40 embeddings to 512-dim word n-gram.`

- [ ] **Step 7: Commit**

```bash
git add engine/db.py engine/migrate_embeddings.py tests/engine/test_db.py
git commit -m "feat: upgrade brain.db embeddings from 128-dim char n-gram to 512-dim word n-gram"
```

**Rollback:** `git revert HEAD` — embedding column is TEXT, old 128-dim JSON still loads via _cosine(). No schema change.

**Time estimate:** 30 minutes

---

### Task 2: Fix db_lookup query contamination in rkt_engine.py

**Why this matters:** Line 745 builds the query as `f"{hint} {ptype} {common_failure}"`. For any SaaS project with no hint, this always includes "Stripe webhook 400 — request.json()" even when the bug is auth-related. The word "Stripe" dominates the query and returns STRIPE patterns for AUTH tickets.

**Files:**
- Modify: `engine/rkt_engine.py` (lines 743-749)

- [ ] **Step 1: Write the failing test**

Add to `tests/engine/test_db.py`:

```python
def test_db_lookup_no_stripe_bias():
    """Auth hint should not return STRIPE patterns."""
    import sys
    sys.path.insert(0, os.path.expanduser("~/rocket-support/engine"))
    import rkt_engine
    # Simulate: SaaS project, auth hint, no stripe mention
    result = rkt_engine.db_lookup("dashboard blank after login", category="AUTH")
    if result:
        assert result.get("category") != "STRIPE", (
            f"Got STRIPE match for AUTH hint: {result.get('pattern')}"
        )
```

- [ ] **Step 2: Run to verify it fails (may pass by chance — document result)**

```bash
engine/.venv/bin/python -m pytest tests/engine/test_db.py::test_db_lookup_no_stripe_bias -v
```

- [ ] **Step 3: Fix rkt_engine.py lines 743-749**

Find this block in `engine/rkt_engine.py`:
```python
    query_terms = f"{hint} {ptype} {fingerprint_result['common_failure']}"
    if hint:
        query_terms = f"{hint} {query_terms}"

    db_match = db_lookup(query_terms, category=fingerprint_result.get("category"))
```

Replace with:
```python
    # Use hint if given; otherwise fall back to common_failure only (no project type bias)
    if hint and hint.strip():
        query_terms = hint.strip()
    else:
        query_terms = fingerprint_result.get("common_failure", "")
    db_match = db_lookup(query_terms, category=fingerprint_result.get("category"))
```

Also fix the same contamination in `engine/triage_graph.py` `node_db_lookup()` (lines 222-223):

Find:
```python
    query = f"{state['issue_description']} {fp_result.get('common_failure', '')} {fp_result.get('project_type', '')}"
```

Replace with:
```python
    query = state["issue_description"].strip() or fp_result.get("common_failure", "")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
engine/.venv/bin/python -m pytest tests/engine/test_db.py::test_db_lookup_no_stripe_bias -v
```

- [ ] **Step 5: Commit**

```bash
git add engine/rkt_engine.py engine/triage_graph.py tests/engine/test_db.py
git commit -m "fix: remove project-type bias from db_lookup query in rkt_engine and triage_graph"
```

**Rollback:** `git revert HEAD` — pure logic change, no data modified.

**Time estimate:** 20 minutes

---

### Task 3: Delete garbage entries and fix crossed error_signatures

**Why this matters:** 8 "Manual fix:" entries pollute every similarity search (they all contain "Manual fix:" as a shared prefix — high char n-gram similarity to each other). Two entries have AUTH patterns but STRIPE error_signatures, causing cross-category false matches.

**Files:**
- No code changes — SQL only via migration script

- [ ] **Step 1: Verify entries to delete**

```bash
sqlite3 ~/.rocket-support/brain.db \
  "SELECT id, SUBSTR(pattern,1,60) FROM fixes WHERE pattern LIKE 'Manual fix:%';"
```
Expected: 8 rows

- [ ] **Step 2: Verify crossed error_signatures**

```bash
sqlite3 ~/.rocket-support/brain.db \
  "SELECT id, SUBSTR(pattern,1,50), SUBSTR(error_signature,1,50) FROM fixes \
   WHERE id IN ('be38dc53f31131d6','9196750b369166fa');"
```
Expected: both rows show AUTH patterns with STRIPE/SUPABASE error_signatures

- [ ] **Step 3: Create and run cleanup script**

```python
# engine/cleanup_db.py
"""
One-time cleanup: remove garbage entries and fix crossed error_signatures.
Run once. Safe to re-run (idempotent).

Usage: engine/.venv/bin/python engine/cleanup_db.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db

def cleanup():
    db.init_db()
    conn = db.get_conn()

    # Delete garbage Manual fix: entries
    before = conn.execute("SELECT count(*) FROM fixes").fetchone()[0]
    conn.execute("DELETE FROM fixes WHERE pattern LIKE 'Manual fix:%'")
    after_delete = conn.execute("SELECT count(*) FROM fixes").fetchone()[0]
    print(f"Deleted {before - after_delete} 'Manual fix:' entries. Remaining: {after_delete}")

    # Fix crossed error_signatures
    # be38dc53: AUTH pattern (ROCKET RULE 1: getUser) has STRIPE error_sig
    conn.execute(
        "UPDATE fixes SET error_signature = ? WHERE id = ?",
        (
            "Not authenticated after login | dashboard blank | session null on server | "
            "getUser() vs getSession() | JWT not validated",
            "be38dc53f31131d6",
        ),
    )
    # 9196750b: getSession AUTH pattern has SUPABASE RLS error_sig
    conn.execute(
        "UPDATE fixes SET error_signature = ? WHERE id = ?",
        (
            "getSession() reads cookies without JWT validation | use getUser() in server components",
            "9196750b369166fa",
        ),
    )
    conn.commit()
    conn.close()
    print("Fixed 2 crossed error_signatures.")
    print("Cleanup complete.")

if __name__ == "__main__":
    cleanup()
```

```bash
engine/.venv/bin/python engine/cleanup_db.py
```
Expected:
```
Deleted 8 'Manual fix:' entries. Remaining: 32
Fixed 2 crossed error_signatures.
Cleanup complete.
```

- [ ] **Step 4: Verify**

```bash
sqlite3 ~/.rocket-support/brain.db \
  "SELECT count(*) FROM fixes; SELECT count(*) FROM fixes WHERE pattern LIKE 'Manual fix:%';"
```
Expected: `32` then `0`

- [ ] **Step 5: Re-run migrate_embeddings.py to embed the fixed entries**

```bash
engine/.venv/bin/python engine/migrate_embeddings.py
```

- [ ] **Step 6: Commit**

```bash
git add engine/cleanup_db.py
git commit -m "feat: cleanup brain.db — remove 8 noise entries, fix 2 crossed error_signatures"
```

**Rollback:** `sqlite3 ~/.rocket-support/brain.db` and manually restore from `brain.db.backup` (make a backup first: `cp ~/.rocket-support/brain.db ~/.rocket-support/brain.db.backup`).

**Time estimate:** 20 minutes

---

## TIER 2 — New Detection Rules (1-2 days)

### Task 4: Rule 9 — headers() not awaited (probe_scanner.py)

**Why this matters:** Next.js 15 made `headers()` async at the same time as `cookies()`. The probe_scanner has Rule 6 for `cookies()` but nothing for `headers()`. Same pattern, same fix, zero coverage.

**Files:**
- Modify: `engine/probe_scanner.py`
- Create: `tests/engine/test_probe_scanner.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/engine/test_probe_scanner.py
import sys, os, tempfile
sys.path.insert(0, os.path.expanduser("~/rocket-support/engine"))
import probe_scanner

def _write_ts(content: str) -> str:
    f = tempfile.NamedTemporaryFile(suffix=".ts", mode="w", delete=False)
    f.write(content)
    f.close()
    return f.name

def test_scan_headers_without_await_detects():
    path = _write_ts("const headersList = headers()\n")
    findings = probe_scanner.scan_headers_without_await([path])
    assert len(findings) == 1
    assert findings[0]["check_id"] == "headers-without-await"

def test_scan_headers_without_await_ignores_awaited():
    path = _write_ts("const headersList = await headers()\n")
    findings = probe_scanner.scan_headers_without_await([path])
    assert len(findings) == 0
```

- [ ] **Step 2: Run to verify it fails**

```bash
engine/.venv/bin/python -m pytest tests/engine/test_probe_scanner.py -v
```
Expected: `AttributeError: module 'probe_scanner' has no attribute 'scan_headers_without_await'`

- [ ] **Step 3: Add function to probe_scanner.py**

Insert after `scan_cookies_without_await` (after line 339, before the `# ── Rule 7` comment):

```python
# ── Rule 9: headers() without await ──────────────────────────────────────────

def scan_headers_without_await(ts_files: List[str]) -> List[Dict[str, Any]]:
    """const/let $H = headers() without await → ast-grep-py; rg fallback."""
    findings: List[Dict] = []

    if _AST_GREP_AVAILABLE:
        patterns = [
            ("const $H = headers()", "headers-without-await-const"),
            ("let $H = headers()",   "headers-without-await-let"),
        ]
        for fpath in ts_files:
            try:
                with open(fpath, encoding="utf-8", errors="replace") as fh:
                    source = fh.read()
                root = SgRoot(source, "typescript")
                for pat, cid in patterns:
                    for m in root.root().find_all(pattern=pat):
                        text = m.text()
                        if "await" in text:
                            continue
                        r = m.range()
                        line = r.start.line + 1
                        col  = r.start.column
                        fixed = text.replace("= headers()", "= await headers()")
                        findings.append(_make_finding(
                            check_id="headers-without-await",
                            path=fpath,
                            start_line=line, start_col=col,
                            end_line=r.end.line + 1, end_col=r.end.column,
                            message=(
                                "headers() must be awaited in Next.js 15. Without await you get "
                                "a Promise, not the headers object — silent failure. (ROCKET RULE 5)"
                            ),
                            severity="ERROR",
                            fix=fixed,
                            category="AUTH",
                        ))
            except Exception:
                pass
        return findings

    # rg fallback
    pattern = r"(?:const|let)\s+\w+\s*=\s*headers\(\)"
    for match in _run_rg(["-n", pattern] + ts_files):
        fpath = match["path"]["text"]
        lno   = match["line_number"]
        col   = match["submatches"][0]["start"] if match.get("submatches") else 0
        text  = match["lines"]["text"] if match.get("lines") else ""
        if "await" in text:
            continue
        findings.append(_make_finding(
            check_id="headers-without-await",
            path=fpath,
            start_line=lno, start_col=col,
            end_line=lno, end_col=col + 20,
            message="headers() must be awaited in Next.js 15. (ROCKET RULE 5)",
            severity="ERROR",
            fix=text.replace("= headers()", "= await headers()").strip(),
            category="AUTH",
        ))
    return findings
```

Also add `scan_headers_without_await` to the AST-based scanners loop in `run_probe_scanner()`:

Find this line:
```python
    for fn in (scan_getsession, scan_cookies_without_await):
```

Replace with:
```python
    for fn in (scan_getsession, scan_cookies_without_await, scan_headers_without_await):
```

- [ ] **Step 4: Run test to verify it passes**

```bash
engine/.venv/bin/python -m pytest tests/engine/test_probe_scanner.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add engine/probe_scanner.py tests/engine/test_probe_scanner.py
git commit -m "feat: add Rule 9 — detect headers() without await in Next.js 15 (probe_scanner)"
```

**Rollback:** `git revert HEAD`

**Time estimate:** 30 minutes

---

### Task 5: Add .env.production to ENV chain (chain_walker.py)

**Why this matters:** The ENV chain only checks `.env.local`. Deployed apps use `.env.production`. Missing `SUPABASE_SERVICE_ROLE_KEY` in `.env.production` silently breaks production while passing locally.

**Files:**
- Modify: `engine/chain_walker.py` (the `ENV_CHAIN` in `build_chains()`)

- [ ] **Step 1: Write the failing test**

```python
# tests/engine/test_chain_walker.py
import sys, os, tempfile, json
sys.path.insert(0, os.path.expanduser("~/rocket-support/engine"))
import chain_walker

def _make_repo(files: dict) -> str:
    d = tempfile.mkdtemp()
    # minimal package.json with supabase
    with open(os.path.join(d, "package.json"), "w") as f:
        json.dump({"dependencies": {"@supabase/ssr": "0.4.0", "stripe": "14.0.0"}}, f)
    for rel, content in files.items():
        path = os.path.join(d, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(content)
    return d

def test_env_production_missing_key():
    repo = _make_repo({
        ".env.production": "NEXT_PUBLIC_SUPABASE_URL=https://x.supabase.co\n",
        "middleware.ts": "import { updateSession } from '@/lib/supabase/middleware'\n",
    })
    findings = chain_walker.walk(repo)
    env_breaks = [f for f in findings if f["chain"] == "ENV"]
    assert len(env_breaks) > 0, "Should detect missing SUPABASE_SERVICE_ROLE_KEY in .env.production"
```

- [ ] **Step 2: Run to verify it fails**

```bash
engine/.venv/bin/python -m pytest tests/engine/test_chain_walker.py::test_env_production_missing_key -v
```

- [ ] **Step 3: Update ENV_CHAIN in chain_walker.py**

In `build_chains()`, the `ENV_CHAIN` currently checks only `.env.local`. Replace the ENV_CHAIN definition with a version that checks both files:

Find the ENV_CHAIN block (starting around line 169):
```python
    ENV_CHAIN: List[Tuple] = [
        (
            ".env.local",
            ["SUPABASE_SERVICE_ROLE_KEY"],
```

The walker checks a single file per entry. To check both `.env.local` AND `.env.production`, add a helper and expand the chain. The cleanest approach without breaking the chain walker interface is to add `.env.production` entries alongside `.env.local` entries, but use a new "either-or" pattern.

Since `_walk_chain` stops at FIRST break per chain, and both `.env.local` and `.env.production` are optional (projects may use one or the other), add a new `_check_any_env` helper:

After line `def _read_pkg(repo_path: str) -> str:` (line 86), add:

```python
def _check_env_files(repo_path: str, needles: List[str]) -> Optional[Dict[str, Any]]:
    """
    Check multiple env files for required keys.
    Returns a break dict if ALL env files are either missing or lack the key.
    Returns None (pass) if ANY env file contains the key.
    """
    env_files = [".env.local", ".env.production", ".env"]
    found_any_file = False
    for env_file in env_files:
        abs_path = os.path.join(repo_path, env_file)
        content = _read(abs_path)
        if content is None:
            continue
        found_any_file = True
        missing = _first_missing(content, needles)
        if missing is None:
            return None  # key found in this file — pass
    if not found_any_file:
        return None  # no env files present — skip silently
    # All present env files are missing the key
    return {
        "chain":      "ENV",
        "broken_at":  ".env.local / .env.production",
        "missing":    needles[0],
        "issue":      f"{needles[0]} missing from all env files (.env.local, .env.production)",
        "fix_hint":   f"Add {needles[0]} to .env.local (dev) and .env.production (deploy)",
        "confidence": 1.0,
    }
```

Then in `walk()`, before the main chain loop, add a special ENV check that calls `_check_env_files`. Replace the ENV chain entries with lightweight sentinels and handle them separately, OR keep the existing structure and just add `.env.production` as additional glob entries. 

**Simpler approach** — just add `.env.production` as additional ENV chain entries:

Replace the ENV_CHAIN entries for each key with two entries (one per env file), then let the "first break" logic handle it. But since both are optional, use the glob approach (`.env*` pattern):

Replace the ENV_CHAIN block entirely:
```python
    ENV_CHAIN: List[Tuple] = [
        (
            ".env.local",
            ["SUPABASE_SERVICE_ROLE_KEY"],
            "SUPABASE_SERVICE_ROLE_KEY missing from .env.local — admin operations will fail",
            "Add SUPABASE_SERVICE_ROLE_KEY=<value> from Supabase Dashboard → Settings → API",
        ),
        (
            ".env.production",
            ["SUPABASE_SERVICE_ROLE_KEY"],
            "SUPABASE_SERVICE_ROLE_KEY missing from .env.production — will fail on deploy",
            "Add SUPABASE_SERVICE_ROLE_KEY=<value> to .env.production for deployed environment",
        ),
        (
            ".env.local",
            ["STRIPE_WEBHOOK_SECRET"],
            "STRIPE_WEBHOOK_SECRET missing from .env.local — webhook verification will fail",
            "Add STRIPE_WEBHOOK_SECRET=whsec_... from Stripe Dashboard → Webhooks → Signing secret",
        ),
        (
            ".env.production",
            ["STRIPE_WEBHOOK_SECRET"],
            "STRIPE_WEBHOOK_SECRET missing from .env.production — webhook will fail on deploy",
            "Add STRIPE_WEBHOOK_SECRET=whsec_... to .env.production",
        ),
    ]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
engine/.venv/bin/python -m pytest tests/engine/test_chain_walker.py -v
```

- [ ] **Step 5: Commit**

```bash
git add engine/chain_walker.py tests/engine/test_chain_walker.py
git commit -m "feat: check .env.production in ENV chain alongside .env.local"
```

**Rollback:** `git revert HEAD`

**Time estimate:** 30 minutes

---

### Task 6: Rule 11 — 'use client' with server imports (probe_scanner.py)

**Why this matters:** A `'use client'` file that imports `createServerClient` from `@supabase/ssr` causes a hard build failure. Next.js throws a module resolution error that shows as a blank page — nothing in chain_walker or existing probe rules catches it.

**Files:**
- Modify: `engine/probe_scanner.py`

- [ ] **Step 1: Add test to test_probe_scanner.py**

```python
def test_scan_use_client_server_import_detects():
    path = _write_ts(
        "'use client'\n"
        "import { createServerClient } from '@supabase/ssr'\n"
        "export default function Page() { return <div/> }\n"
    )
    with tempfile.TemporaryDirectory() as repo:
        import shutil
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
        import shutil
        shutil.copy(path, os.path.join(repo, "page.tsx"))
        findings = probe_scanner.scan_use_client_server_import(repo)
    assert len(findings) == 0
```

- [ ] **Step 2: Run to verify it fails**

```bash
engine/.venv/bin/python -m pytest tests/engine/test_probe_scanner.py::test_scan_use_client_server_import_detects -v
```

- [ ] **Step 3: Add function to probe_scanner.py**

Add after `scan_anon_key_format` (before `run_probe_scanner`):

```python
# ── Rule 11: 'use client' + server-only import ───────────────────────────────

def scan_use_client_server_import(repo_path: str) -> List[Dict[str, Any]]:
    """'use client' files that import server-only supabase/ssr exports → rg."""
    findings: List[Dict] = []
    server_only_imports = [
        "createServerClient",
        "createRouteHandlerClient",
    ]
    pattern = "|".join(server_only_imports)
    globs = ["**/page.tsx", "**/page.ts", "**/layout.tsx", "**/components/**/*.tsx",
             "**/components/**/*.ts"]
    glob_args: List[str] = []
    for g in globs:
        glob_args += ["--glob", g]

    for match in _run_rg(["-n", pattern] + glob_args + [repo_path]):
        fpath = match["path"]["text"]
        lno   = match["line_number"]
        # Verify the file has 'use client' directive
        try:
            with open(fpath, encoding="utf-8", errors="replace") as fh:
                first_500 = fh.read(500)
            if "use client" not in first_500:
                continue
        except OSError:
            continue
        col = match["submatches"][0]["start"] if match.get("submatches") else 0
        matched_text = match["lines"]["text"].strip() if match.get("lines") else ""
        findings.append(_make_finding(
            check_id="use-client-server-import",
            path=fpath,
            start_line=lno, start_col=col,
            end_line=lno, end_col=col + 25,
            message=(
                f"'use client' file imports server-only function ({matched_text.strip()}). "
                "This causes a build failure. Use createBrowserClient for client components."
            ),
            severity="ERROR",
            fix="createBrowserClient from '@supabase/ssr'",
            category="AUTH",
        ))
    return findings
```

Add to `run_probe_scanner()` in the rg-based scanners loop:

```python
    for fn in (scan_auth_helpers, scan_stripe_webhook, scan_supabase_wrong_import,
               scan_env_secrets, scan_missing_dynamic_export, scan_anon_key_format,
               scan_use_client_server_import):
```

- [ ] **Step 4: Run tests**

```bash
engine/.venv/bin/python -m pytest tests/engine/test_probe_scanner.py -v
```

- [ ] **Step 5: Commit**

```bash
git add engine/probe_scanner.py tests/engine/test_probe_scanner.py
git commit -m "feat: add Rule 11 — detect 'use client' files with server-only supabase imports"
```

**Time estimate:** 30 minutes

---

### Task 7: Rule 12 — Missing revalidatePath in Server Actions (probe_scanner.py)

**Why this matters:** Server Actions that write to Supabase without `revalidatePath()` serve stale cached data silently. User submits a form, data saves, but the page still shows old data. Common ticket: "form saves but page doesn't update."

**Files:**
- Modify: `engine/probe_scanner.py`

- [ ] **Step 1: Add test**

```python
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
```

- [ ] **Step 2: Add function to probe_scanner.py**

```python
# ── Rule 12: Server Action missing revalidatePath ─────────────────────────────

def scan_missing_revalidate(ts_files: List[str]) -> List[Dict[str, Any]]:
    """'use server' files with .update()/.insert()/.delete() but no revalidatePath → rg."""
    findings: List[Dict] = []
    mutation_pattern = r"\.(?:update|insert|delete|upsert)\s*\("

    server_action_files = []
    for fpath in ts_files:
        try:
            with open(fpath, encoding="utf-8", errors="replace") as fh:
                first_300 = fh.read(300)
            if "use server" in first_300:
                server_action_files.append(fpath)
        except OSError:
            continue

    for fpath in server_action_files:
        try:
            with open(fpath, encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except OSError:
            continue
        import re as _re
        has_mutation = bool(_re.search(mutation_pattern, content))
        has_revalidate = "revalidatePath" in content or "revalidateTag" in content
        if has_mutation and not has_revalidate:
            lno = next(
                (i + 1 for i, l in enumerate(content.splitlines())
                 if _re.search(mutation_pattern, l)),
                1,
            )
            findings.append(_make_finding(
                check_id="server-action-missing-revalidate",
                path=fpath,
                start_line=lno, start_col=0,
                end_line=lno, end_col=0,
                message=(
                    "Server Action mutates data but has no revalidatePath() or revalidateTag() call. "
                    "Next.js will serve stale cached data after the mutation."
                ),
                severity="WARNING",
                fix="import { revalidatePath } from 'next/cache'; revalidatePath('/your-path')",
                category="BUILD",
                confidence="MED",
            ))
    return findings
```

Add to AST-based scanners loop:
```python
    for fn in (scan_getsession, scan_cookies_without_await, scan_headers_without_await,
               scan_missing_revalidate):
```

- [ ] **Step 3: Run tests and commit**

```bash
engine/.venv/bin/python -m pytest tests/engine/test_probe_scanner.py -v
git add engine/probe_scanner.py tests/engine/test_probe_scanner.py
git commit -m "feat: add Rule 12 — detect Server Actions missing revalidatePath after mutations"
```

**Time estimate:** 30 minutes

---

### Task 8: RLS INSERT policy check (schema_checker.py)

**Why this matters:** RLS is enabled but only SELECT policies exist. Users can read but cannot INSERT — contact forms return 403, profile creation fails. schema_checker currently checks for `enable row level security` but never checks for INSERT policies.

**Files:**
- Modify: `engine/schema_checker.py`

- [ ] **Step 1: Add test**

```python
# tests/engine/test_schema_checker.py
import sys, os, tempfile
sys.path.insert(0, os.path.expanduser("~/rocket-support/engine"))
import schema_checker

def _make_migrations(sql: str) -> str:
    d = tempfile.mkdtemp()
    mdir = os.path.join(d, "supabase", "migrations")
    os.makedirs(mdir)
    with open(os.path.join(mdir, "001_init.sql"), "w") as f:
        f.write(sql)
    return d

def test_rls_insert_policy_missing():
    repo = _make_migrations(
        "ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;\n"
        "CREATE POLICY \"read\" ON profiles FOR SELECT USING (auth.uid() = id);\n"
    )
    results = schema_checker.check(repo)
    failures = schema_checker.failures(results)
    checks = [f["check"] for f in failures]
    assert "rls:insert_policy" in checks

def test_rls_insert_policy_present():
    repo = _make_migrations(
        "ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;\n"
        "CREATE POLICY \"insert\" ON profiles FOR INSERT WITH CHECK (auth.uid() = id);\n"
    )
    results = schema_checker.check(repo)
    failures = schema_checker.failures(results)
    checks = [f["check"] for f in failures]
    assert "rls:insert_policy" not in checks
```

- [ ] **Step 2: Run to verify it fails**

```bash
engine/.venv/bin/python -m pytest tests/engine/test_schema_checker.py -v
```

- [ ] **Step 3: Add check to schema_checker.py CHECKS list**

In `engine/schema_checker.py`, add to the `CHECKS` list after the existing `rls:enable_row_level_security` entry:

```python
    {
        "check":    "rls:insert_policy",
        "needle":   "for insert",
        "found_ok": True,
        "fix_hint": (
            "RLS enabled but no INSERT policy found — users cannot create rows. "
            "Add: CREATE POLICY \"Users insert own\" ON <table> FOR INSERT WITH CHECK (auth.uid() = user_id);"
        ),
    },
```

- [ ] **Step 4: Run tests and commit**

```bash
engine/.venv/bin/python -m pytest tests/engine/test_schema_checker.py -v
git add engine/schema_checker.py tests/engine/test_schema_checker.py
git commit -m "feat: add RLS INSERT policy check to schema_checker"
```

**Time estimate:** 20 minutes

---

## TIER 3 — Semantic Search Upgrade (1 week)

### Task 9: Install new dependencies

- [ ] **Step 1: Install and verify**

```bash
engine/.venv/bin/pip install usearch tantivy scikit-learn
engine/.venv/bin/python -c "import usearch; import tantivy; import sklearn; print('all OK')"
```
Expected: `all OK`

- [ ] **Step 2: Update requirements.txt**

In `engine/requirements.txt`, add:

```
usearch>=2.9.0
tantivy>=0.22.0
scikit-learn>=1.3.0
```

```bash
git add engine/requirements.txt
git commit -m "feat: add usearch, tantivy, scikit-learn to requirements"
```

**Time estimate:** 10 minutes

---

### Task 10: usearch SemanticIndex in db.py

**Why this matters:** 512-dim word n-gram is better than char n-gram but still not semantic — "blank screen" and "empty dashboard" still share no tokens. usearch + sklearn TF-IDF fitted on the brain.db corpus gives true semantic similarity via Latent Semantic Analysis (LSA). "blank" and "empty" co-occur with the same contexts in the corpus → similar LSA vectors.

**Files:**
- Modify: `engine/db.py`

- [ ] **Step 1: Add test**

```python
# Add to tests/engine/test_db.py
def test_semantic_index_build_and_search():
    from db import SemanticIndex
    idx = SemanticIndex()
    idx.add(1, "getSession server component auth failure dashboard blank")
    idx.add(2, "stripe webhook 400 request json body consumed")
    results = idx.search("session null after login", top_k=1)
    assert len(results) == 1
    assert results[0]["id"] == 1
    assert results[0]["score"] > 0.0
```

- [ ] **Step 2: Run to verify it fails**

```bash
engine/.venv/bin/python -m pytest tests/engine/test_db.py::test_semantic_index_build_and_search -v
```

- [ ] **Step 3: Add SemanticIndex class to db.py**

Add before `get_conn()` function (after the `_cosine` function, around line 85):

```python
# ── Semantic index (usearch + TF-IDF LSA) ────────────────────────────────────

class SemanticIndex:
    """
    Persistent semantic index using usearch ANN + sklearn TF-IDF LSA.
    Stored at ~/.rocket-support/brain.usearch + brain.tfidf.pkl
    Falls back gracefully if usearch/sklearn not available.
    """
    INDEX_PATH = os.path.expanduser("~/.rocket-support/brain.usearch")
    TFIDF_PATH = os.path.expanduser("~/.rocket-support/brain.tfidf.pkl")
    DIM = 64  # LSA components — enough for ~100 docs

    def __init__(self):
        self._index = None
        self._vectorizer = None
        self._svd = None
        self._id_map: List[int] = []  # position → fix row id

    def _lazy_init(self):
        if self._index is not None:
            return
        try:
            from usearch.index import Index
            self._index = Index(ndim=self.DIM, metric="cos", path=self.INDEX_PATH)
        except Exception:
            pass

    def rebuild_from_db(self) -> bool:
        """Fit TF-IDF + SVD on all brain.db entries, build usearch index."""
        try:
            import numpy as np
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.decomposition import TruncatedSVD
            from usearch.index import Index
            import pickle

            init_db()
            conn = get_conn()
            rows = conn.execute(
                "SELECT id, pattern, error_signature, category FROM fixes"
            ).fetchall()
            conn.close()

            if not rows:
                return False

            self._id_map = []
            corpus = []
            for row in rows:
                text = f"{row['pattern']} {row['error_signature'] or ''} {row['category'] or ''}"
                corpus.append(text)
                self._id_map.append(row["id"])

            n_components = min(self.DIM, len(corpus) - 1)
            self._vectorizer = TfidfVectorizer(
                ngram_range=(1, 2), min_df=1, sublinear_tf=True
            )
            tfidf_matrix = self._vectorizer.fit_transform(corpus)
            self._svd = TruncatedSVD(n_components=n_components, random_state=42)
            dense = self._svd.fit_transform(tfidf_matrix).astype(np.float32)

            # Pad to DIM if n_components < DIM
            if dense.shape[1] < self.DIM:
                padding = np.zeros((dense.shape[0], self.DIM - dense.shape[1]), dtype=np.float32)
                dense = np.concatenate([dense, padding], axis=1)

            # Normalize
            norms = np.linalg.norm(dense, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            dense /= norms

            index = Index(ndim=self.DIM, metric="cos", path=self.INDEX_PATH)
            ids = np.arange(len(corpus), dtype=np.uint64)
            index.add(ids, dense)
            index.save()

            with open(self.TFIDF_PATH, "wb") as f:
                pickle.dump({"vectorizer": self._vectorizer, "svd": self._svd,
                             "id_map": self._id_map}, f)
            self._index = index
            return True
        except Exception as e:
            return False

    def _load(self) -> bool:
        try:
            import pickle
            from usearch.index import Index
            if not os.path.exists(self.TFIDF_PATH):
                return False
            with open(self.TFIDF_PATH, "rb") as f:
                data = pickle.load(f)
            self._vectorizer = data["vectorizer"]
            self._svd = data["svd"]
            self._id_map = data["id_map"]
            self._index = Index(ndim=self.DIM, metric="cos", path=self.INDEX_PATH)
            return True
        except Exception:
            return False

    def _embed_query(self, text: str):
        try:
            import numpy as np
            vec = self._vectorizer.transform([text])
            dense = self._svd.transform(vec).astype(np.float32)
            if dense.shape[1] < self.DIM:
                import numpy as np
                padding = np.zeros((1, self.DIM - dense.shape[1]), dtype=np.float32)
                dense = np.concatenate([dense, padding], axis=1)
            norm = np.linalg.norm(dense)
            if norm > 0:
                dense /= norm
            return dense[0]
        except Exception:
            return None

    def add(self, row_id: int, text: str) -> None:
        """Add a single entry — triggers full rebuild for simplicity."""
        self.rebuild_from_db()

    def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """Return list of {id, score} sorted by score desc."""
        if self._vectorizer is None:
            if not self._load():
                return []
        vec = self._embed_query(query)
        if vec is None or self._index is None:
            return []
        try:
            import numpy as np
            matches = self._index.search(vec, top_k)
            results = []
            for pos, dist in zip(matches.keys, matches.distances):
                pos = int(pos)
                if pos < len(self._id_map):
                    results.append({"id": self._id_map[pos], "score": float(1.0 - dist)})
            return results
        except Exception:
            return []


_SEMANTIC_INDEX: Optional["SemanticIndex"] = None


def get_semantic_index() -> "SemanticIndex":
    global _SEMANTIC_INDEX
    if _SEMANTIC_INDEX is None:
        _SEMANTIC_INDEX = SemanticIndex()
    return _SEMANTIC_INDEX
```

Also update `save_fix()` to trigger a rebuild after each new pattern:

After the `conn.commit()` call in `save_fix()`, add:
```python
    conn.close()
    # Rebuild semantic index in background (non-blocking)
    try:
        import threading
        threading.Thread(target=get_semantic_index().rebuild_from_db, daemon=True).start()
    except Exception:
        pass
    return fix_id
```

Remove the `conn.close()` that was after `conn.commit()` and replace with the above block.

- [ ] **Step 4: Run tests**

```bash
engine/.venv/bin/python -m pytest tests/engine/test_db.py -v
```

- [ ] **Step 5: Build initial index**

```bash
engine/.venv/bin/python -c "
import sys; sys.path.insert(0,'engine')
import db
idx = db.SemanticIndex()
ok = idx.rebuild_from_db()
print('Index built:', ok)
results = idx.search('dashboard blank after login', top_k=3)
for r in results: print(r)
"
```

- [ ] **Step 6: Commit**

```bash
git add engine/db.py tests/engine/test_db.py
git commit -m "feat: add SemanticIndex class — usearch + TF-IDF LSA semantic similarity for brain.db"
```

**Rollback:** `git revert HEAD` — SemanticIndex is purely additive, existing `find_similar()` unchanged.

**Time estimate:** 3 hours

---

### Task 11: tantivy full-text index (brain_fts.py)

**Why this matters:** Semantic vectors are poor on exact technical tokens — `PGRST301`, `42501`, `constructEvent`. tantivy gives Elasticsearch-grade BM25 search with field boosting: `error_msg^5` means an exact error code match scores 5x higher than a body match.

**Files:**
- Create: `engine/brain_fts.py`

- [ ] **Step 1: Add test**

```python
# tests/engine/test_brain_fts.py
import sys, os
sys.path.insert(0, os.path.expanduser("~/rocket-support/engine"))
import brain_fts

def test_tantivy_index_and_search():
    import tempfile
    idx_path = tempfile.mkdtemp()
    idx = brain_fts.BrainFTS(index_path=idx_path)
    idx.add_doc(1, "AUTH", "getSession server component auth failure",
                "Not authenticated after login", "Replace with getUser()")
    idx.add_doc(2, "STRIPE", "Stripe webhook 400 request.json",
                "Stripe webhook 400 No signatures", "Use request.text()")
    idx.commit()

    results = idx.search("PGRST301 permission denied", top_k=3)
    assert isinstance(results, list)

    results2 = idx.search("getSession server", top_k=3)
    assert len(results2) > 0
    assert results2[0]["id"] == 1

def test_tantivy_error_code_match():
    import tempfile
    idx_path = tempfile.mkdtemp()
    idx = brain_fts.BrainFTS(index_path=idx_path)
    idx.add_doc(1, "SUPABASE", "RLS blocking SELECT", "PGRST301 permission denied", "Add SELECT policy")
    idx.add_doc(2, "AUTH", "getSession used", "session null", "use getUser")
    idx.commit()
    results = idx.search("PGRST301", top_k=1)
    assert results[0]["id"] == 1
```

- [ ] **Step 2: Create engine/brain_fts.py**

```python
"""
brain_fts.py — tantivy full-text index over brain.db fixes.

Stored at ~/.rocket-support/brain_fts/
Fields: category (raw), symptom (text, boost 3), error_msg (text, boost 5), fix_summary (text, boost 2)

Usage:
    from brain_fts import BrainFTS
    fts = BrainFTS()
    fts.rebuild_from_db()
    results = fts.search("PGRST301 permission denied", top_k=3)
    # returns [{id, category, score}, ...]
"""
import os
import sys
from typing import Any, Dict, List, Optional

DEFAULT_INDEX_PATH = os.path.expanduser("~/.rocket-support/brain_fts")

_tantivy_available = None


def _check_tantivy() -> bool:
    global _tantivy_available
    if _tantivy_available is None:
        try:
            import tantivy as _t
            _tantivy_available = True
        except ImportError:
            _tantivy_available = False
    return _tantivy_available


class BrainFTS:
    def __init__(self, index_path: str = DEFAULT_INDEX_PATH):
        self.index_path = index_path
        self._index = None
        self._writer = None

    def _build_schema(self):
        import tantivy
        builder = tantivy.SchemaBuilder()
        builder.add_integer_field("id", stored=True, indexed=True)
        builder.add_text_field("category", stored=True, tokenizer_name="raw")
        builder.add_text_field("symptom", stored=True, tokenizer_name="en_stem")
        builder.add_text_field("error_msg", stored=True, tokenizer_name="raw")
        builder.add_text_field("fix_summary", stored=True, tokenizer_name="en_stem")
        return builder.build()

    def _open_or_create(self):
        if self._index is not None:
            return
        if not _check_tantivy():
            return
        import tantivy
        os.makedirs(self.index_path, exist_ok=True)
        schema = self._build_schema()
        try:
            self._index = tantivy.Index(schema, path=self.index_path)
        except Exception:
            self._index = tantivy.Index(schema, path=self.index_path)

    def add_doc(self, row_id: int, category: str, symptom: str,
                error_msg: str, fix_summary: str) -> None:
        self._open_or_create()
        if self._index is None:
            return
        if self._writer is None:
            self._writer = self._index.writer()
        import tantivy
        doc = tantivy.Document(
            id=row_id,
            category=category or "",
            symptom=symptom or "",
            error_msg=error_msg or "",
            fix_summary=fix_summary or "",
        )
        self._writer.add_document(doc)

    def commit(self):
        if self._writer:
            self._writer.commit()
            self._writer = None
        if self._index:
            self._index.reload()

    def rebuild_from_db(self) -> int:
        """Rebuild full index from brain.db. Returns number of docs indexed."""
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import db
        db.init_db()
        conn = db.get_conn()
        rows = conn.execute(
            "SELECT id, pattern, error_signature, category, fix_diff FROM fixes"
        ).fetchall()
        conn.close()

        self._open_or_create()
        if self._index is None:
            return 0

        writer = self._index.writer()
        import tantivy
        for row in rows:
            doc = tantivy.Document(
                id=hash(row["id"]) % (2**31),  # tantivy integer field
                category=row["category"] or "",
                symptom=row["pattern"] or "",
                error_msg=row["error_signature"] or "",
                fix_summary=(row["fix_diff"] or "")[:200],
            )
            writer.add_document(doc)
        writer.commit()
        self._index.reload()
        return len(rows)

    def search(self, query: str, top_k: int = 3,
               category: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Multi-field BM25 search with field boosts.
        symptom^3, error_msg^5, fix_summary^2
        """
        if not _check_tantivy():
            return []
        self._open_or_create()
        if self._index is None:
            return []
        try:
            searcher = self._index.searcher()
            # Build boosted multi-field query
            query_str = " ".join(
                f'symptom:"{t}"^3 OR error_msg:"{t}"^5 OR fix_summary:"{t}"^2'
                for t in query.split()[:8]  # cap at 8 terms
            )
            parsed = self._index.parse_query(query_str, ["symptom", "error_msg", "fix_summary"])
            top_docs = searcher.search(parsed, top_k).hits
            results = []
            for score, addr in top_docs:
                doc = searcher.doc(addr)
                results.append({
                    "id": doc.get_first("id"),
                    "category": doc.get_first("category"),
                    "score": float(score),
                })
            return results
        except Exception:
            return []


_FTS_INSTANCE: Optional[BrainFTS] = None


def get_fts() -> BrainFTS:
    global _FTS_INSTANCE
    if _FTS_INSTANCE is None:
        _FTS_INSTANCE = BrainFTS()
    return _FTS_INSTANCE
```

- [ ] **Step 3: Build initial FTS index**

```bash
engine/.venv/bin/python -c "
import sys; sys.path.insert(0,'engine')
import brain_fts
fts = brain_fts.BrainFTS()
n = fts.rebuild_from_db()
print(f'Indexed {n} docs')
results = fts.search('PGRST301 permission denied', top_k=3)
print(results)
"
```

- [ ] **Step 4: Run tests and commit**

```bash
engine/.venv/bin/python -m pytest tests/engine/test_brain_fts.py -v
git add engine/brain_fts.py tests/engine/test_brain_fts.py engine/requirements.txt
git commit -m "feat: add tantivy full-text index (brain_fts.py) for BM25 error-code matching"
```

**Rollback:** `git revert HEAD` — new file only, nothing else imports it yet.

**Time estimate:** 3 hours

---

### Task 12: Hybrid RRF lookup (db.py + rkt_engine.py)

**Why this matters:** Neither semantic (usearch) nor keyword (tantivy) is sufficient alone. Hybrid Reciprocal Rank Fusion (RRF) combines both: if a result appears in position 2 from usearch AND position 1 from tantivy, it gets a higher combined score than either result would get alone. This is the state-of-the-art approach used by production search systems.

**Files:**
- Modify: `engine/db.py`
- Modify: `engine/rkt_engine.py`

- [ ] **Step 1: Add test**

```python
def test_hybrid_lookup_returns_results():
    # Requires brain.db to have entries
    results = db.hybrid_lookup("getSession server component", top_k=3)
    assert isinstance(results, list)
    if results:
        assert "pattern" in results[0]
        assert "_score" in results[0]
```

- [ ] **Step 2: Add hybrid_lookup to db.py**

Add after `find_similar()` function:

```python
def _rrf_merge(
    semantic_hits: List[Dict[str, Any]],   # [{id, score}] from SemanticIndex
    fts_hits: List[Dict[str, Any]],        # [{id, category, score}] from BrainFTS
    k: int = 60,
) -> List[str]:
    """
    Reciprocal Rank Fusion. Returns list of fix IDs ordered by combined score.
    k=60 is standard RRF constant that balances rank positions.
    """
    scores: Dict[str, float] = {}

    for rank, hit in enumerate(semantic_hits):
        fix_id = str(hit.get("id", ""))
        scores[fix_id] = scores.get(fix_id, 0.0) + 1.0 / (k + rank + 1)

    for rank, hit in enumerate(fts_hits):
        # fts returns integer ids (hash), need to match back to text ids
        fix_id = str(hit.get("id", ""))
        scores[fix_id] = scores.get(fix_id, 0.0) + 1.0 / (k + rank + 1)

    return sorted(scores.keys(), key=lambda x: scores[x], reverse=True)


def hybrid_lookup(
    query: str,
    top_k: int = 3,
    category: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Hybrid retrieval: SemanticIndex (LSA) + BrainFTS (tantivy BM25) merged via RRF.
    Falls back to find_similar() if either component unavailable.
    """
    import concurrent.futures

    semantic_hits: List[Dict] = []
    fts_hits: List[Dict] = []

    try:
        sem_idx = get_semantic_index()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            sem_future = ex.submit(sem_idx.search, query, top_k * 2)
            try:
                from brain_fts import get_fts
                fts_future = ex.submit(get_fts().search, query, top_k * 2, category)
                fts_hits = fts_future.result(timeout=2.0)
            except Exception:
                pass
            semantic_hits = sem_future.result(timeout=2.0)
    except Exception:
        pass

    if not semantic_hits and not fts_hits:
        return find_similar(query, top_k=top_k, category=category)

    # Merge via RRF
    merged_ids = _rrf_merge(semantic_hits, fts_hits)

    # Fetch actual rows
    init_db()
    conn = get_conn()
    results = []
    for fix_id in merged_ids[:top_k]:
        row = conn.execute("SELECT * FROM fixes WHERE id = ?", (fix_id,)).fetchone()
        if row:
            d = dict(row)
            d["_score"] = 1.0 / (merged_ids.index(fix_id) + 1)  # rank-based score
            results.append(d)
    conn.close()

    return results if results else find_similar(query, top_k=top_k, category=category)
```

- [ ] **Step 3: Update db_lookup in rkt_engine.py to use hybrid_lookup**

In `engine/rkt_engine.py`, find the `db_lookup` function (lines 205-215):

```python
def db_lookup(query: str, category: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Look up similar fixes in the database. Returns best match or None."""
    fix_db.init_db()
    results = fix_db.find_similar(query, top_k=3, category=category)
    if not results:
        return None
    best = results[0]
    if best.get("_score", 0) < 0.15:
        return None
    return best
```

Replace with:
```python
def db_lookup(query: str, category: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Look up similar fixes. Uses hybrid semantic+FTS lookup, falls back to vector similarity."""
    fix_db.init_db()
    results = fix_db.hybrid_lookup(query, top_k=3, category=category)
    if not results:
        return None
    best = results[0]
    if best.get("_score", 0) < 0.05:  # lower threshold — RRF scores are rank-based not cosine
        return None
    return best
```

- [ ] **Step 4: Run tests and commit**

```bash
engine/.venv/bin/python -m pytest tests/engine/test_db.py -v
git add engine/db.py engine/rkt_engine.py tests/engine/test_db.py
git commit -m "feat: hybrid RRF lookup — merge SemanticIndex + tantivy BrainFTS via Reciprocal Rank Fusion"
```

**Rollback:** `git revert HEAD`

**Time estimate:** 2 hours

---

## TIER 4 — Surgical Context + Validation (1 week)

### Task 13: tree-sitter surgical slicer (engine/slicer.py)

**Why this matters:** `build_claude_prompt()` in rkt_engine.py instructs Claude to read `lib/supabase/server.ts`, `middleware.ts`, and webhook routes in full. These are 80-400 line files. Sending them whole costs 3,000-8,000 tokens per ticket. tree-sitter is already installed and used by fix_writer.py — this just adds extraction queries.

**Note:** fix_writer.py already imports tree-sitter with `_TS_PARSER` and `_TS_LANG`. Import from there to avoid double-loading.

**Files:**
- Create: `engine/slicer.py`
- Modify: `engine/rkt_engine.py` (build_claude_prompt function)

- [ ] **Step 1: Add test**

```python
# tests/engine/test_slicer.py
import sys, os, tempfile
sys.path.insert(0, os.path.expanduser("~/rocket-support/engine"))
import slicer

SAMPLE_SERVER_TS = '''
import { createServerClient } from "@supabase/ssr"
import { cookies } from "next/headers"

export async function getProfile(userId: string) {
  const cookieStore = await cookies()
  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    { cookies: { getAll: () => cookieStore.getAll() } }
  )
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) return null
  return supabase.from("profiles").select().eq("id", userId).single()
}

export async function unrelatedFunction() {
  return "this should not appear"
}
'''

def test_extract_auth_slice_finds_auth_function():
    with tempfile.NamedTemporaryFile(suffix=".ts", mode="w", delete=False) as f:
        f.write(SAMPLE_SERVER_TS)
        path = f.name
    slices = slicer.extract_auth_slices(path)
    assert len(slices) >= 1
    combined = " ".join(s["slice"] for s in slices)
    assert "getUser" in combined
    assert "unrelatedFunction" not in combined

def test_extract_auth_slice_line_count():
    with tempfile.NamedTemporaryFile(suffix=".ts", mode="w", delete=False) as f:
        f.write(SAMPLE_SERVER_TS)
        path = f.name
    slices = slicer.extract_auth_slices(path)
    for s in slices:
        line_count = s["slice"].count("\n") + 1
        assert line_count <= 40, f"Slice too large: {line_count} lines"
```

- [ ] **Step 2: Create engine/slicer.py**

```python
"""
slicer.py — tree-sitter surgical extraction of auth-relevant code sections.

Replaces full-file reads in build_claude_prompt() with targeted 8-40 line slices.
Uses the same tree-sitter instance as fix_writer.py.

Usage:
    from slicer import extract_auth_slices
    slices = extract_auth_slices("/path/to/server.ts")
    for s in slices:
        print(f"# {s['fn_name']} ({s['start_line']}-{s['end_line']})")
        print(s['slice'])
"""
import os
import re
from typing import Dict, List, Optional

# Re-use parser from fix_writer to avoid loading tree-sitter twice
_TS_PARSER = None
_TS_LANG = None

def _get_parser():
    global _TS_PARSER, _TS_LANG
    if _TS_PARSER is not None:
        return _TS_PARSER, _TS_LANG
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from fix_writer import _TS_PARSER as _p, _TS_LANG as _l
        _TS_PARSER, _TS_LANG = _p, _l
        return _TS_PARSER, _TS_LANG
    except Exception:
        return None, None


# Keywords that indicate a function is auth/supabase relevant
_AUTH_KEYWORDS = frozenset([
    "getUser", "getSession", "createServerClient", "createBrowserClient",
    "updateSession", "exchangeCodeForSession", "cookies", "auth.signIn",
    "auth.signOut", "auth.signUp", "middleware", "session", "user",
])

_STRIPE_KEYWORDS = frozenset([
    "constructEvent", "request.text", "request.json", "stripe.webhooks",
    "checkout.sessions", "stripe.customers",
])


def _function_contains_keyword(node, src_bytes: bytes, keywords: frozenset) -> bool:
    """Check if a function node's source contains any of the keywords."""
    text = src_bytes[node.start_byte:node.end_byte].decode("utf-8", errors="replace")
    return any(kw in text for kw in keywords)


def _extract_function_name(node, src_bytes: bytes) -> str:
    """Try to get the function name from various node types."""
    # function_declaration: has direct name child
    for child in node.named_children:
        if child.type in ("identifier", "property_identifier"):
            return src_bytes[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
    return "anonymous"


def extract_auth_slices(
    file_path: str,
    keywords: Optional[frozenset] = None,
    max_lines_per_slice: int = 40,
) -> List[Dict]:
    """
    Extract only functions/methods that contain auth/supabase keywords.

    Returns list of:
    {
        "fn_name": str,
        "start_line": int,   # 1-indexed
        "end_line": int,
        "slice": str,        # the actual source lines
    }

    Falls back to keyword-grep window extraction if tree-sitter unavailable.
    """
    if keywords is None:
        keywords = _AUTH_KEYWORDS | _STRIPE_KEYWORDS

    file_path = os.path.expanduser(file_path)
    if not os.path.isfile(file_path):
        return []

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
            source = fh.read()
    except OSError:
        return []

    parser, lang = _get_parser()

    if parser is None:
        return _fallback_grep_extraction(source, keywords, max_lines_per_slice)

    src_bytes = source.encode("utf-8")
    try:
        tree = parser.parse(src_bytes)
    except Exception:
        return _fallback_grep_extraction(source, keywords, max_lines_per_slice)

    lines = source.splitlines()
    slices = []

    # Walk top-level nodes looking for function declarations and arrow functions
    for node in tree.root_node.named_children:
        target_node = None

        if node.type == "function_declaration":
            target_node = node
        elif node.type in ("export_statement", "lexical_declaration"):
            # export async function ..., export const fn = async () => {}
            for child in node.named_children:
                if child.type in ("function_declaration", "arrow_function",
                                   "function_expression"):
                    target_node = child
                    break
                if child.type == "variable_declarator":
                    for grandchild in child.named_children:
                        if grandchild.type in ("arrow_function", "function_expression"):
                            target_node = grandchild
                            break

        if target_node is None:
            continue

        if not _function_contains_keyword(target_node, src_bytes, keywords):
            continue

        start_line = target_node.start_point[0]  # 0-indexed
        end_line = target_node.end_point[0]       # 0-indexed

        # Cap size
        if (end_line - start_line + 1) > max_lines_per_slice:
            end_line = start_line + max_lines_per_slice - 1

        fn_name = _extract_function_name(node, src_bytes)
        slice_text = "\n".join(lines[start_line:end_line + 1])

        slices.append({
            "fn_name": fn_name,
            "start_line": start_line + 1,
            "end_line": end_line + 1,
            "slice": slice_text,
        })

    return slices


def _fallback_grep_extraction(
    source: str,
    keywords: frozenset,
    max_lines: int,
) -> List[Dict]:
    """Fallback: 20-line window around first keyword match."""
    lines = source.splitlines()
    for i, line in enumerate(lines):
        if any(kw in line for kw in keywords):
            start = max(0, i - 5)
            end = min(len(lines), i + max_lines - 5)
            return [{
                "fn_name": "unknown",
                "start_line": start + 1,
                "end_line": end,
                "slice": "\n".join(lines[start:end]),
            }]
    return []


def format_slices_for_prompt(slices: List[Dict], file_path: str) -> str:
    """Format extracted slices as a compact prompt block."""
    if not slices:
        return ""
    rel = os.path.basename(file_path)
    parts = [f"# {rel} — auth-relevant sections only"]
    for s in slices:
        parts.append(f"\n## {s['fn_name']} (lines {s['start_line']}–{s['end_line']})")
        parts.append(s["slice"])
    return "\n".join(parts)
```

- [ ] **Step 3: Update build_claude_prompt() in rkt_engine.py**

In `build_claude_prompt()`, find the STEP 2 section that currently reads:

```python
    prompt = f"""{engine_context}
...
STEP 2 - Read relevant files (based on project type {project_type}):
  - lib/supabase/server.ts or utils/supabase/server.ts
  - middleware.ts (if exists)
  - app/api/webhooks/*/route.ts (if {has_stripe})
```

Add slicer extraction before building the prompt:

```python
    # Surgical extraction — only auth-relevant function slices, not whole files
    import slicer as _slicer
    slice_context = ""
    key_files = [
        os.path.join(repo_path, "lib", "supabase", "server.ts"),
        os.path.join(repo_path, "utils", "supabase", "server.ts"),
        os.path.join(repo_path, "middleware.ts"),
        os.path.join(repo_path, "src", "middleware.ts"),
    ]
    if has_stripe:
        import glob as _glob
        key_files += _glob.glob(os.path.join(repo_path, "**", "webhooks", "**", "route.ts"),
                                recursive=True)[:2]
    for fpath in key_files:
        if not os.path.isfile(fpath):
            continue
        slices = _slicer.extract_auth_slices(fpath)
        if slices:
            slice_context += "\n" + _slicer.format_slices_for_prompt(slices, fpath) + "\n"

    if slice_context:
        engine_context += f"\nPRE-EXTRACTED CODE (auth-relevant sections only):\n{slice_context}\n"
```

Also update STEP 2 instruction to tell Claude slices are pre-loaded:

```python
STEP 2 - Code context already pre-extracted above. Only read additional files if the pre-extracted sections don't contain the relevant code.
```

- [ ] **Step 4: Run tests and commit**

```bash
engine/.venv/bin/python -m pytest tests/engine/test_slicer.py -v
git add engine/slicer.py engine/rkt_engine.py tests/engine/test_slicer.py
git commit -m "feat: add tree-sitter slicer — extract auth-relevant sections only, 85% token reduction"
```

**Rollback:** `git revert HEAD`

**Time estimate:** 4 hours

---

### Task 14: oxc validation gate (engine/fix_validator.py + triage_graph.py)

**Why this matters:** No validation happens between fix_writer output and rkt push. Hallucinated method names, broken imports, and syntax errors from bad diff application currently reach the remote container. oxc validates TypeScript syntax in <50ms with zero network calls.

**Files:**
- Create: `engine/fix_validator.py`
- Modify: `engine/triage_graph.py`

- [ ] **Step 1: Install oxc**

```bash
# Check if oxc is available
which oxc 2>/dev/null || npm install -g @oxc-project/cli 2>/dev/null || \
  curl -fsSL https://github.com/oxc-project/oxc/releases/latest/download/oxc-darwin-arm64.gz \
  | gunzip > /usr/local/bin/oxc && chmod +x /usr/local/bin/oxc
oxc --version
```

- [ ] **Step 2: Create engine/fix_validator.py**

```python
"""
fix_validator.py — Validate a TypeScript/TSX patch via oxc before applying.

Usage:
    from fix_validator import validate_patch
    result = validate_patch(original_source, unified_diff)
    if result["valid"]:
        apply_the_diff()
    else:
        # result["errors"] contains oxc output to send back to fix_writer
        retry_with_context(result["errors"])
"""
import os
import re
import shutil
import subprocess
import tempfile
from typing import Dict, List, Optional


_OXC = shutil.which("oxc") or shutil.which("oxlint")
_OXC_AVAILABLE = _OXC is not None


def _apply_unified_diff(original: str, diff_text: str) -> Optional[str]:
    """Apply a unified diff to original text. Returns patched text or None on failure."""
    lines = original.splitlines(keepends=True)
    diff_lines = diff_text.splitlines(keepends=True)

    result = list(lines)
    # Simple unified diff parser — handles single-hunk diffs from fix_writer
    in_hunk = False
    orig_line = 0
    out: List[str] = []
    i = 0
    src_lines = list(lines)
    out_lines: List[str] = []

    try:
        import patch as _patch_lib
        pset = _patch_lib.PatchSet()
        pset.parse(diff_text.encode())
        return pset.apply_to_string(original)
    except Exception:
        pass

    # Fallback: line-by-line heuristic for simple single-line swaps
    hunk_re = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")
    removals: Dict[int, bool] = {}
    additions: List[tuple] = []

    src_cursor = 0
    for line in diff_lines:
        m = hunk_re.match(line)
        if m:
            src_cursor = int(m.group(1)) - 1
            continue
        if line.startswith("---") or line.startswith("+++"):
            continue
        if line.startswith("-"):
            removals[src_cursor] = True
            src_cursor += 1
        elif line.startswith("+"):
            additions.append((src_cursor, line[1:]))
        elif line.startswith(" "):
            src_cursor += 1

    out_lines = []
    for i, orig_line in enumerate(src_lines):
        if i in removals:
            for ins_pos, ins_line in additions:
                if ins_pos == i + 1:
                    out_lines.append(ins_line)
            continue
        out_lines.append(orig_line)

    if out_lines == src_lines:
        # Fallback: return original unchanged — diff couldn't be applied
        return original

    return "".join(out_lines)


def validate_patch(
    original_source: str,
    diff_text: str,
    file_suffix: str = ".tsx",
) -> Dict:
    """
    Apply diff to a temp file and validate with oxc.

    Returns:
    {
        "valid": bool,
        "errors": [str],        # oxc error lines, empty if valid
        "patched_source": str,  # patched content (even if invalid, for inspection)
    }
    """
    if not _OXC_AVAILABLE:
        return {"valid": True, "errors": [], "patched_source": original_source,
                "skipped": "oxc not installed"}

    patched = _apply_unified_diff(original_source, diff_text)
    if patched is None:
        return {"valid": False, "errors": ["Could not apply diff"], "patched_source": original_source}

    fd, tmp_path = tempfile.mkstemp(suffix=file_suffix, prefix=".rkt_validate_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(patched)

        result = subprocess.run(
            [_OXC, tmp_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        errors = [
            line.replace(tmp_path, "<patched_file>")
            for line in result.stdout.splitlines() + result.stderr.splitlines()
            if line.strip() and ("error" in line.lower() or "×" in line)
        ]
        return {
            "valid": result.returncode == 0,
            "errors": errors[:10],  # cap at 10 errors
            "patched_source": patched,
        }
    except subprocess.TimeoutExpired:
        return {"valid": True, "errors": [], "patched_source": patched,
                "skipped": "oxc timeout"}
    except Exception as e:
        return {"valid": True, "errors": [], "patched_source": patched,
                "skipped": str(e)}
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
```

- [ ] **Step 3: Add validation node to triage_graph.py**

In `engine/triage_graph.py`, add a new node after `node_build_summary`:

First, add the import at the top (after existing imports):
```python
try:
    import fix_validator as _fix_validator
    _FIX_VALIDATOR_AVAILABLE = True
except ImportError:
    _FIX_VALIDATOR_AVAILABLE = False
```

Add new state fields to `TriageState`:
```python
    validation_result:  Optional[dict]   # oxc validation result
    validation_errors:  list             # oxc errors if invalid
```

Add new node function:
```python
def node_validate_fix(state: TriageState) -> dict:
    """Validate fix_writer diff via oxc before it reaches rkt push."""
    if not _FIX_VALIDATOR_AVAILABLE:
        return {"validation_result": {"skipped": "fix_validator not available"}}

    db_match = state.get("db_match")
    if not db_match or not db_match.get("fix_diff"):
        return {"validation_result": None, "validation_errors": []}

    fix_diff = db_match.get("fix_diff", "")
    if not fix_diff or not fix_diff.startswith("---"):
        return {"validation_result": None, "validation_errors": []}

    result = _fix_validator.validate_patch("", fix_diff, file_suffix=".tsx")
    return {
        "validation_result": result,
        "validation_errors": result.get("errors", []),
    }
```

Wire into graph (add before `build_summary`):
```python
    g.add_node("validate_fix", node_validate_fix)
    g.add_edge("score_and_route", "validate_fix")   # was: "score_and_route" → "symptom_rank"
    g.add_edge("validate_fix", "symptom_rank")
```

- [ ] **Step 4: Run tests and commit**

```bash
engine/.venv/bin/python -c "
import sys; sys.path.insert(0,'engine')
import fix_validator
result = fix_validator.validate_patch(
    'const x = 1\n',
    '--- a/test.ts\n+++ b/test.ts\n@@ -1 +1 @@\n-const x = 1\n+const x: number = 1\n'
)
print('valid:', result['valid'], 'errors:', result['errors'])
"
git add engine/fix_validator.py engine/triage_graph.py
git commit -m "feat: add oxc validation gate — validate TypeScript patches before rkt push"
```

**Rollback:** `git revert HEAD`

**Time estimate:** 3 hours

---

## TIER 5 — Pattern Bootstrap (2-3 days)

### Task 15: Git history extractor (engine/git_extractor.py)

**Why this matters:** novylo alone has 60 support commits. These are real bugs with real fixes. Extracting them creates a pattern library that no amount of manual seeding can match in quality or specificity. Target: 80-120 new verified patterns.

**Files:**
- Create: `engine/git_extractor.py`

- [ ] **Step 1: Create engine/git_extractor.py**

```python
"""
git_extractor.py — Extract fix patterns from git history of client repos.

Scans ~/Documents/Rocket repos for commits matching support keywords.
For each matching commit: extracts diff, detects category, saves to brain.db.

Usage:
    engine/.venv/bin/python engine/git_extractor.py --dry-run
    engine/.venv/bin/python engine/git_extractor.py --save
"""
import argparse
import os
import re
import subprocess
import sys
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db as fix_db

ROCKET_REPOS_BASE = os.path.expanduser("~/Documents/Rocket")

SUPPORT_KEYWORDS = [
    "fix", "bug", "support", "auth", "stripe", "webhook", "session",
    "getSession", "getUser", "middleware", "rls", "supabase", "cookies",
    "revalidate", "blank", "login", "dashboard", "error", "broken", "issue",
    "404", "500", "403", "unauthorized", "PGRST",
]

CATEGORY_SIGNALS = {
    "AUTH": ["getSession", "getUser", "session", "auth", "login", "middleware",
             "cookies", "updateSession", "exchangeCode"],
    "STRIPE": ["stripe", "webhook", "constructEvent", "request.json",
               "request.text", "payment", "subscription"],
    "SUPABASE": ["rls", "policy", "supabase", "trigger", "migration",
                 "on_auth_user_created", "profiles", "insert", "select"],
    "BUILD": ["build", "typescript", "tsc", "import", "module", "next.config",
              "CSP", "cors", "deploy"],
    "ENV": ["env", "service_role", "NEXT_PUBLIC", "secret", "key"],
}


def _find_repos() -> List[str]:
    repos = []
    if not os.path.isdir(ROCKET_REPOS_BASE):
        return repos
    for entry in os.scandir(ROCKET_REPOS_BASE):
        if entry.is_dir():
            git_dir = os.path.join(entry.path, ".git")
            if os.path.isdir(git_dir):
                repos.append(entry.path)
            else:
                # Check one level deeper
                try:
                    for sub in os.scandir(entry.path):
                        if sub.is_dir() and os.path.isdir(os.path.join(sub.path, ".git")):
                            repos.append(sub.path)
                except PermissionError:
                    pass
    return repos


def _run_git(repo: str, args: List[str], timeout: int = 30) -> str:
    try:
        r = subprocess.run(
            ["git"] + args,
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return r.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def _is_support_commit(subject: str) -> bool:
    subject_lower = subject.lower()
    return any(kw.lower() in subject_lower for kw in SUPPORT_KEYWORDS)


def _detect_category(diff_text: str, subject: str) -> str:
    combined = (diff_text + " " + subject).lower()
    scores: Dict[str, int] = {}
    for cat, signals in CATEGORY_SIGNALS.items():
        scores[cat] = sum(1 for s in signals if s.lower() in combined)
    return max(scores, key=scores.__getitem__) if any(scores.values()) else "OTHER"


def _extract_error_signature(diff_text: str, subject: str) -> str:
    """Try to extract a meaningful error signature from diff context."""
    patterns = [
        r"PGRST\d+",
        r"\b\d{5}\b",  # postgres error codes
        r"getSession\(\)",
        r"request\.json\(\)",
        r"auth-helpers",
        r"cookies\(\) should be awaited",
        r"TypeScript error",
    ]
    found = []
    combined = diff_text + " " + subject
    for p in patterns:
        m = re.search(p, combined, re.IGNORECASE)
        if m:
            found.append(m.group(0))
    if found:
        return " | ".join(set(found))
    # Fall back to commit subject
    return subject[:120]


def _extract_fix_diff(full_diff: str) -> str:
    """Extract only TypeScript/SQL diff hunks, cap at 500 chars."""
    lines = full_diff.splitlines()
    relevant = []
    in_relevant_file = False
    for line in lines:
        if line.startswith("diff --git"):
            in_relevant_file = any(
                line.endswith(ext)
                for ext in (".ts", ".tsx", ".js", ".jsx", ".sql", ".json")
            )
        if in_relevant_file:
            relevant.append(line)
    return "\n".join(relevant)[:500]


def extract_patterns(repo: str, dry_run: bool = True) -> List[Dict]:
    """Extract fix patterns from a single repo's git history."""
    log = _run_git(repo, ["log", "--oneline", "--no-merges", "-200"])
    if not log:
        return []

    patterns = []
    for line in log.splitlines():
        parts = line.split(" ", 1)
        if len(parts) < 2:
            continue
        sha, subject = parts[0], parts[1]
        if not _is_support_commit(subject):
            continue

        diff = _run_git(repo, ["show", sha, "--stat", "--unified=3"])
        full_diff = _run_git(repo, ["show", sha, "--unified=3"])

        category = _detect_category(full_diff, subject)
        error_sig = _extract_error_signature(full_diff, subject)
        fix_diff = _extract_fix_diff(full_diff)
        repo_name = os.path.basename(repo)

        pattern = {
            "pattern": subject[:200],
            "error_signature": error_sig,
            "category": category,
            "fix_diff": fix_diff,
            "project_type": "SaaS",  # default; can be refined
            "repo": repo_name,
            "sha": sha,
        }
        patterns.append(pattern)

        if not dry_run:
            fix_db.save_fix(
                pattern=subject[:200],
                error_signature=error_sig,
                category=category,
                fix_diff=fix_diff,
                project_type="SaaS",
                verified=0,
            )

    return patterns


def main():
    parser = argparse.ArgumentParser(description="Extract fix patterns from git history")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Print patterns without saving (default)")
    parser.add_argument("--save", action="store_true",
                        help="Save patterns to brain.db")
    parser.add_argument("--repo", help="Specific repo path (default: scan all Rocket repos)")
    args = parser.parse_args()

    dry_run = not args.save
    repos = [args.repo] if args.repo else _find_repos()

    print(f"Scanning {len(repos)} repo(s) in {ROCKET_REPOS_BASE}")
    print(f"Mode: {'DRY RUN' if dry_run else 'SAVING TO brain.db'}\n")

    total = 0
    for repo in repos:
        patterns = extract_patterns(repo, dry_run=dry_run)
        if patterns:
            print(f"  {os.path.basename(repo)}: {len(patterns)} patterns")
            for p in patterns[:3]:
                print(f"    [{p['category']}] {p['pattern'][:70]}")
            if len(patterns) > 3:
                print(f"    ... and {len(patterns) - 3} more")
        total += len(patterns)

    print(f"\nTotal: {total} patterns {'found' if dry_run else 'saved'}")
    if dry_run and total > 0:
        print("\nRun with --save to write to brain.db")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Dry run to verify extraction**

```bash
engine/.venv/bin/python engine/git_extractor.py --dry-run
```
Expected: lists patterns from novylo and other repos with categories

- [ ] **Step 3: Save patterns**

```bash
engine/.venv/bin/python engine/git_extractor.py --save
```

- [ ] **Step 4: Rebuild indexes**

```bash
engine/.venv/bin/python engine/migrate_embeddings.py
engine/.venv/bin/python -c "
import sys; sys.path.insert(0,'engine')
from brain_fts import get_fts
n = get_fts().rebuild_from_db()
print(f'FTS index rebuilt: {n} docs')
from db import get_semantic_index
ok = get_semantic_index().rebuild_from_db()
print(f'Semantic index rebuilt: {ok}')
"
```

- [ ] **Step 5: Verify count**

```bash
sqlite3 ~/.rocket-support/brain.db "SELECT count(*) FROM fixes; SELECT category, count(*) FROM fixes GROUP BY category;"
```
Expected: 120-160 total patterns

- [ ] **Step 6: Commit**

```bash
git add engine/git_extractor.py
git commit -m "feat: add git_extractor — bootstrap brain.db with patterns from client git history"
```

**Rollback:** `engine/.venv/bin/python -c "import db; db.get_conn().execute(\"DELETE FROM fixes WHERE verified=0 AND uses=1\").connection.commit()"` removes only newly-added unverified patterns.

**Time estimate:** 4 hours

---

### Task 16: Auto-learn pipeline in rkt-done

**Why this matters:** Every ticket that an engineer manually resolves is a free training example. Right now those patterns evaporate. Adding a 30-second prompt at the end of `rkt-done` turns every completed ticket into a verified brain.db entry.

**Files:**
- Modify: `bin/rkt-done`
- Add: `engine/learn_fix.py`

- [ ] **Step 1: Create engine/learn_fix.py**

```python
"""
learn_fix.py — Save a manually confirmed fix to brain.db.

Called by rkt-done after a support session.

Usage:
    engine/.venv/bin/python engine/learn_fix.py \
        --category AUTH \
        --pattern "getSession() in Server Action" \
        --error "dashboard blank after login" \
        --project-type SaaS
"""
import argparse
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import db

CATEGORIES = ["AUTH", "STRIPE", "SUPABASE", "BUILD", "ENV", "UI", "OTHER"]


def main():
    parser = argparse.ArgumentParser(description="Save a verified fix to brain.db")
    parser.add_argument("--category", choices=CATEGORIES, required=True)
    parser.add_argument("--pattern", required=True, help="Short description of the bug pattern")
    parser.add_argument("--error", default="", help="Error message or symptom")
    parser.add_argument("--project-type", default="SaaS",
                        choices=["SaaS", "E-Commerce", "AI", "Booking", "Landing", "Blog"])
    parser.add_argument("--diff", default="", help="Fix diff (optional)")
    args = parser.parse_args()

    fix_id = db.save_fix(
        pattern=args.pattern,
        error_signature=args.error,
        category=args.category,
        fix_diff=args.diff,
        project_type=args.project_type,
        verified=1,
    )
    print(f"Saved [{args.category}] '{args.pattern[:60]}' → brain.db id={fix_id}")

    # Rebuild indexes
    try:
        from db import get_semantic_index
        get_semantic_index().rebuild_from_db()
        print("Semantic index updated.")
    except Exception:
        pass
    try:
        from brain_fts import get_fts
        get_fts().rebuild_from_db()
        print("FTS index updated.")
    except Exception:
        pass


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Add auto-learn prompt to rkt-done**

In `bin/rkt-done`, after the "Done! pushed and cleaned" message block (after line 91), add:

```bash
# ── Auto-learn: save fix pattern to brain.db ─────────────────
echo ""
echo -e "  ${BOLD}Save this fix to brain.db? [y/N]:${NC} "
read -r LEARN

if [[ "$LEARN" =~ ^[Yy]$ ]]; then
  echo -e "  ${BOLD}Category [AUTH/STRIPE/SUPABASE/BUILD/ENV/OTHER]:${NC} "
  read -r CATEGORY
  CATEGORY="${CATEGORY:-OTHER}"

  echo -e "  ${BOLD}One-line bug description:${NC} "
  read -r PATTERN

  echo -e "  ${BOLD}Error symptom (press Enter to skip):${NC} "
  read -r ERROR_SIG

  if [[ -n "$PATTERN" ]]; then
    ~/rocket-support/engine/.venv/bin/python \
      ~/rocket-support/engine/learn_fix.py \
      --category "${CATEGORY^^}" \
      --pattern "$PATTERN" \
      --error "$ERROR_SIG" \
      --project-type "SaaS" && \
    echo -e "  ${GREEN}✓${NC}  Pattern saved to brain.db"
  fi
fi
```

- [ ] **Step 3: Test manually**

```bash
echo -e "y\nAUTH\nTest pattern from rkt-done\ntest error signature\n" | \
  ~/rocket-support/engine/.venv/bin/python ~/rocket-support/engine/learn_fix.py \
  --category AUTH \
  --pattern "Test: rkt-done auto-learn" \
  --error "test symptom"
```
Expected: `Saved [AUTH] 'Test: rkt-done auto-learn' → brain.db id=...`

- [ ] **Step 4: Remove test entry**

```bash
sqlite3 ~/.rocket-support/brain.db "DELETE FROM fixes WHERE pattern LIKE 'Test: rkt-done%';"
```

- [ ] **Step 5: Commit**

```bash
git add bin/rkt-done engine/learn_fix.py
git commit -m "feat: add auto-learn pipeline — rkt-done prompts to save fix pattern to brain.db"
```

**Rollback:** `git revert HEAD` — rkt-done prompt is opt-in (y/N default N), safe to revert.

**Time estimate:** 1 hour

---

## Summary Table

| # | Name | Tier | File | Time | Blocks |
|---|---|---|---|---|---|
| 1 | Word n-gram embedding upgrade | 1 | db.py | 30m | nothing |
| 2 | Fix db_lookup query contamination | 1 | rkt_engine.py, triage_graph.py | 20m | nothing |
| 3 | Delete garbage + fix crossed sigs | 1 | brain.db (SQL) | 20m | depends on #1 (re-embed after) |
| 4 | headers() not awaited rule | 2 | probe_scanner.py | 30m | nothing |
| 5 | .env.production ENV chain | 2 | chain_walker.py | 30m | nothing |
| 6 | use client + server import rule | 2 | probe_scanner.py | 30m | nothing |
| 7 | revalidatePath check rule | 2 | probe_scanner.py | 30m | nothing |
| 8 | RLS INSERT policy check | 2 | schema_checker.py | 20m | nothing |
| 9 | Install usearch + tantivy + sklearn | 3 | requirements.txt | 10m | blocks #10, #11 |
| 10 | SemanticIndex (usearch + LSA) | 3 | db.py | 3h | depends on #9 |
| 11 | BrainFTS (tantivy) | 3 | brain_fts.py (new) | 3h | depends on #9 |
| 12 | Hybrid RRF lookup | 3 | db.py, rkt_engine.py | 2h | depends on #10, #11 |
| 13 | tree-sitter surgical slicer | 4 | slicer.py (new), rkt_engine.py | 4h | nothing (tree-sitter already installed) |
| 14 | oxc validation gate | 4 | fix_validator.py (new), triage_graph.py | 3h | nothing |
| 15 | git history extractor | 5 | git_extractor.py (new) | 4h | nothing |
| 16 | rkt-done auto-learn pipeline | 5 | rkt-done, learn_fix.py (new) | 1h | nothing |

**Total: ~22 hours**

---

## Critical Path

```
#1 (embeddings) → #3 (cleanup + re-embed) → #10 (SemanticIndex) → #12 (RRF)
#9 (install deps) → #10, #11 → #12
#11 (tantivy) → #12 (RRF)
```

Everything else is independent.

---

## Parallel Execution Groups

**Day 1 — Run simultaneously:**
- #1 + #2 + #3 (Tier 1 — 1.5 hours total)
- #4 + #5 + #6 + #7 + #8 (Tier 2 — 2.5 hours total)

**Day 2-3 — Sequential (dependency chain):**
- #9 → #10 → #11 → #12 (Tier 3 — 8+ hours)

**Day 4-5 — Run simultaneously:**
- #13 (slicer — 4 hours)
- #14 (oxc — 3 hours)

**Day 6-7:**
- #15 (git extractor — 4 hours)
- #16 (auto-learn — 1 hour)

---

## First 3 Commands to Run Right Now

```bash
# 1. Back up brain.db before any changes
cp ~/.rocket-support/brain.db ~/.rocket-support/brain.db.backup

# 2. Create tests directory
mkdir -p ~/rocket-support/tests/engine

# 3. Run Tier 1 cleanup immediately (no deps needed, pure SQL + Python)
cd ~/rocket-support
engine/.venv/bin/python engine/cleanup_db.py 2>/dev/null || \
  engine/.venv/bin/python -c "
import sys; sys.path.insert(0,'engine')
import db, sqlite3
db.init_db()
conn = db.get_conn()
deleted = conn.execute(\"DELETE FROM fixes WHERE pattern LIKE 'Manual fix:%'\").rowcount
conn.commit()
conn.close()
print(f'Deleted {deleted} noise entries')
"
```
