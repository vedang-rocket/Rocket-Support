"""
format_output.py — Rich terminal UI for rkt diagnosis output.
All functions return Rich renderables or print via console.
"""

import os
import shutil as _shutil
import subprocess as _subprocess
from typing import Optional
from rich.console import Console, Group
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich.columns import Columns
from rich.text import Text
from rich.padding import Padding
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn
from rich import box

console = Console(highlight=False)

_DELTA_BIN = _shutil.which("delta") or "/usr/local/bin/delta"
_DELTA_AVAILABLE = bool(_shutil.which("delta"))

# ── Color / style maps ────────────────────────────────────────────────────────

_CONF_COLOR = {"HIGH": "bright_green", "MED": "bright_yellow", "LOW": "bright_red"}
_CONF_ICON  = {"HIGH": "✓", "MED": "⚠", "LOW": "✗"}

_CAT_COLOR = {
    "AUTH":     "cyan",
    "STRIPE":   "magenta",
    "SUPABASE": "blue",
    "BUILD":    "yellow",
    "ENV":      "orange1",
    "SCHEMA":   "dark_orange",
    "OTHER":    "white",
}
_CAT_ICON = {
    "AUTH":     "🔐",
    "STRIPE":   "💳",
    "SUPABASE": "🗄",
    "BUILD":    "🔨",
    "ENV":      "⚙",
    "SCHEMA":   "📋",
    "OTHER":    "•",
}


# ── delta helper ─────────────────────────────────────────────────────────────

def _render_with_delta(diff: str) -> Optional[str]:
    """Pipe diff through delta; return ANSI output or None if unavailable."""
    if not _DELTA_AVAILABLE or not diff.strip():
        return None
    try:
        r = _subprocess.run(
            [_DELTA_BIN, "--no-gitconfig", "--color-only"],
            input=diff, capture_output=True, text=True, timeout=5,
        )
        return r.stdout if r.returncode == 0 and r.stdout.strip() else None
    except Exception:
        return None


# ── 1. format_header ──────────────────────────────────────────────────────────

def format_header(title: str, subtitle: str = "") -> Panel:
    """ROOT CAUSE panel — HEAVY box, cyan border."""
    body = Text(title, style="bold white")
    if subtitle:
        body.append(f"\n{subtitle}", style="dim")
    return Panel(body, box=box.HEAVY, border_style="cyan", padding=(0, 2))


# ── 2. format_metadata ────────────────────────────────────────────────────────

def format_metadata(confidence: str, category: str, file_count: int) -> Columns:
    """Three side-by-side badges: confidence · category · file count."""
    conf_color = _CONF_COLOR.get(confidence, "white")
    conf_icon  = _CONF_ICON.get(confidence, "•")
    cat_color  = _CAT_COLOR.get(category, "white")
    cat_icon   = _CAT_ICON.get(category, "•")

    conf_panel = Panel.fit(
        Text(f"{conf_icon} {confidence}", style=f"bold {conf_color}"),
        title="Confidence", border_style=conf_color, box=box.ROUNDED,
    )
    cat_panel = Panel.fit(
        Text(f"{cat_icon} {category}", style=f"bold {cat_color}"),
        title="Category", border_style=cat_color, box=box.ROUNDED,
    )
    count_panel = Panel.fit(
        Text(str(file_count), style="bold white"),
        title="Files", border_style="dim", box=box.ROUNDED,
    )
    return Columns([conf_panel, cat_panel, count_panel], equal=False, padding=(0, 1))


# ── 3. format_files_table ─────────────────────────────────────────────────────

def format_files_table(files: list) -> Table:
    """Minimal table listing (file_path, line) pairs."""
    tbl = Table(box=box.MINIMAL, show_header=True, header_style="bold dim",
                padding=(0, 1), expand=False)
    tbl.add_column("File", style="cyan", no_wrap=False)
    tbl.add_column("Line", style="dim", justify="right", width=6)
    for entry in files:
        path = entry.get("file_path", entry.get("path", ""))
        line = str(entry.get("line_number", entry.get("line", "—")))
        tbl.add_row(path, line)
    return tbl


