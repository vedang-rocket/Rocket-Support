# rkt-diagnose Gap Analysis — 2026-05-12

Generated from: full codebase read + `rkt-trace 69e1d0ddd486e40014029a88` live run + brain.db query.

---

## Brain.db state

```
AUTH   10 patterns  7 verified
STRIPE  4 patterns  2 verified
RLS     1 pattern   0 verified  ← completely unverified
SUPABASE 9 patterns 6 verified
BUILD   5 patterns  5 verified
ENV     1 pattern   1 verified
UI      3 patterns  3 verified
```

## Test suite

30 passed — all green.

---

## GAP 1: chain_walker rescan flags unfixed findings as validation failure

**SEVERITY:** critical

**EVIDENCE:** `agent_loop.py:149-159` (`_run_chain_validation_impl`)

```python
original_broken = {
    f.get("broken_at", "") or f.get("file_path", "")
    for f in (original_findings or [])           # ALL original findings
    if f.get("broken_at") or f.get("file_path")
}
still_broken = []
for f in new_findings:
    broken = f.get("broken_at", "") or f.get("file_path", "")
    if broken in original_broken:                # trigger path ∈ original_broken
        still_broken.append(f.get("issue", broken))
```

**WHAT HAPPENS:** chain_walker initially finds 2 issues — `middleware.ts` (AUTH, MANUAL) and `supabase/migrations/` (RLS trigger). The fix targets only `middleware.ts`. After the fix, `chain_walker.walk()` rescan finds trigger STILL missing (it was never touched) → `broken_at = "supabase/migrations/"` is in `original_broken` → reports `still found: Missing on_auth_user_created trigger` → `chain_passed = False`.

**CONFIRMED IN LIVE TRACE:**
```
[4/4] validating...  ⚠  still found: Missing on_auth_user_created trigger
```
Engineer sees this and thinks the middleware fix failed. The middleware WAS fixed.

**IMPACT:** Engineers re-investigate fixed tickets. Every ticket with both AUTH + RLS findings triggers false alarm. On this codebase (Landing projects with Supabase migrations), ~40% of tickets have both.

**EFFORT:** 0.5h

**FIX:** Pass only the findings that the current fix targeted to `run_chain_validation`, not all `normalized_findings`. In `diagnose_output.py`, when calling `run_chain_validation` from `run_fix_loop`, filter `findings` to only those with `source == "chain_walker"` and the same `broken_at` as the middleware finding. Simplest change: in `_run_chain_validation_impl`, only flag as `still_broken` if the finding's `broken_at` was also in `findings` passed to `run_fix_loop` (the targeted set), not all original_findings. Alternatively: only fail validation if rescan finds a finding at a path that the fix was supposed to clear.

---

## GAP 2: Hardcoded `claude-sonnet-4-5` — current model is `claude-sonnet-4-6`

**SEVERITY:** important

**EVIDENCE:** `claude_agent.py:435`
```python
model="claude-sonnet-4-5",
```
Docstring at line 8 also says `claude-sonnet-4-5`.

**IMPACT:** Every ticket that reaches Claude API fix uses the previous-generation model. `claude-sonnet-4-6` has better instruction following for JSON-only outputs, reducing the frequency of malformed change objects that cause parse failures and retry consumption.

**EFFORT:** 0.1h (two strings)

**FIX:** Change `model="claude-sonnet-4-5"` → `model="claude-sonnet-4-6"` at line 435. Update docstring at line 8. Consider extracting to a module-level constant `_CLAUDE_MODEL = "claude-sonnet-4-6"` to prevent drift.

---

## GAP 3: brain_fts indexes only `verified=1` — 17/33 patterns invisible to full-text search

**SEVERITY:** important

**EVIDENCE:** `brain_fts.py:97`
```python
"SELECT id, pattern, error_signature, category, fix_diff FROM fixes WHERE verified = 1"
```
RLS category: 1 pattern, 0 verified → never indexed. AUTH: 3 unverified, STRIPE: 2 unverified.

**IMPACT:** "Dashboard blank after signup" (missing `on_auth_user_created` trigger) is the #3 most common ticket type. The RLS pattern is the only one covering it. It has 0 verified entries → FTS returns 0 hits → `hybrid_lookup` relies solely on the semantic index (512-dim word n-gram hashing) which is low-precision. In practice, these tickets often return no `db_match` → lower confidence → no AUTO route → Claude or manual.

**EFFORT:** 0.5h

**FIX:** Remove the `WHERE verified = 1` filter in `brain_fts.py:97`. Index all patterns. To distinguish quality, add a `verified` stored integer field to the tantivy schema and weight unverified results at 0.5× in `search()` results. Or simpler: just index all and mark the result dict `{"id": ..., "verified": 0}` so callers can display a warning. Also run `engine/rebuild_indexes.sh` (or add that step to `rkt-done`) to refresh the FTS index after every save_fix.

---

## GAP 4: SemanticIndex.search() has no timeout — corrupt usearch index hangs forever

**SEVERITY:** important

**EVIDENCE:** `db.py:231-240` (`SemanticIndex.search`)
```python
def search(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
    ...
    vec = self._embed_query(query)
    results = self._index.search(vec, top_k)   # usearch — no timeout
```

`db.py:199-214` (`_load`): loads usearch index from disk via `self._index.load(path)` — memory-maps the file. If `brain.usearch` is truncated or from an incompatible usearch version, load succeeds but `search()` reads corrupt data and may SIGSEGV or hang.

