# Claude Code CLI Routing Label + SQL Trigger Wrong File — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the "Claude API" label that hides which fix path ran, and prevent trigger SQL from being injected into the wrong migration file.

**Architecture:** Three surgical edits across three engine files. No new modules, no new tests. The routing in `claude_agent.py` is already correct — only display labels and prompt rules change.

**Tech Stack:** Python 3, existing engine venv at `engine/.venv/`

---

## File Map

| File | Lines touched | Why |
|------|--------------|-----|
| `engine/diagnose_output.py` | 596–600, 648–649, 879–880, 948–951 | 4 label sites hardcode "Claude API" |
| `engine/claude_code_agent.py` | `_build_fix_prompt()` | Add trigger SQL rule to CLI prompt |
| `engine/claude_agent.py` | prompt RULES section + apply loop | Add Rule 10 + new-file creation |

---

## Task 1 — Fix path labels in diagnose_output.py

**Files:**
- Modify: `engine/diagnose_output.py:596-600, 648-649, 879-880, 948-951`

There are four independent label sites. All need a `claude_code_cli` branch added.

- [ ] **Step 1.1 — Fix Site 1 (line 596–600) — post-fix success banner**

Current:
```python
path_label = ""
if agent_result.path_used == "brain_db_diff":
    path_label = "  ·  brain.db diff"
elif agent_result.tokens_used:
    path_label = f"  ·  {agent_result.tokens_used:,} tokens"
```

Replace with:
```python
path_label = ""
if agent_result.path_used == "brain_db_diff":
    path_label = "  ·  brain.db diff"
elif agent_result.path_used == "claude_code_cli":
    path_label = f"  ·  Claude Code CLI · {agent_result.tokens_used:,} tokens"
elif agent_result.tokens_used:
    path_label = f"  ·  {agent_result.tokens_used:,} tokens"
```

- [ ] **Step 1.2 — Fix Site 2 (line 648–649) — shadow block footer**

Current:
```python
path_label = "brain.db" if agent_result.path_used == "brain_db_diff" else \
             f"Claude API · {agent_result.tokens_used:,} tokens"
```

Replace with:
```python
if agent_result.path_used == "brain_db_diff":
    path_label = "brain.db"
elif agent_result.path_used == "claude_code_cli":
    path_label = f"Claude Code CLI · {agent_result.tokens_used:,} tokens"
else:
    path_label = f"Claude API · {agent_result.tokens_used:,} tokens"
```

- [ ] **Step 1.3 — Fix Site 3 (line 879–880) — shadow branch of node_validate_fix**

Current:
```python
path_label = "brain.db" if agent_result.path_used == "brain_db_diff" \
             else f"Claude API · {agent_result.tokens_used:,} tokens"
```

Replace with:
```python
if agent_result.path_used == "brain_db_diff":
    path_label = "brain.db"
elif agent_result.path_used == "claude_code_cli":
    path_label = f"Claude Code CLI · {agent_result.tokens_used:,} tokens"
else:
    path_label = f"Claude API · {agent_result.tokens_used:,} tokens"
```

- [ ] **Step 1.4 — Fix Site 4 (line 948–951) — live AUTO branch of node_validate_fix**

Current:
```python
if agent_result.path_used == "brain_db_diff":
    path_label = "brain.db"
else:
    path_label = f"Claude API · {agent_result.tokens_used:,} tokens"
```

Replace with:
```python
if agent_result.path_used == "brain_db_diff":
    path_label = "brain.db"
elif agent_result.path_used == "claude_code_cli":
    path_label = f"Claude Code CLI · {agent_result.tokens_used:,} tokens"
else:
    path_label = f"Claude API · {agent_result.tokens_used:,} tokens"
```

- [ ] **Step 1.5 — Run tests**

```bash
engine/.venv/bin/python -m pytest tests/ -v 2>&1 | tail -5
```

Expected: `30 passed`

- [ ] **Step 1.6 — Commit**

```bash
git add engine/diagnose_output.py
git commit -m "fix: show Claude Code CLI label in fix path display"
```

---

## Task 2 — Add trigger SQL rule to Claude Code CLI prompt

**Files:**
- Modify: `engine/claude_code_agent.py` — `_build_fix_prompt()` function

- [ ] **Step 2.1 — Add trigger detection + rule injection**

In `_build_fix_prompt()`, the function currently ends with `return f"""..."""`. Before the `return`, add:

```python
    # Inject trigger rule when the finding relates to auth triggers
    _issue_lower = issue.lower()
    _db_category = (db_match or {}).get("category", "") if db_match else ""
    _is_trigger_finding = (
        "trigger" in _issue_lower
        or "on_auth_user_created" in _issue_lower
        or _db_category in ("SUPABASE", "RLS")
    )

    trigger_rule = ""
    if _is_trigger_finding:
        from datetime import datetime as _dt
        _ts = _dt.now().strftime("%Y%m%d%H%M%S")
        trigger_rule = f"""

IMPORTANT — SQL TRIGGER RULE:
If the fix requires creating a trigger:
1. Create a NEW migration file: supabase/migrations/{_ts}_add_user_trigger.sql
   (use exactly this timestamp: {_ts})
2. NEVER modify existing migration files
3. Use EXECUTE FUNCTION not EXECUTE PROCEDURE (PostgreSQL 11+)
4. The new file must contain both the function AND the trigger:

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger AS $$
BEGIN
  INSERT INTO public.profiles (id, email)
  VALUES (new.id, new.email);
  RETURN new;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE OR REPLACE TRIGGER on_auth_user_created
AFTER INSERT ON auth.users
FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();"""
```

