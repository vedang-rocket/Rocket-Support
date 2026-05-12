# Finding 22 — `print_cw_finding()` output investigation

**Date:** 2026-05-11  
**Scope:** `engine/format_output.py`, `engine/diagnose_output.py`, callers, Rich `Console` routing.

---

## Step 1 — `print_cw_finding()` full source

Location: `engine/format_output.py` lines 214–253.

```python
def print_cw_finding(cw: dict, conf: str) -> None:
    """Print a chain_walker finding."""
    conf_color = _CONF_COLOR.get(conf, "white")
    conf_icon  = _CONF_ICON.get(conf, "•")
    chain      = cw.get("chain", "?")
    broken_at  = cw.get("broken_at", "")
    issue      = cw.get("issue", "")
    missing    = cw.get("missing", "")
    fix_hint   = cw.get("fix_hint", "")
    cat_color  = _CAT_COLOR.get(chain, "cyan")

    # Header panel
    console.print(format_header(issue or broken_at))

    # Metadata
    conf_panel = Panel.fit(
        Text(f"{conf_icon} {conf}", style=f"bold {conf_color}"),
        title="Confidence", border_style=conf_color, box=box.ROUNDED,
    )
    chain_panel = Panel.fit(
        Text(f"{_CAT_ICON.get(chain, '•')} {chain}", style=f"bold {cat_color}"),
        title="Chain", border_style=cat_color, box=box.ROUNDED,
    )
    file_panel = Panel.fit(
        Text(broken_at or "—", style="dim"),
        title="File", border_style="dim", box=box.ROUNDED,
    )
    console.print(Columns([conf_panel, chain_panel, file_panel], equal=False, padding=(0, 1)))

    # Fix hint as code block
    if fix_hint:
        tbl = Table(box=box.MINIMAL, show_header=False, padding=(0, 1), expand=False)
        tbl.add_column("", style="dim")
        tbl.add_column("", style="white")
        tbl.add_row("Missing:", Text(missing, style="bold bright_red"))
        tbl.add_row("Fix:", Text(fix_hint, style="bright_green"))
        console.print(tbl)

    console.print(format_ready_to_apply(conf == "HIGH"))
    console.print("")
```

### Module-level `Console` used by `print_cw_finding`

Line 20 in `engine/format_output.py`:

```python
console = Console(highlight=False)
```

That is **default Rich behavior**: no `file=` argument → writes to **sys.stdout** (not stderr, not `/dev/tty`).

### Call sites for `print_cw_finding`

| Location | Notes |
|----------|--------|
| `engine/rkt_engine.py` ~541 | `fmt_out.print_cw_finding(cw_safe, conf)` inside `_print_all_findings()` |
| `docs/dead_code_audit.md` | Documentation only |

No calls from `bin/rkt-diagnose` directly; diagnosis UI path is `diagnose_output.py` (different helpers).

### `grep` (requested pattern)

Relevant hits in `engine/` and `bin/`:

- `engine/format_output.py`: `console = Console(highlight=False)`; `print_cw_finding`; `/dev/tty` in `print_triage_report`, `print_ready_panel`, `prompt_fix_mode`.
- `engine/diagnose_output.py`: `Console(file=_REAL_STDOUT, highlight=False)`.
- `engine/run_triage.py`: comment + `print_triage_report` (not `print_cw_finding`).

---

## Step 2 — All `Console(...)` in `engine/*.py` (script output)

```
engine/diagnose_output.py:
  Console(file=_REAL_STDOUT, highlight=False)
engine/format_output.py:
  Console(highlight=False)
  Console(file=tty, force_terminal=True, highlight=False)   # print_triage_report
  Console(file=tty, force_terminal=True, highlight=False)   # print_ready_panel
  Console(file=tty_out, force_terminal=True, highlight=False)  # prompt_fix_mode
  Console(force_terminal=True, highlight=False)             # print_fingerprint
```

---

## Step 3 — Visibility test for `print_cw_finding`

Command wrapped output between `--- output starts ---` / `--- output ends ---`.

**Result:** Rich panels and tables **did appear** between the markers → **not** silently routed to `/dev/tty`.

**Note:** The minimal fake finding used `file` instead of real chain_walker shape `broken_at`, so the “File” column showed `—`; real callers in `rkt_engine.py` pass `cw_safe` with `broken_at` from `chain_walker`.

---

## Step 4 — `diagnose_output.py` and `print_*` functions

`inspect.getmembers(..., isfunction)` with `name.startswith('print_')` returned **`[]`**.

This module uses **`_print_*`** helpers and a module-level:

```python
_REAL_STDOUT = sys.stdout
console = Console(file=_REAL_STDOUT, highlight=False)
```

That explicitly targets **captured original stdout** (not `/dev/tty`). Same class of behavior as stdout for normal runs.

---

## Step 5 — Conclusions

| Question | Answer |
|----------|--------|
| Is `print_cw_finding()` output broken? | **No.** Evidence: Step 3 produced full Rich output on stdout between markers. |
| Which `Console` does it use? | The global `console = Console(highlight=False)` in `format_output.py` → **stdout**. |
| How many other `print_*` in `format_output` share the same issue? | **None** for `/dev/tty`. All finding printers that use `console.print` (`print_cw_finding`, `print_semgrep_finding`, `print_schema_finding`, `print_fs_finding`, `print_db_match`, `print_kb_hits`, `print_summary`, `print_section_header`, `print_progress`, `format_complete_finding`) use the same module `console` → stdout. |
| Does diagnosis output silently go to `/dev/tty`? | **`print_cw_finding` / `_print_all_findings` path: no.** Other functions **intentionally** use `/dev/tty`: `print_triage_report`, `print_ready_panel`, `prompt_fix_mode` (documented: bypass bash `$()` capture). `run_triage.py` calls `print_triage_report` only. |
| `diagnose_output.py` same problem? | **No** `print_*` functions; uses `Console(file=_REAL_STDOUT)` — stdout-oriented, not tty. |

---

## Code change

**None applied.** Output was confirmed working; changing `Console(file=tty)` in triage/ready-panel flows would break the documented bash-capture bypass behavior.

---

## Follow-up (optional)

If engineers expected `fake_finding['file']` to populate the File panel: real API uses **`broken_at`** (see `chain_walker` dict keys). That is a **test data shape** mismatch, not a Rich routing bug.
