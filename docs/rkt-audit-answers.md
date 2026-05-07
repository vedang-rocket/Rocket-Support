# rkt Codebase Audit — All 10 Questions Answered
# From actual file reads. No guessing.
# Date: May 2026


---

## Q1 — What does rkt-crazy do end to end?

Takes a zip file (not threadId). Runs three phases.

PHASE 1 — TRIAGE (always runs):
1. Extracts zip via workspace.create_workspace()
2. Runs bun install in workspace
3. Runs run_triage.py → triage_graph.py full LangGraph pipeline
4. Gets back: fix_mode (AUTO/GUIDED/CLAUDE/MANUAL), overall_confidence, auto_fixable_count

PHASE 2 — SETUP (skipped with --fast flag):
- Runs rkt-main --no-diagnose on workspace
- Installs: 61 Cursor rules, Graphify, UI/UX Pro Max, skills, MCPs, CLAUDE.md,
  code-review-graph, Obsidian, RuFlo

PHASE 3 — FIX MODE MENU (always runs):
Shows 4 options. Recommended is pre-selected based on triage result.

  [1] AUTO    — runs rkt_smart.py --yes --non-interactive --skip-semgrep
                APPLIES ALL FIXES AUTOMATICALLY. No approval asked.
                Then runs retriage.py on modified files.
  [2] GUIDED  — writes .rkt_prompt.md with findings, opens Cursor
  [3] CLAUDE  — launches: claude --dangerously-skip-permissions in workspace
  [4] MANUAL  — runs rkt_smart.py --skip-semgrep (shows diff, asks a/s/v/q per file)

After fix mode: runs handoff.py, then shows workspace path.

LAST THING ENGINEER SEES (AUTO mode):
  Fixes applied. Run: rkt-deliver to package and deliver

  Workspace
  ▸ cd   /path/to/workspace
  ▸ open /path/to/workspace

CODE REFERENCE:
  rkt-crazy line 313: "$PYTHON" "$ENGINE_DIR/rkt_smart.py" --yes --non-interactive --skip-semgrep
  rkt-crazy line 336: echo "Fixes applied. Run: rkt-deliver"


---

## Q2 — What does rkt-ok do currently?

Does NOT call the engine.
Does NOT call Claude API.
Zero diagnosis. Zero fix.

Does exactly 5 things:
1. SSH → rocket clean on remote container
2. SSH → rocket init <threadId> on remote container
3. Detects project folder in ~/app on remote
4. Runs rkt-rules-add to install cursor-rules-v34 on remote project
5. Opens Cursor remotely: cursor --remote ssh-remote+<host> <remote_path>
6. Opens Ghostty split panes via AppleScript:
   - Left pane:  SSH → npm install → npm run build → npm run serve
   - Right pane: SSH → raw bash shell in project directory

rkt-ok is purely a SESSION LAUNCHER. It sets up the environment.
It does not diagnose. It does not fix.

CODE REFERENCE:
  rkt-ok line 30: INIT_OUTPUT=$(ssh "$SSH_HOST" "printf '1\ny\n' | rocket init $THREAD_ID")
  rkt-ok line 54: cursor --remote "ssh-remote+$SSH_HOST" "$REMOTE_PROJECT_PATH" &


---

## Q3 — Current terminal output format (triage report)

Based on triage_graph.py node_build_summary() — this is the exact structure printed:

════════════════════════════════════════════════════════════
  RKT TRIAGE REPORT
════════════════════════════════════════════════════════════
  Project type : SaaS  (confidence 87%)
  Next.js      : 15.1.0
  Supabase     : yes  Stripe: yes
  Port         : 3001

  Issue        : auth broken after login
  Symptom cat  : AUTH (matched from issue description)
  Fix mode     : AUTO  (avg confidence 97%)
  Auto-fixable : 2 finding(s)

  FINDINGS:
  ★ [AUTO:97%]       [chain_walker       ] middleware.ts missing updateSession()  ✓ confirmed
    [AUTO:97%]       [probe              ] getsession @ lib/supabase/server.ts:12

  KNOWN FIX    : getSession() in server code
  Category     : AUTH  (score 0.89)

  Timings: fingerprint_ms=45  chain_walker_ms=180  schema_ms=12  total=850ms
════════════════════════════════════════════════════════════

After this the fix-mode menu appears and engineer picks 1-4.