Then change the final `return` statement to append `trigger_rule`:

Current:
```python
    return f"""Fix this bug in {rel_file}.
...
Read AGENTS.md in the project root for all hard rules. This is a Rocket.new project."""
```

Change to:
```python
    return f"""Fix this bug in {rel_file}.
...
Read AGENTS.md in the project root for all hard rules. This is a Rocket.new project.""" + trigger_rule
```

The full function after the change (showing the two additions in context):

```python
def _build_fix_prompt(
    findings: list,
    repo_path: str,
    db_match: Optional[dict],
    hint: str,
) -> str:
    primary = findings[0] if findings else {}

    broken_file = (
        primary.get("broken_at")
        or primary.get("file_path", "")
        or ""
    )
    if broken_file and not os.path.isabs(broken_file):
        broken_file = os.path.join(repo_path, broken_file)

    rel_file = os.path.relpath(broken_file, repo_path) if broken_file else "unknown"
    issue = primary.get("issue") or primary.get("message") or "unknown issue"
    line = primary.get("line_number") or 1

    db_context = ""
    if db_match and db_match.get("pattern"):
        db_context = f"\nKnown pattern: {db_match['pattern']}"
        if db_match.get("fix_diff"):
            db_context += f"\nSimilar fix applied before:\n{db_match['fix_diff'][:200]}"

    # Inject trigger rule when the finding relates to auth triggers
    _issue_lower = issue.lower()
    _db_category = (db_match or {}).get("category", "") if db_match else ""
    _is_trigger_finding = (
        "trigger" in _issue_lower
        or "on_auth_user_created" in _issue_lower
        or _db_category in ("SUPABASE", "RLS")
    )

    trigger_rule = ""
    if _is_trigger_finding:
        from datetime import datetime as _dt
        _ts = _dt.now().strftime("%Y%m%d%H%M%S")
        trigger_rule = f"""

IMPORTANT — SQL TRIGGER RULE:
If the fix requires creating a trigger:
1. Create a NEW migration file: supabase/migrations/{_ts}_add_user_trigger.sql
   (use exactly this timestamp: {_ts})
2. NEVER modify existing migration files
3. Use EXECUTE FUNCTION not EXECUTE PROCEDURE (PostgreSQL 11+)
4. The new file must contain both the function AND the trigger:

CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger AS $$
BEGIN
  INSERT INTO public.profiles (id, email)
  VALUES (new.id, new.email);
  RETURN new;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE OR REPLACE TRIGGER on_auth_user_created
AFTER INSERT ON auth.users
FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();"""

    return f"""Fix this bug in {rel_file}.

TICKET: {hint or "(no hint)"}
ISSUE: {issue}
FILE: {rel_file}
LINE: {line}{db_context}

INSTRUCTIONS:
1. Read {rel_file} fully before making any change
2. Make the minimum change needed — do not refactor
3. Do not change any other files unless strictly required
4. After fixing, run: npx tsc --noEmit
5. If tsc fails, fix the TypeScript errors

Read AGENTS.md in the project root for all hard rules. This is a Rocket.new project.""" + trigger_rule
```

- [ ] **Step 2.2 — Run tests**

```bash
engine/.venv/bin/python -m pytest tests/ -v 2>&1 | tail -5
```

Expected: `30 passed`

- [ ] **Step 2.3 — Commit**

```bash
git add engine/claude_code_agent.py
git commit -m "fix: inject SQL trigger rule into Claude Code CLI prompt for SUPABASE/trigger findings"
```

---

## Task 3 — Add Rule 10 to raw API prompt + fix new-file creation in apply loop

**Files:**
- Modify: `engine/claude_agent.py` — `_claude_api_fix()` method

### Part A — Rule 10 in the prompt

- [ ] **Step 3.1 — Append Rule 10 to RULES section**

Current (lines 431–440, ending at rule 9):
```python
RULES — READ CAREFULLY:
1. Return ONLY valid JSON. No markdown. No backticks. No explanation.
2. The "old" field must be the EXACT content of the broken line (copy it exactly from context above).
3. The "new" field must be the replacement for that ONE line only.
4. If fix requires adding an import: add it as a SEPARATE change with the import line.
5. Maximum 3 changes total. If you need more than 3 changes → return empty changes array.
6. Do NOT reformat, rename, or restructure anything.
7. Do NOT add comments.
8. Do NOT change indentation of surrounding lines.
9. The >>> prefix in the context above is a visual marker only. Do NOT include >>> in the "old" field. Copy the exact line content without any prefix.
```