# ── 4. format_code_fix ────────────────────────────────────────────────────────

def format_code_fix(diff: str, title: str = "CODE FIX") -> Panel:
    """Syntax-highlighted diff wrapped in a ROUNDED panel (delta if available)."""
    delta_out = _render_with_delta(diff.strip())
    if delta_out:
        content = Text.from_ansi(delta_out.strip())
    else:
        content = Syntax(diff.strip(), "diff", theme="monokai", word_wrap=True)
    return Panel(
        Padding(content, (1, 2)),
        title=f"[bold]{title}[/bold]",
        box=box.ROUNDED,
        border_style="dim",
        padding=(0, 0),
    )


# ── 5. format_verify_command ──────────────────────────────────────────────────

def format_verify_command(cmd: str) -> Text:
    """Styled verification command line."""
    t = Text()
    t.append("  Verify: ", style="dim")
    t.append(cmd, style="dim italic cyan")
    return t


# ── 6. format_ready_to_apply ─────────────────────────────────────────────────

def format_ready_to_apply(auto_apply: bool) -> Panel:
    """Final status panel — green HEAVY border if auto_apply."""
    if auto_apply:
        label = Text("✓ Ready to auto-apply", style="bold bright_green")
        border = "bright_green"
    else:
        label = Text("⚠ Manual review required", style="bold bright_yellow")
        border = "bright_yellow"
    return Panel.fit(label, box=box.HEAVY, border_style=border, padding=(0, 2))


# ── 7. format_complete_finding ────────────────────────────────────────────────

def format_complete_finding(finding: dict) -> None:
    """Print one complete formatted finding using all Rich components."""
    rule_id    = finding.get("rule_id", "unknown")
    file_path  = finding.get("file_path", "")
    line_num   = finding.get("line_number", 0)
    message    = finding.get("message", "")
    confidence = finding.get("confidence", "MED").upper()
    category   = finding.get("category", "OTHER").upper()
    fix_diff   = finding.get("_fix_diff", "")
    auto_apply = finding.get("_auto_apply", False)

    # Header
    console.print(format_header(message, rule_id))

    # Metadata badges
    console.print(format_metadata(confidence, category, 1 if file_path else 0))

    # Files table
    if file_path:
        console.print(format_files_table([{"file_path": file_path, "line_number": line_num}]))

    # Code diff
    if fix_diff and fix_diff.strip():
        console.print(format_code_fix(fix_diff))

    # Verify
    console.print(format_verify_command("npx tsc --noEmit"))

    # Ready status
    console.print(format_ready_to_apply(auto_apply))
    console.print("")


# ── 8. print_progress ────────────────────────────────────────────────────────

def print_progress(layer: str, current: int, total: int) -> None:
    """Print a one-line progress indicator for engine layers."""
    bar_filled = int((current / max(total, 1)) * 20)
    bar = "█" * bar_filled + "░" * (20 - bar_filled)
    t = Text()
    t.append(f"  [{current}/{total}] ", style="dim")
    t.append(bar, style="cyan")
    t.append(f"  {layer}", style="bold")
    console.print(t)


# ── Specialized section printers (used by _print_all_findings) ────────────────

def print_section_header(title: str, count: int = 0, color: str = "cyan") -> None:
    count_str = f" ({count})" if count else ""
    t = Text()
    t.append(f" {title}{count_str} ", style=f"bold {color} on grey15")
    console.print(t)
    console.print("")


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


def print_semgrep_finding(f: dict, conf: str, context_block: str = "") -> None:
    """Print a semgrep finding."""
    rule  = f.get("check_id", "").split(".")[-1]
    path  = f.get("path", "")
    line  = f.get("start", {}).get("line", 0)
    msg   = f.get("extra", {}).get("message", "").split("\n")[0][:120]
    fix   = f.get("extra", {}).get("fix", "")

    from rkt_engine import _infer_category
    category = _infer_category(rule)

    console.print(format_header(msg, rule))
    console.print(format_metadata(conf, category, 1 if path else 0))

    if path:
        console.print(format_files_table([{"file_path": path, "line_number": line}]))

    if fix:
        console.print(format_code_fix(f"- {fix}\n+ (autofix)", "AUTOFIX"))
    elif context_block and context_block.strip():
        console.print(format_code_fix(context_block, "CONTEXT"))

    console.print(format_verify_command("npx tsc --noEmit"))
    console.print(format_ready_to_apply(bool(fix)))
    console.print("")