★ marker = symptom matched from issue description
✓ confirmed = same finding caught by 2+ detection layers


---

## Q4 — What does fix_writer.py output? Auto or approval?

DEPENDS ON MODE:

MANUAL / interactive (no flags):
  Shows colored unified diff per file.
  Prompts: [review] action? [a]pply/[s]kip/[v]iew full/[q]uit
  Engineer approves file by file.

AUTO mode (--yes --non-interactive):
  No prompts. Applies every write-capable proposal silently.
  This is what rkt-crazy AUTO uses.
  Shows summary at end:
    [fix_writer] Applied 2 new fixes this run
    [fix_writer] Skipped 0
    [fix_writer] Progress 2/2 actionable issues across 2 file(s)

CODE REFERENCE:
  rkt_smart.py line 437: elif args.yes: selected_paths = {p.file_path for p in apply_candidates}
  rkt_smart.py line 444: selected_paths = _interactive_review(plan.proposals)


---

## Q5 — brain.db current state

Query run: SELECT category, COUNT(*), AVG(uses) FROM fixes GROUP BY category;
(Note: no confidence column exists — AVG(uses) returned instead)

Result:
  AUTH     | 13 patterns | avg 6.3 uses  ← most battle-tested
  STRIPE   | 11 patterns | avg 2.5 uses
  SUPABASE |  6 patterns | avg 1.7 uses
  BUILD    |  5 patterns | avg 1.0 uses
  UI       |  3 patterns | avg 1.0 uses  ← freshly seeded
  ENV      |  1 pattern  | avg 2.0 uses
  RLS      |  1 pattern  | avg 3.0 uses

TOTAL: 40 patterns across 7 categories

AUTH is most reliable (hit 6x per pattern on average).
UI, BUILD, ENV are least proven (1x average — recently added, not yet battle-tested).


---

## Q6 — Does chain_walker return JSON or plain text?

Returns Python list of dicts. NOT a JSON string. NOT plain text.

When called as a module (which everything does), walk() returns:

[
  {
    "chain":      "AUTH",
    "broken_at":  "middleware.ts",
    "missing":    "updateSession",
    "issue":      "middleware.ts missing updateSession() — cookies won't refresh",
    "fix_hint":   "Refactor middleware to call updateSession(request)...",
    "confidence": 1.0
  },
  ...
]

When run directly from CLI (python chain_walker.py <path>):
  Prints plain text to stdout for human reading.
  But nothing in the pipeline runs it as subprocess — always imported as module.

CODE REFERENCE:
  chain_walker.py line 230-237: returns dict with chain/broken_at/missing/issue/fix_hint/confidence


---

## Q7 — Does triage_graph.py exist?

YES. Fully read. It is a LangGraph StateGraph with 11 nodes.

PIPELINE (all straight edges, NO conditional branches today):
  fingerprint → chain_walker → schema → semgrep → fs_checks
             → context_filter → deduplicate → db_lookup
             → score_and_route → symptom_rank → build_summary → END

KEY NODES:
  score_and_route  — assigns fix_mode (AUTO/GUIDED/CLAUDE/MANUAL) and confidence per finding
  db_lookup        — calls rkt_engine.db_lookup() → db.find_similar() [THIS IS WHAT WE UPGRADE]
  symptom_rank     — re-orders findings based on client's issue description keywords
  build_summary    — builds the triage report string shown in terminal

CONFIDENCE THRESHOLDS in score_and_route:
  avg >= 0.85 AND auto_count > 0  → AUTO
  avg >= 0.60                     → GUIDED
  avg >= 0.40                     → CLAUDE
  else                            → MANUAL

CODE REFERENCE:
  triage_graph.py line 374-402: graph assembly with all nodes and edges


---

## Q8 — Which files import Claude API today?

6 files found by grep:

  engine/rkt_engine.py   — MAIN: sends surgical context JSON, receives fix JSON back
  engine/rkt_smart.py    — orchestrates Claude call via rkt_engine
  engine/probe_scanner.py — uses Claude/ast-grep for rule matching
  engine/fingerprint.py  — possibly Claude-assisted project type detection
  engine/deliverer.py    — packages fixed project, may generate delivery summary
  engine/gen_claude_md.py — generates CLAUDE.md files for client projects


---

## Q9 — What is rkt-main step 11 "Engine Intelligence" (last 100 lines)?