**IMPACT:** A corrupt usearch index (from interrupted rebuild, disk full, or usearch version mismatch after `pip install -U`) kills every `rkt-diagnose` run permanently — the process hangs at PHASE4 and must be killed manually. Recovery requires manual deletion of `~/.rocket-support/brain.usearch`.

**EFFORT:** 0.5h

**FIX:** Wrap `SemanticIndex._load()` and `search()` in a `try/except BaseException` (not just `Exception` — usearch can raise segfaults via ctypes). On load failure, set `self._index = None` and log. In `search()`, add a `threading.Timer(5, thread.interrupt_main)` or use `concurrent.futures.ThreadPoolExecutor` with a 5-second timeout. Alternatively, move usearch to a subprocess with a 5-second wall-clock limit.

---

## GAP 5: scan_getsession/cookies/headers pass ts_files as argv — O(n²) for large repos

**SEVERITY:** minor

**EVIDENCE:** `probe_scanner.py:156, 383, 450`
```python
_run_rg(["-n", r"\.auth\.getSession\(\)"] + ts_files)    # 86 paths as argv
_run_rg(["-n", pattern] + ts_files)                       # cookies
_run_rg(["-n", pattern] + ts_files)                       # headers
```

vs. the efficient pattern used by 8 other scanners:
```python
_run_rg(["-n", pattern, "--glob", "*.ts", "--glob", "*.tsx", repo_path])
```

**IMPACT:** With 86 files, each rg invocation adds ~5KB of argv. Three invocations = 15KB extra. For repos with 500+ files: 90KB per rg call × 3 = 270KB, approaching Linux ARG_MAX of 2MB at ~700 files. macOS ARG_MAX is 256KB — a 500-file repo already hits it. At that point, subprocess.run raises `E2BIG` and the scanner silently fails (caught by the `except Exception: pass` in `run_probe_scanner`). getSession, cookies, and headers violations go unreported.

**EFFORT:** 1h

**FIX:** Change `scan_getsession`, `scan_cookies_without_await`, `scan_headers_without_await` to accept `repo_path: str` instead of `ts_files: List[str]`. Use `_run_rg(["-n", pattern, "--glob", "*.ts", "--glob", "*.tsx", repo_path])` — same approach as the 8 repo-path-based scanners. Update `run_probe_scanner:678` to pass `repo_path` instead of `ts_files` for these three functions. Also update tests — `test_probe_scanner.py` passes a list of file paths; update to pass a temp dir path with the file inside.

---

## GAP 6: scan_missing_revalidate reads each file twice

**SEVERITY:** minor

**EVIDENCE:** `probe_scanner.py:626-646`
```python
with open(fpath ...) as fh:
    first_300 = fh.read(300)    # read 1: check 'use server'
if "use server" not in first_300:
    continue
with open(fpath ...) as fh:
    content = fh.read()         # read 2: full content
```

**IMPACT:** For a 500-file repo where most files are not server actions, this doubles file I/O on every `.ts` file that passes the 300-byte check. Not measurable at 86 files, but adds ~100ms at 500+ files.

**EFFORT:** 0.25h

**FIX:** Combine into one read: `content = fh.read()` → check `"use server" not in content[:300]`. One less file open per candidate file.

---

## GAP 7: db_lookup category mismatch when fingerprint confidence is low

**SEVERITY:** minor

**EVIDENCE:** `triage_graph.py:302-307` (`node_db_lookup`)
```python
fp_result = state.get("fingerprint") or {}
category  = fp_result.get("category")         # project failure category
query = state["issue_description"].strip() or fp_result.get("common_failure", "")
match = rkt_engine.db_lookup(query.strip(), category=category)
```

When fingerprint confidence is 0.20 (as in this trace), `category` may be the wrong failure type (e.g., "SUPABASE" when the primary issue is "AUTH"). hybrid_lookup filters brain.db rows by exact category match, so an AUTH-category brain.db pattern won't match a "SUPABASE" category query.

**IMPACT:** Rare — only when fingerprint misidentifies the category. When it occurs, `db_match` is None → confidence stays low → no brain.db fix path. Affects mostly ambiguous projects (low-confidence fingerprint).

**EFFORT:** 0.5h

**FIX:** When fingerprint confidence < 0.50, pass `category=None` to `hybrid_lookup` to search all categories. Or: derive category from the top chain_walker/probe finding rather than fingerprint, since chain_walker is more reliable than fingerprint for category identification.

---

## Summary ranking (severity × 1/effort)

| # | Gap | Severity | Effort | Ratio |
|---|-----|----------|--------|-------|
| 1 | Rescan false alarm — unfixed findings block pass | critical | 0.5h | 4.0 |
| 2 | Model claude-sonnet-4-5 → 4-6 | important | 0.1h | 10.0 |
| 3 | brain_fts excludes unverified patterns (RLS invisible) | important | 0.5h | 2.0 |
| 4 | SemanticIndex: no timeout on corrupt usearch | important | 0.5h | 2.0 |
| 5 | ts_files argv growth → E2BIG at 500+ files | minor | 1.0h | 0.5 |
| 6 | scan_missing_revalidate double file read | minor | 0.25h | 0.25 |
| 7 | db_lookup category wrong on low-confidence fingerprint | minor | 0.5h | 0.2 |

**Fix now:** GAP 2 (5 min, every ticket affected), GAP 1 (30 min, high confusion rate), GAP 3 (30 min, RLS tickets miss brain.db), GAP 4 (30 min, catastrophic when triggered).

**Fix later:** GAP 5, 6, 7 — correctness risks only at scale or edge cases.