def print_schema_finding(sf: dict) -> None:
    """Print a schema check failure."""
    check    = sf.get("check", "")
    fix_hint = sf.get("fix_hint", "")

    console.print(format_header(check, "schema check"))
    console.print(format_metadata("MED", "SCHEMA", 0))
    if fix_hint:
        console.print(format_code_fix(fix_hint, "MIGRATION FIX"))
    console.print(format_ready_to_apply(False))
    console.print("")


def print_fs_finding(issue: dict, conf: str) -> None:
    """Print a file-system finding."""
    rule = issue.get("rule", "")
    msg  = issue.get("message", "")
    fix  = issue.get("fix", "")

    from rkt_engine import _infer_category
    category = _infer_category(rule)

    console.print(format_header(msg, rule))
    console.print(format_metadata(conf, category, 0))
    if fix:
        console.print(format_code_fix(fix, "FIX"))
    console.print(format_ready_to_apply(False))
    console.print("")


def print_db_match(db_match: dict) -> None:
    """Print a brain.db match."""
    score    = db_match.get("_score", 0)
    uses     = db_match.get("uses", 0)
    pattern  = db_match.get("pattern", "")[:100]
    sig      = db_match.get("error_signature", "")[:100]
    diff     = db_match.get("fix_diff", "")
    category = db_match.get("category", "OTHER").upper()

    t = Text()
    t.append(f" KNOWN FIX ", style="bold white on grey15")
    t.append(f"  {score:.0%} similarity · used {uses}×", style="dim")
    console.print(t)
    console.print("")

    console.print(format_header(pattern, sig))
    console.print(format_metadata("HIGH", category, 0))
    if diff and diff.strip():
        console.print(format_code_fix(diff[:500], "FIX DIFF"))
    console.print(format_ready_to_apply(True))
    console.print("")


def print_kb_hits(kb_hits: list) -> None:
    """Print knowledge-base search hits."""
    if not kb_hits:
        return
    t = Text()
    t.append(" RELEVANT DOCS ", style="bold white on grey15")
    console.print(t)
    console.print("")
    for hit in kb_hits:
        source = hit.get("source", "")
        score  = hit.get("score", 0)
        chunk  = hit.get("chunk", "")[:400]
        hdr = Text()
        hdr.append(f"[{source}]", style="bold cyan")
        hdr.append(f"  score={score:.3f}", style="dim")
        console.print(Panel(
            Text(chunk, style="dim"),
            title=hdr,
            box=box.ROUNDED,
            border_style="dim",
            padding=(0, 1),
        ))
    console.print("")


def print_summary(repo_name: str, total: int) -> None:
    """Final summary line."""
    if total == 0:
        msg = Text("✓ No issues detected", style="bold bright_green")
    else:
        msg = Text(f"  {total} issue{'s' if total != 1 else ''} found in ", style="bold")
        msg.append(repo_name, style="bold cyan")
        msg.append("  —  run ", style="dim")
        msg.append(f"rkt {repo_name}", style="bold cyan")
        msg.append(" to apply fixes", style="dim")
    console.print(Panel.fit(msg, box=box.HEAVY, border_style="cyan", padding=(0, 2)))


# ── Triage report printer (writes to /dev/tty to bypass bash $() capture) ────