Three sub-steps at the end of rkt-main (around lines 875-975):

E2 — probe_scanner:
  Runs probe_scanner.run_probe_scanner(PROJECT_DIR)
  Prints: "probe_scanner: N issue(s) found" or "probe_scanner: no violations"
  Skipped if RKT_SKIP_SEMGREP=1 (which rkt-crazy sets)

E3 — Seed brain.db:
  Pipes fingerprint JSON into seed_project.py
  Saves project fingerprint to brain.db projects table

READY PANEL:
  Runs format_output.py ready-panel
  Shows rich terminal panel: project name, code dir, vault dir, tools installed,
  engine summary, semgrep summary, next steps

E4 — Full diagnosis (only if --diagnose flag, NOT --no-diagnose):
  If RUN_DIAGNOSE is true:
    Runs rkt_smart.py with SMART_ARGS (full chain_walker + probe + brain.db + KB + Claude)
  If --no-diagnose (default when called from rkt-crazy):
    E4 does NOT run

CODE REFERENCE:
  rkt-main line 968-974:
    if $RUN_DIAGNOSE; then
      "$ENGINE_VENV" "$ENGINE_SMART" "$PROJECT_DIR" "${SMART_ARGS[@]}"
    fi


---

## Q10 — Realistic terminal output of rkt-crazy from start to finish

rkt-crazy ~/Downloads/wedcraft.zip "auth broken after login"

rkt-crazy — Triage + Setup + Fix

── Phase 1 / Triage — Step 1/3  Creating workspace ──
  ▸ Zip:   /Users/vedang/Downloads/wedcraft.zip
  ▸ Issue: auth broken after login
  ✓ Workspace: wedcraft_1746559201
  ✓ Path:      /Users/vedang/rocket-support/workspace/wedcraft_1746559201
  ✓ Port:      3001

── Phase 1 / Triage — Step 2/3  Installing dependencies ──
  ⠸  bun install
  ✓ bun install complete

── Phase 1 / Triage — Step 3/3  Running triage pipeline ──
  ▸ Analyzing project...
  ✓ Triage complete  (confidence: 94%, 2 auto-fixable, recommended: AUTO)

── Phase 2 / Setup  Running rkt-main on workspace ──
  ▸ Installing: Cursor rules, Graphify, UI/UX Pro Max, skills, MCPs, CLAUDE.md...
  ▸ Workspace: /Users/vedang/rocket-support/workspace/wedcraft_1746559201
  [rkt-main runs for 30-60 seconds, installs everything]
  ✓ Setup complete

  [1] AUTO    ← recommended
  [2] GUIDED
  [3] CLAUDE
  [4] MANUAL

  Enter number [default 1]:
[engineer presses Enter]

  ▸ Running rkt_smart.py with --yes --non-interactive...

[fix_writer] Applied 2 new fixes this run
[fix_writer] Skipped 0 (already fixed/non-actionable)
[fix_writer] Diff-only 0 (manual review required)
[fix_writer] Progress 2/2 actionable issues across 2 file(s)

  Fixes applied. Run: rkt-deliver to package and deliver

  Workspace
  ▸ cd   /Users/vedang/rocket-support/workspace/wedcraft_1746559201
  ▸ open /Users/vedang/rocket-support/workspace/wedcraft_1746559201

--- END OF rkt-crazy RUN ---

Engineer then opens workspace in Cursor, reviews 2 changed files, runs rkt-deliver.


---

## SUMMARY — KEY FACTS

| Question | Answer |
|---|---|
| rkt-crazy input | zip file + issue description |
| rkt-ok input | threadId (SSH-based, no engine) |
| rkt-ok calls engine? | NO |
| rkt-ok calls Claude? | NO |
| fix_writer auto-applies? | YES in AUTO mode, asks in MANUAL mode |
| brain.db total patterns | 40 (across 7 categories) |
| chain_walker return type | Python list of dicts (not JSON string) |
| triage_graph.py exists? | YES — LangGraph StateGraph, 11 nodes, linear |
| Files using Claude API | 6 files (rkt_engine, rkt_smart, probe_scanner, fingerprint, deliverer, gen_claude_md) |
| rkt-main E4 diagnosis | Only runs if --diagnose flag. Default is --no-diagnose. |
| rkt-crazy calls Claude? | YES — via AUTO mode → rkt_smart.py → rkt_engine.py |
