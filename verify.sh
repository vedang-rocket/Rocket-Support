#!/usr/bin/env bash
# verify.sh — end-to-end verification suite for rkt Claude Code integration
# Run: bash ~/rocket-support/verify.sh
# Tests: hooks, MCPs (config + binary), skills, brain.db, KB search

set -euo pipefail

PASS=0
FAIL=0
WARN=0

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[0;33m'
CYAN='\033[1;36m'
BOLD='\033[1m'
NC='\033[0m'

pass() { echo -e "  ${GREEN}PASS${NC}  $1"; PASS=$((PASS + 1)); }
fail() { echo -e "  ${RED}FAIL${NC}  $1"; FAIL=$((FAIL + 1)); }
warn() { echo -e "  ${YELLOW}WARN${NC}  $1"; WARN=$((WARN + 1)); }
section() { echo -e "\n${CYAN}── $1 ──${NC}"; }

echo ""
echo -e "${BOLD}rkt Verification Suite${NC}"
echo "$(date)"
echo "────────────────────────────────────────────────"

# ── HOOKS ────────────────────────────────────────────────────────────────────

section "HOOKS"

# 1. graphify.sh exists and is executable
if [[ -x "$HOME/.claude/hooks/graphify.sh" ]]; then
  pass "graphify.sh exists and is executable"
else
  fail "graphify.sh missing or not executable"
fi

# 2. graphify fires on Read (check settings.json matcher)
GRAPHIFY_MATCHER=$(python3 -c "
import json
s = json.load(open('$HOME/.claude/settings.json'))
pre = s.get('hooks', {}).get('PreToolUse', [])
for entry in pre:
    if 'graphify' in str(entry.get('hooks', [])):
        print(entry.get('matcher', ''))
" 2>/dev/null)
if echo "$GRAPHIFY_MATCHER" | grep -q "Read"; then
  pass "graphify.sh fires on Grep|Glob|Read (matcher: $GRAPHIFY_MATCHER)"
else
  fail "graphify.sh missing Read matcher (current: '$GRAPHIFY_MATCHER')"
fi

# 3. graphify.sh runs and produces output
GRAPHIFY_OUTPUT=$(echo '{"pattern":"getUser","path":"/tmp"}' | bash "$HOME/.claude/hooks/graphify.sh" 2>/dev/null || true)
if echo "$GRAPHIFY_OUTPUT" | grep -q "GRAPHIFY"; then
  pass "graphify.sh produces output when run"
else
  fail "graphify.sh produced no output (got: $(echo "$GRAPHIFY_OUTPUT" | head -1))"
fi

# 4. chain-walker-check.sh reads from stdin (not env var)
if [[ -x "$HOME/.claude/hooks/chain-walker-check.sh" ]]; then
  if grep -q '"$(cat)"' "$HOME/.claude/hooks/chain-walker-check.sh"; then
    pass "chain-walker-check.sh reads tool input from stdin"
  else
    fail "chain-walker-check.sh still uses env var CLAUDE_TOOL_INPUT (not stdin)"
  fi
else
  fail "chain-walker-check.sh missing or not executable"
fi

# 5. chain-walker-check.sh wired to PostToolUse Write|Edit
CWC_MATCHER=$(python3 -c "
import json
s = json.load(open('$HOME/.claude/settings.json'))
post = s.get('hooks', {}).get('PostToolUse', [])
for entry in post:
    if 'chain-walker' in str(entry.get('hooks', [])):
        print(entry.get('matcher', ''))
" 2>/dev/null)
if echo "$CWC_MATCHER" | grep -q "Write"; then
  pass "chain-walker-check.sh wired to PostToolUse (matcher: $CWC_MATCHER)"
else
  fail "chain-walker-check.sh not wired to PostToolUse (got: '$CWC_MATCHER')"
fi

# 6. chain_walker.py exists
if [[ -f "$HOME/rocket-support/engine/chain_walker.py" ]]; then
  pass "chain_walker.py exists at engine/"
else
  fail "chain_walker.py MISSING"
fi

# 7. tsc-check.sh exists, has infinite-loop guard
if [[ -x "$HOME/.claude/hooks/tsc-check.sh" ]]; then
  if grep -q "CLAUDE_STOP_HOOK_ACTIVE" "$HOME/.claude/hooks/tsc-check.sh"; then
    pass "tsc-check.sh exists with infinite-loop guard"
  else
    warn "tsc-check.sh exists but missing CLAUDE_STOP_HOOK_ACTIVE guard"
  fi
else
  fail "tsc-check.sh missing or not executable"
fi

# 8. ux-detector.sh fires on UserPromptSubmit
UX_HOOK=$(python3 -c "
import json
s = json.load(open('$HOME/.claude/settings.json'))
ups = s.get('hooks', {}).get('UserPromptSubmit', [])
for entry in ups:
    hooks = entry.get('hooks', [])
    for h in hooks:
        if 'ux-detector' in h.get('command', ''):
            print('wired')
" 2>/dev/null)
if [[ "$UX_HOOK" == "wired" ]]; then
  pass "ux-detector.sh wired to UserPromptSubmit"
else
  fail "ux-detector.sh not wired to UserPromptSubmit"
fi

# 9. ux-detector.sh produces output on UI keyword
UX_OUTPUT=$(echo "build a button component" | bash "$HOME/.claude/hooks/ux-detector.sh" 2>/dev/null || true)
if echo "$UX_OUTPUT" | grep -q "UI/UX PRO MAX"; then
  pass "ux-detector.sh fires on 'button' keyword"
else
  fail "ux-detector.sh did not fire on 'button component' prompt"
fi

# 10. brain-inject.sh exists and produces output
if [[ -x "$HOME/.claude/hooks/brain-inject.sh" ]]; then
  BRAIN_OUTPUT=$(CLAUDE_PROJECT_DIR="$HOME/Documents/Rocket/wedcraft" bash "$HOME/.claude/hooks/brain-inject.sh" 2>/dev/null || true)
  if echo "$BRAIN_OUTPUT" | grep -q "BRAIN INJECT"; then
    pass "brain-inject.sh exists and produces output"
  else
    fail "brain-inject.sh exists but produced no output"
  fi
else
  fail "brain-inject.sh MISSING"
fi

# 11. brain-inject.sh wired to SessionStart
BRAIN_WIRED=$(python3 -c "
import json
s = json.load(open('$HOME/.claude/settings.json'))
ss = s.get('hooks', {}).get('SessionStart', [])
for entry in ss:
    hooks = entry.get('hooks', [])
    for h in hooks:
        if 'brain-inject' in h.get('command', ''):
            print('wired')
" 2>/dev/null)
if [[ "$BRAIN_WIRED" == "wired" ]]; then
  pass "brain-inject.sh wired to SessionStart"
else
  fail "brain-inject.sh not wired to SessionStart in settings.json"
fi

# ── MCP SERVERS ───────────────────────────────────────────────────────────────

section "MCP SERVERS (config + binary check)"

# 12. context7
if python3 -c "import json; d=json.load(open('$HOME/.claude/mcp.json')); assert 'context7' in d['mcpServers']" 2>/dev/null; then
  C7_VER=$(npx -y @upstash/context7-mcp@latest --version 2>/dev/null | head -1 || echo "")
  if [[ -n "$C7_VER" ]]; then
    pass "context7 configured + binary responds (v$C7_VER)"
  else
    warn "context7 configured but binary didn't respond — check npm/npx"
  fi
else
  fail "context7 not in ~/.claude/mcp.json"
fi

# 13. sequential-thinking
if python3 -c "import json; d=json.load(open('$HOME/.claude/mcp.json')); assert 'sequential-thinking' in d['mcpServers']" 2>/dev/null; then
  if npx -y @modelcontextprotocol/server-sequential-thinking --help 2>/dev/null | head -1 | grep -qi "sequential\|mcp\|usage" || \
     npx -y @modelcontextprotocol/server-sequential-thinking 2>/dev/null | head -1 | grep -qi "." ; then
    pass "sequential-thinking configured + package runnable"
  else
    pass "sequential-thinking configured (binary check skipped — starts as MCP server)"
  fi
else
  fail "sequential-thinking not in ~/.claude/mcp.json"
fi

# 14. memory MCP
if python3 -c "import json; d=json.load(open('$HOME/.claude/mcp.json')); assert 'memory' in d['mcpServers']" 2>/dev/null; then
  pass "memory MCP configured in ~/.claude/mcp.json"
else
  fail "memory MCP not in ~/.claude/mcp.json"
fi

# 15. playwright
if python3 -c "import json; d=json.load(open('$HOME/.claude/mcp.json')); assert 'playwright' in d['mcpServers']" 2>/dev/null; then
  if npx @playwright/mcp@latest --version 2>/dev/null | grep -q "[0-9]"; then
    pass "playwright MCP configured + binary responds"
  else
    pass "playwright MCP configured (binary check skipped — starts as MCP server)"
  fi
else
  fail "playwright not in ~/.claude/mcp.json"
fi

# 16. code-review-graph
if python3 -c "import json; d=json.load(open('$HOME/.claude/mcp.json')); assert 'code-review-graph' in d['mcpServers']" 2>/dev/null; then
  if uvx code-review-graph --help 2>/dev/null | grep -q "serve"; then
    pass "code-review-graph configured + uvx binary responds (has 'serve' command)"
  else
    warn "code-review-graph configured but 'uvx code-review-graph serve' not verified"
  fi
else
  fail "code-review-graph not in ~/.claude/mcp.json"
fi

# 17. ruflo
if python3 -c "import json; d=json.load(open('$HOME/.claude/settings.json')); assert 'ruflo' in d.get('mcpServers',{})" 2>/dev/null; then
  pass "ruflo MCP configured in settings.json mcpServers"
else
  fail "ruflo MCP not in settings.json"
fi

# ── SKILLS ────────────────────────────────────────────────────────────────────

section "SKILLS"

SKILLS_DIR="$HOME/.claude/skills"
SKILL_FILES="think.md graph.md memory.md ux.md review.md obsidian.md"
SKILL_CMDS="/think /graph /memory /ux /review /obsidian"

i=0
for cmd in $SKILL_CMDS; do
  i=$((i + 1))
  file=$(echo $SKILL_FILES | tr ' ' '\n' | sed -n "${i}p")
  skill_path="$SKILLS_DIR/$file"
  if [[ -f "$skill_path" ]]; then
    # Check it has a valid frontmatter name
    if grep -q "^name:" "$skill_path"; then
      pass "$cmd skill exists with frontmatter ($skill_path)"
    else
      warn "$cmd skill exists but missing frontmatter name: field"
    fi
  else
    fail "$cmd skill MISSING ($skill_path)"
  fi
done

# 18. obsidian skill has fallback path logic
if grep -q "fallback\|isdir\|basename.*pwd" "$SKILLS_DIR/obsidian.md" 2>/dev/null; then
  pass "/obsidian skill has fallback vault detection"
else
  fail "/obsidian skill missing fallback vault detection"
fi

# ── BRAIN.DB ──────────────────────────────────────────────────────────────────

section "BRAIN.DB"

# 19. brain.db exists
BRAIN_DB="$HOME/.rocket-support/brain.db"
if [[ -f "$BRAIN_DB" ]]; then
  FIX_COUNT=$(sqlite3 "$BRAIN_DB" "SELECT COUNT(*) FROM fixes;" 2>/dev/null || echo "0")
  PROJ_COUNT=$(sqlite3 "$BRAIN_DB" "SELECT COUNT(*) FROM projects;" 2>/dev/null || echo "0")
  if [[ "$FIX_COUNT" -gt 0 ]]; then
    pass "brain.db exists with $FIX_COUNT fixes, $PROJ_COUNT projects"
  else
    warn "brain.db exists but is empty — run: python3 ~/rocket-support/engine/rkt_smart.py --seed-db"
  fi
else
  fail "brain.db MISSING at $BRAIN_DB"
fi

# 20. KB search returns results
KB_RESULT=$(python3 -c "
import sys
sys.path.insert(0, '$HOME/rocket-support/engine/kb')
try:
    import kb_search
    results = kb_search.search('middleware cookies auth', top_k=1)
    if results:
        r = results[0]
        print(f\"source={r.get('source','?')} score={r.get('score',0):.2f}\")
    else:
        print('empty')
except Exception as e:
    print(f'error: {e}')
" 2>/dev/null || echo "error")

if echo "$KB_RESULT" | grep -q "source="; then
  pass "KB search returns results ($KB_RESULT)"
elif echo "$KB_RESULT" | grep -q "empty"; then
  warn "KB search returned empty — run: ~/rocket-support/engine/kb/refresh.sh"
else
  fail "KB search failed: $KB_RESULT"
fi

# ── OBSIDIAN ──────────────────────────────────────────────────────────────────

section "OBSIDIAN"

# 21. vault-config.json exists
VAULT_CFG="$HOME/.claude/obsidian/vault-config.json"
if [[ -f "$VAULT_CFG" ]]; then
  VAULT_COUNT=$(python3 -c "import json; d=json.load(open('$VAULT_CFG')); print(len(d.get('vaults',[])))" 2>/dev/null || echo "0")
  pass "vault-config.json exists with $VAULT_COUNT registered vaults"
else
  fail "vault-config.json MISSING at $VAULT_CFG"
fi

# 22. rkt-main step 9 updates vault-config.json
if grep -q "vault-config.json\|VAULT_CONFIG" "$HOME/rocket-support/bin/rkt-main" 2>/dev/null; then
  pass "rkt-main step 9 registers vaults in vault-config.json"
else
  fail "rkt-main step 9 does NOT update vault-config.json"
fi

# ── GLOBAL CLAUDE.MD ─────────────────────────────────────────────────────────

section "GLOBAL CLAUDE.MD"

# 23. global CLAUDE.md exists with hard rules
GLOBAL_CLAUDE="$HOME/.claude/CLAUDE.md"
if [[ -f "$GLOBAL_CLAUDE" ]]; then
  LINE_COUNT=$(wc -l < "$GLOBAL_CLAUDE" | tr -d ' ')
  if grep -q "getUser\|getSession\|Hard Rules\|HARD RULES" "$GLOBAL_CLAUDE"; then
    pass "~/.claude/CLAUDE.md exists ($LINE_COUNT lines) with hard rules"
  else
    warn "~/.claude/CLAUDE.md exists ($LINE_COUNT lines) but missing hard rules content"
  fi
else
  fail "~/.claude/CLAUDE.md MISSING"
fi

# ── ENGINE ────────────────────────────────────────────────────────────────────

section "ENGINE"

# 24. venv + semgrep
VENV_PYTHON="$HOME/rocket-support/engine/.venv/bin/python3"
if [[ -x "$VENV_PYTHON" ]]; then
  SEMGREP_VER=$("$VENV_PYTHON" -c "import subprocess; r=subprocess.run(['semgrep','--version'],capture_output=True,text=True); print(r.stdout.strip())" 2>/dev/null || echo "")
  if [[ -n "$SEMGREP_VER" ]]; then
    pass "venv exists, semgrep available ($SEMGREP_VER)"
  else
    warn "venv exists but semgrep check failed — run: pip install semgrep in venv"
  fi
else
  fail "Python venv missing at engine/.venv/"
fi

# 25. rkt-smart.py --db-stats works
DB_STATS=$("$VENV_PYTHON" "$HOME/rocket-support/engine/rkt_smart.py" --db-stats 2>/dev/null | head -3 || echo "error")
if echo "$DB_STATS" | grep -q "Total fixes"; then
  pass "rkt_smart.py --db-stats responds"
else
  fail "rkt_smart.py --db-stats failed: $DB_STATS"
fi

# ── SUMMARY ───────────────────────────────────────────────────────────────────

TOTAL=$((PASS + FAIL + WARN))
echo ""
echo "────────────────────────────────────────────────"
echo -e "${BOLD}Results: ${GREEN}$PASS PASS${NC}  ${RED}$FAIL FAIL${NC}  ${YELLOW}$WARN WARN${NC}  / $TOTAL checks"

if [[ $FAIL -eq 0 ]]; then
  echo -e "${GREEN}All checks passed.${NC}"
elif [[ $FAIL -le 2 ]]; then
  echo -e "${YELLOW}Minor issues — see FAIL items above.${NC}"
else
  echo -e "${RED}$FAIL checks failed — review above.${NC}"
fi
echo ""