def print_triage_report(state: dict) -> None:
    """
    Rich triage report — writes directly to /dev/tty so bash $() capture
    doesn't strip formatting. Falls back to console if /dev/tty unavailable.
    """
    import os
    try:
        tty = open("/dev/tty", "w")
        tty_console = Console(file=tty, force_terminal=True, highlight=False)
    except OSError:
        tty_console = console

    fp      = state.get("fingerprint") or {}
    scored  = state.get("findings_scored") or []
    supp    = state.get("suppressed_findings") or []
    db_m    = state.get("db_match")
    timings = state.get("timings") or {}
    total_ms = sum(timings.values())

    # ── Header ────────────────────────────────────────────────────────────────
    tty_console.print("")
    tty_console.print(Panel.fit(
        Text("RKT TRIAGE REPORT", style="bold white"),
        box=box.HEAVY, border_style="cyan", padding=(0, 4),
    ))

    # ── Project metadata ──────────────────────────────────────────────────────
    proj_type = fp.get("project_type", "Unknown")
    conf_pct  = fp.get("confidence", 0)
    has_sb    = fp.get("has_supabase", False)
    has_st    = fp.get("has_stripe", False)

    proj_panel = Panel.fit(
        Text(f"{proj_type}  ({conf_pct:.0%})", style="bold white"),
        title="Project", border_style="dim", box=box.ROUNDED,
    )
    nxt_panel = Panel.fit(
        Text(fp.get("next_version") or "unknown", style="bold white"),
        title="Next.js", border_style="dim", box=box.ROUNDED,
    )
    sb_color = "bright_green" if has_sb else "dim"
    st_color = "bright_green" if has_st else "dim"
    sb_text = Text()
    sb_text.append("Supabase ", style=sb_color)
    sb_text.append("Stripe", style=st_color)
    stack_panel = Panel.fit(sb_text, title="Stack", border_style="dim", box=box.ROUNDED)

    fix_mode = state.get("fix_mode", "MANUAL")
    fix_conf = state.get("overall_confidence", 0)
    auto_cnt = state.get("auto_fixable_count", 0)
    mode_color = {"AUTO": "bright_green", "GUIDED": "bright_yellow", "CLAUDE": "cyan", "MANUAL": "dim"}.get(fix_mode, "white")
    mode_panel = Panel.fit(
        Text(f"{fix_mode}  ({fix_conf:.0%})", style=f"bold {mode_color}"),
        title="Fix Mode", border_style=mode_color, box=box.ROUNDED,
    )
    auto_panel = Panel.fit(
        Text(str(auto_cnt), style="bold bright_green" if auto_cnt else "dim"),
        title="Auto-fixable", border_style="dim", box=box.ROUNDED,
    )

    tty_console.print(Columns([proj_panel, nxt_panel, stack_panel, mode_panel, auto_panel],
                               equal=False, padding=(0, 1)))
    tty_console.print("")

    # ── Issue description ─────────────────────────────────────────────────────
    issue_desc = state.get("issue_description", "")
    sym_cat    = state.get("symptom_category")
    if issue_desc or sym_cat:
        parts = Text()
        if issue_desc:
            parts.append(issue_desc, style="italic")
        if sym_cat:
            parts.append(f"  [{sym_cat}]", style="dim cyan")
        tty_console.print(Panel(parts, title="Issue", box=box.ROUNDED,
                                border_style="dim", padding=(0, 1)))
        tty_console.print("")

    # ── Findings table ────────────────────────────────────────────────────────
    if scored:
        tbl = Table(box=box.MINIMAL, show_header=True, header_style="bold dim",
                    padding=(0, 1), expand=True)
        tbl.add_column("Mode", width=14)
        tbl.add_column("Conf", width=6, justify="right")
        tbl.add_column("Source", width=14)
        tbl.add_column("Finding")

        _MODE_COLOR = {"AUTO": "bright_green", "GUIDED": "bright_yellow", "MANUAL": "dim"}
        for s in scored:
            src     = s.get("source", "")
            f       = s.get("finding", {})
            mode    = s.get("fix_mode", "MANUAL")
            conf    = s.get("confidence", 0)
            matched = s.get("symptom_match", False)

            if src == "chain_walker":
                msg = f.get("issue", "")
            elif src in ("semgrep", "probe"):
                rule = (f.get("check_id") or "").split(".")[-1]
                path = os.path.basename(f.get("path", ""))
                line = f.get("start", {}).get("line", "?")
                msg  = f"{rule} @ {path}:{line}"
            else:
                msg = f.get("message", "")

            star = "★ " if matched else "  "
            mc   = _MODE_COLOR.get(mode, "white")
            tbl.add_row(
                Text(f"{star}{mode}", style=f"bold {mc}"),
                Text(f"{conf:.0%}", style="dim"),
                Text(src, style="dim"),
                Text(msg[:100]),
            )
        tty_console.print(tbl)
        tty_console.print("")

    # ── DB match ──────────────────────────────────────────────────────────────
    if db_m:
        cat   = db_m.get("category", "OTHER").upper()
        score = db_m.get("_score", 0)
        pat   = db_m.get("pattern", "")[:100]
        cat_color = _CAT_COLOR.get(cat, "white")
        t = Text()
        t.append(f"{_CAT_ICON.get(cat, '•')} {cat}", style=f"bold {cat_color}")
        t.append(f"  score={score:.2f}", style="dim")
        t.append(f"\n{pat}", style="italic dim")
        tty_console.print(Panel(t, title="Known Fix", box=box.ROUNDED,
                                border_style=cat_color, padding=(0, 1)))
        tty_console.print("")

    # ── Suppressed ────────────────────────────────────────────────────────────
    if supp:
        tty_console.print(Text(f"  {len(supp)} finding(s) suppressed (low signal / duplicate)",
                               style="dim"))
        tty_console.print("")

    # ── Timings ───────────────────────────────────────────────────────────────
    timing_parts = Text("  ", style="dim")
    for k, v in timings.items():
        timing_parts.append(f"{k}=", style="dim")
        timing_parts.append(f"{v:.0f}ms  ", style="dim cyan")
    timing_parts.append(f"total={total_ms:.0f}ms", style="bold dim")
    tty_console.print(timing_parts)
    tty_console.print("")

    try:
        tty.close()
    except Exception:
        pass