Replace the entire RULES block (lines 431–440) with:
```python
RULES — READ CAREFULLY:
1. Return ONLY valid JSON. No markdown. No backticks. No explanation.
2. The "old" field must be the EXACT content of the broken line (copy it exactly from context above).
3. The "new" field must be the replacement for that ONE line only.
4. If fix requires adding an import: add it as a SEPARATE change with the import line.
5. Maximum 3 changes total. If you need more than 3 changes → return empty changes array.
6. Do NOT reformat, rename, or restructure anything.
7. Do NOT add comments.
8. Do NOT change indentation of surrounding lines.
9. The >>> prefix in the context above is a visual marker only. Do NOT include >>> in the "old" field. Copy the exact line content without any prefix.
10. For a missing on_auth_user_created trigger: create a NEW file supabase/migrations/<YYYYMMDDHHMMSS>_add_user_trigger.sql — never modify existing migration files. Set "old" to "" (empty string) and "new" to the full file content. Use EXECUTE FUNCTION not EXECUTE PROCEDURE.
```

The rule is appended inside the existing f-string, right after rule 9's line. The edit target is the exact string `9. The >>> prefix in the context above is a visual marker only. Do NOT include >>> in the "old" field. Copy the exact line content without any prefix.` and the replacement adds Rule 10 after it.

### Part B — New-file creation in apply loop

- [ ] **Step 3.2 — Fix apply loop to create new files when old is empty**

Current (lines 534–538):
```python
            abs_path = os.path.join(repo_path, change_rel)
            if not os.path.isfile(abs_path):
                continue
            if not self._verify_change_safe(abs_path, change):
                continue
```

Replace with:
```python
            abs_path = os.path.join(repo_path, change_rel)
            if not os.path.isfile(abs_path):
                if (change.get("old") or "").strip() == "":
                    os.makedirs(os.path.dirname(abs_path), exist_ok=True)
                    self._write_atomic(abs_path, (change.get("new") or "") + "\n")
                    changes_applied.append({
                        "file": change_rel,
                        "line": 1,
                        "old": "",
                        "new": (change.get("new") or "")[:80],
                    })
                continue
            if not self._verify_change_safe(abs_path, change):
                continue
```

The `os.makedirs` call handles nested paths like `supabase/migrations/` that may not exist yet. The `continue` after the `if` block means non-new-file missing paths are still skipped as before.

- [ ] **Step 3.3 — Run tests**

```bash
engine/.venv/bin/python -m pytest tests/ -v 2>&1 | tail -5
```

Expected: `30 passed`

- [ ] **Step 3.4 — Commit**

```bash
git add engine/claude_agent.py
git commit -m "fix: Rule 10 SQL trigger in raw API prompt + new-file creation in apply loop"
```

---

## Task 4 — Final verification

- [ ] **Step 4.1 — Full test run**

```bash
engine/.venv/bin/python -m pytest tests/ -v 2>&1 | tail -10
```

Expected: `30 passed`

- [ ] **Step 4.2 — Import smoke test**

```bash
engine/.venv/bin/python -c "
import sys; sys.path.insert(0, 'engine')
from claude_code_agent import _build_fix_prompt

# Trigger finding — should contain TRIGGER RULE block
p = _build_fix_prompt(
    findings=[{'issue': 'Missing on_auth_user_created trigger', 'broken_at': 'supabase/migrations', 'line_number': 1}],
    repo_path='/tmp',
    db_match={'category': 'SUPABASE', 'pattern': 'missing trigger'},
    hint='user cannot login',
)
assert 'EXECUTE FUNCTION' in p, 'trigger rule missing'
assert 'EXECUTE PROCEDURE' not in p, 'wrong SQL syntax present'
assert 'NEVER modify existing migration files' in p, 'migration rule missing'
print('trigger rule: OK')

# Non-trigger finding — should NOT contain trigger block
p2 = _build_fix_prompt(
    findings=[{'issue': 'middleware missing updateSession', 'broken_at': 'middleware.ts', 'line_number': 5}],
    repo_path='/tmp',
    db_match=None,
    hint='redirect loop',
)
assert 'TRIGGER RULE' not in p2, 'trigger rule injected for wrong finding'
print('no trigger rule for middleware: OK')
"
```

Expected output:
```
trigger rule: OK
no trigger rule for middleware: OK
```

- [ ] **Step 4.3 — Verify label string is present in diagnose_output.py**

```bash
grep "Claude Code CLI" engine/diagnose_output.py
```

Expected: 3 matches (one per site).

- [ ] **Step 4.4 — Final commit if anything was missed**

If the three task commits all landed cleanly, nothing to do here. Otherwise:

```bash
git add engine/diagnose_output.py engine/claude_code_agent.py engine/claude_agent.py
git commit -m "fix: Claude Code CLI routing label + SQL trigger wrong file

- diagnose_output.py: 4 label sites now show 'Claude Code CLI' when path_used=claude_code_cli
- claude_code_agent.py: trigger SQL rule injected for SUPABASE/trigger findings
- claude_agent.py: Rule 10 added to raw API prompt; apply loop creates new files when old=''"
```
