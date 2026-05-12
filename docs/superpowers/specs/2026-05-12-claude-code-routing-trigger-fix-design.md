# Design: Claude Code CLI Routing Label + SQL Trigger Wrong File

**Date:** 2026-05-12  
**Status:** Approved

---

## Problem

Two bugs surfaced from a live trace showing `"1 change · Claude API · 879 tokens"` and a trigger injected into the wrong migration file.

### BUG 1 — PATH B label is hardcoded to "Claude API"

`diagnose_output.py` has three display sites that produce path labels. All three use an `if/else` that only recognises `"brain_db_diff"` — anything else falls into the `else` branch and is labelled `"Claude API"`:

```python
# line 948–951 (and two similar sites at 879, 648)
if agent_result.path_used == "brain_db_diff":
    path_label = "brain.db"
else:
    path_label = f"Claude API · {agent_result.tokens_used:,} tokens"
```

`path_used == "claude_code_cli"` is silently swallowed into the `else`. The routing in `claude_agent.py` (PATH B before PATH C) is already correct — the label is lying, making it impossible to tell from the trace whether PATH B or PATH C actually ran.

### BUG 2 — Trigger SQL written to wrong file, wrong syntax

When PATH C (raw Claude API) handles a `missing on_auth_user_created trigger` finding:

1. It has no rule against modifying existing migrations → appends SQL to the nearest `.sql` file it finds (e.g. a storage-bucket migration).
2. It uses `EXECUTE PROCEDURE` (deprecated in PostgreSQL 11+) instead of `EXECUTE FUNCTION`.
3. The apply loop at `_claude_api_fix` line 535 silently skips any file that does not already exist — new migration files can never be created.

PATH B (Claude Code CLI) also has no trigger rule in its prompt, so even if it ran it could make the same mistake.

---

## Design

### 1 — Fix path label display (diagnose_output.py)

Three label sites all need the same new `elif` branch:

```python
if agent_result.path_used == "brain_db_diff":
    path_label = "brain.db"
elif agent_result.path_used == "claude_code_cli":
    path_label = f"Claude Code CLI · {agent_result.tokens_used:,} tokens"
else:
    path_label = f"Claude API · {agent_result.tokens_used:,} tokens"
```

Sites to update:
- Line ~648 (shadow `_print_shadow_block` helper)
- Line ~879 (shadow branch of `node_validate_fix`)
- Line ~948 (live AUTO branch of `node_validate_fix`)

### 2 — Add trigger rule to Claude Code CLI prompt (claude_code_agent.py)

In `_build_fix_prompt()`, detect trigger findings and append a hard rule block:

```python
_is_trigger = (
    "trigger" in issue.lower()
    or (db_match and db_match.get("category", "") in ("SUPABASE", "RLS"))
    or "on_auth_user_created" in issue.lower()
)
```

When true, append to the prompt:

```
IMPORTANT — SQL TRIGGER RULE:
If the fix requires creating a trigger:
1. Create a NEW migration file: supabase/migrations/<YYYYMMDDHHMMSS>_add_user_trigger.sql
   where <timestamp> = current datetime as YYYYMMDDHHMMSS
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
FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();
```

Detection covers both `"trigger"` in issue text and the category being `SUPABASE` with trigger-related keywords.

### 3 — Add Rule 9 to raw API prompt (claude_agent.py)

Append to the `RULES` section in `_claude_api_fix`:

```
9. For missing on_auth_user_created trigger:
   Create a NEW file: supabase/migrations/<YYYYMMDDHHMMSS>_add_user_trigger.sql
   Never modify existing migration files.
   Set "old" to "" (empty string) for new file creation.
   Use EXECUTE FUNCTION not EXECUTE PROCEDURE.
```

### 4 — Fix apply loop for new file creation (claude_agent.py)

Current code skips any file that does not exist:

```python
if not os.path.isfile(abs_path):
    continue   # ← BUG: new files silently dropped
```

Replace with:

```python
if not os.path.isfile(abs_path):
    if (change.get("old") or "").strip() == "":
        # new file creation — "old" is empty by convention
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        self._write_atomic(abs_path, (change.get("new") or "") + "\n")
        changes_applied.append({
            "file": change_rel,
            "line": 1,
            "old": "",
            "new": (change.get("new") or "")[:80],
        })
    continue
```

The `_write_atomic` helper already exists and handles the temp-file swap correctly.

---

## Files Changed

| File | Change |
|------|--------|
| `engine/diagnose_output.py` | 3 label sites: add `elif claude_code_cli` branch |
| `engine/claude_code_agent.py` | `_build_fix_prompt()`: inject trigger SQL rule when relevant |
| `engine/claude_agent.py` | Rule 9 in raw API prompt; new-file creation in apply loop |

---

## Verification

```bash
# 1. All 30 tests pass
engine/.venv/bin/python -m pytest tests/ -v 2>&1 | tail -5

# 2. PATH B label check — shadow run shows "Claude Code CLI" not "Claude API"
#    (requires live rkt-trace or rkt-diagnose on a SUPABASE finding)

# 3. Trigger rule check — shadow run for trigger finding
engine/.venv/bin/python -c "
import sys; sys.path.insert(0,'engine')
from claude_code_agent import run_claude_code_fix
# shadow=True — no file changes, just prompt/result check
"
```

---

## Out of Scope

- Changing the routing order in `claude_agent.fix()` — it is already correct (PATH B before PATH C).
- Any change to `diagnose_output.py` routing logic — only label strings change.
- Changes to `agent_loop.py` — not involved.