# ── Ready panel (rkt-main final screen) ──────────────────────────────────────

def print_ready_panel(project: str, code_dir: str, vault_dir: str,
                      tools: list, next_steps: list = None,
                      engine_summary: str = "", semgrep_summary: str = "") -> None:
    """Hero 'X is ready' panel — tools checklist + next steps."""
    import os
    try:
        tty = open("/dev/tty", "w")
        c = Console(file=tty, force_terminal=True, highlight=False)
    except OSError:
        c = console

    # Tools table — 2 columns: icon + description
    tools_tbl = Table.grid(padding=(0, 2))
    tools_tbl.add_column(width=2)
    tools_tbl.add_column()
    for t in tools:
        tools_tbl.add_row(Text("✓", style="bright_green"), Text(t, style="white"))
    if engine_summary:
        tools_tbl.add_row(Text("✓", style="bright_green"),
                          Text(f"Engine: {engine_summary}", style="white"))
    if semgrep_summary:
        tools_tbl.add_row(Text("✓", style="bright_green"),
                          Text(f"Semgrep: {semgrep_summary}", style="white"))

    # Paths
    paths = Table.grid(padding=(0, 2))
    paths.add_column(width=6)
    paths.add_column()
    paths.add_row(Text("Code", style="bold dim"),  Text(code_dir, style="cyan"))
    paths.add_row(Text("Vault", style="bold dim"), Text(vault_dir, style="cyan"))

    # Title text inside panel
    title = Text(f"  {project} is ready  ", style="bold white on green")

    group = Group(
        Padding(title, (0, 0, 1, 0)),
        paths,
        Padding(Text("Tools installed", style="bold dim"), (1, 0, 0, 0)),
        tools_tbl,
    )

    if next_steps:
        steps_tbl = Table.grid(padding=(0, 2))
        steps_tbl.add_column(width=3)
        steps_tbl.add_column()
        for i, step in enumerate(next_steps, 1):
            steps_tbl.add_row(
                Text(f"{i}.", style="bold bright_green"),
                Text(step, style="white"),
            )
        group = Group(
            group,
            Padding(Text("Start working", style="bold dim"), (1, 0, 0, 0)),
            steps_tbl,
        )

    c.print("")
    c.print(Panel(group, box=box.HEAVY, border_style="green", padding=(1, 2)))
    c.print("")

    try:
        tty.close()
    except Exception:
        pass


# ── Fix mode chooser (rkt-crazy Phase 3) ─────────────────────────────────────

def prompt_fix_mode(recommended: str, confidence: str, auto_count: int) -> str:
    """
    Interactive Rich menu for fix-mode selection.
    Renders UI to /dev/tty, reads input from /dev/tty, writes ONLY chosen mode to stdout.
    """
    import os, sys

    modes = [
        ("AUTO",   "apply all high-confidence fixes automatically", "bright_green"),
        ("GUIDED", "open Cursor at workspace path",                 "bright_yellow"),
        ("CLAUDE", "launch Claude Code in workspace",               "cyan"),
        ("MANUAL", "show diffs, I decide per file",                 "dim"),
    ]
    name_to_idx = {m[0]: i for i, m in enumerate(modes)}
    default_idx = name_to_idx.get(recommended, 3)

    try:
        tty_in  = open("/dev/tty", "r")
        tty_out = open("/dev/tty", "w")
        c = Console(file=tty_out, force_terminal=True, highlight=False)
    except OSError:
        # No TTY — fall back to default
        print(recommended)
        return recommended

    # Header — section rule
    c.print("")
    c.rule(Text("  Phase 3 / Fix Mode  ", style="bold cyan"), style="cyan", align="left")
    c.print("")

    # Recommendation badge
    rec_color = modes[default_idx][2]
    rec = Text()
    rec.append("  Recommended  ", style="dim")
    rec.append(f" {recommended} ", style=f"bold white on {rec_color}")
    rec.append(f"   {confidence} confidence · {auto_count} auto-fixable", style="dim")
    c.print(rec)
    c.print("")

    # Menu table
    tbl = Table.grid(padding=(0, 2))
    tbl.add_column(width=4, justify="right")
    tbl.add_column(width=8)
    tbl.add_column()
    tbl.add_column(width=16, justify="right")

    for i, (name, desc, color) in enumerate(modes):
        is_def = (i == default_idx)
        num = Text(f"[{i+1}]", style=f"bold {color}" if is_def else "dim")
        mode = Text(name, style=f"bold {color}" if is_def else "white")
        descr = Text(desc, style="white" if is_def else "dim")
        tag = Text("← recommended", style=f"bold {color}") if is_def else Text("")
        tbl.add_row(num, mode, descr, tag)

    c.print(tbl)
    c.print("")
    c.print(Text(f"  Enter number [default {default_idx+1}]: ", style="bold"), end="")

    try:
        choice = tty_in.readline().strip()
    except KeyboardInterrupt:
        choice = ""

    idx = default_idx
    if choice.isdigit():
        v = int(choice)
        if 1 <= v <= len(modes):
            idx = v - 1

    chosen = modes[idx][0]
    chosen_color = modes[idx][2]

    c.print("")
    c.print(Text("  ✓ Selected  ", style="dim") + Text(f" {chosen} ",
            style=f"bold white on {chosen_color}"))
    c.print("")

    try:
        tty_in.close(); tty_out.close()
    except Exception:
        pass

    # Stdout: just the chosen mode name (bash captures this)
    sys.stdout.write(chosen + "\n")
    sys.stdout.flush()
    return chosen


# ── Fingerprint printer (replaces fingerprint.print_human) ───────────────────

def print_fingerprint(result: dict, repo_name: str = "") -> None:
    """Rich replacement for fingerprint.print_human — bars + env columns.
    Uses force_terminal so ANSI survives rkt-main's `| sed` indentation pipe.
    """
    name = repo_name or os.path.basename(result.get("repo_path", "")) or "project"
    c = Console(force_terminal=True, highlight=False)

    # Metadata grid
    meta = Table.grid(padding=(0, 2))
    meta.add_column(style="bold dim", width=16)
    meta.add_column()
    meta.add_row("Project",         Text(name, style="bold white"))
    meta.add_row("Type",            Text(f"{result['project_type']}  ({result['confidence']:.0%})",
                                          style="bold cyan"))
    meta.add_row("Framework",       Text(f"{result['framework']} {result.get('next_version', '')}",
                                          style="white"))
    meta.add_row("Supabase",        Text("yes" if result["has_supabase"] else "no",
                                          style="bright_green" if result["has_supabase"] else "dim"))
    meta.add_row("Stripe",          Text("yes" if result["has_stripe"] else "no",
                                          style="bright_green" if result["has_stripe"] else "dim"))
    meta.add_row("SQL files",       Text(str(result["sql_files_found"]), style="white"))
    meta.add_row("Most likely bug", Text(result["common_failure"], style="italic yellow"))
    meta.add_row("Category",        Text(result["category"],
                                          style=f"bold {_CAT_COLOR.get(result['category'], 'white')}"))
    if result.get("used_fallback"):
        meta.add_row("Signal health",
                     Text(f"low-signal ({result.get('fallback_reason', 'heuristic fallback')})",
                          style="dim yellow"))
    c.print("")
    c.print(meta)

    # Type scores — Rich-native bars
    c.print("")
    c.print(Text("  Type scores", style="bold dim"))
    scores_tbl = Table.grid(padding=(0, 1))
    scores_tbl.add_column(width=2)
    scores_tbl.add_column(width=12)
    scores_tbl.add_column(width=6, justify="right")
    scores_tbl.add_column()

    sorted_scores = sorted(result["all_scores"].items(), key=lambda x: -x[1])
    top_type = sorted_scores[0][0] if sorted_scores else None
    for t, s in sorted_scores:
        is_top = (t == top_type)
        bar_color = "bright_green" if is_top else "cyan" if s > 0.3 else "dim"
        filled = int(s * 30)
        bar = Text("█" * filled, style=bar_color)
        bar.append("░" * (30 - filled), style="grey23")
        scores_tbl.add_row(
            "",
            Text(t, style="bold white" if is_top else "dim"),
            Text(f"{s:.2f}", style=bar_color),
            bar,
        )
    c.print(scores_tbl)

    # Env vars as a compact grid
    env = result.get("env_vars") or {}
    if env:
        c.print("")
        c.print(Text("  Env vars", style="bold dim"))
        env_tbl = Table.grid(padding=(0, 2))
        env_tbl.add_column(width=2)
        env_tbl.add_column()
        for k, v in env.items():
            icon  = Text("✓", style="bright_green") if v else Text("✗", style="bright_red")
            style = "white" if v else "dim"
            env_tbl.add_row(icon, Text(k, style=style))
        c.print(env_tbl)


# ── CLI dispatcher (for bash callers) ────────────────────────────────────────

if __name__ == "__main__":
    import argparse, sys, os

    ap = argparse.ArgumentParser(prog="format_output")
    sub = ap.add_subparsers(dest="cmd")

    p_ready = sub.add_parser("ready-panel")
    p_ready.add_argument("--project", required=True)
    p_ready.add_argument("--code-dir", required=True)
    p_ready.add_argument("--vault-dir", required=True)
    p_ready.add_argument("--tool", action="append", default=[], help="repeat per tool")
    p_ready.add_argument("--step", action="append", default=[], help="repeat per next-step")
    p_ready.add_argument("--engine-summary", default="")
    p_ready.add_argument("--semgrep-summary", default="")

    p_fix = sub.add_parser("fix-mode-menu")
    p_fix.add_argument("--recommended", required=True)
    p_fix.add_argument("--confidence", default="?")
    p_fix.add_argument("--auto-count", type=int, default=0)

    args = ap.parse_args()

    if args.cmd == "ready-panel":
        print_ready_panel(
            project=args.project,
            code_dir=args.code_dir,
            vault_dir=args.vault_dir,
            tools=args.tool,
            next_steps=args.step or None,
            engine_summary=args.engine_summary,
            semgrep_summary=args.semgrep_summary,
        )
    elif args.cmd == "fix-mode-menu":
        prompt_fix_mode(args.recommended, args.confidence, args.auto_count)
    else:
        ap.print_help()
        sys.exit(2)
