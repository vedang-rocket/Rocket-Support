#!/usr/bin/env bash
# ============================================================
#  install.sh — rkt Rocket.new Support Tool Installer
#
#  Run via:
#    curl -fsSL https://raw.githubusercontent.com/vedang-rocket/rkt-support-tool/main/install.sh | bash
#  Or locally:
#    bash install.sh
# ============================================================
set -euo pipefail

# ── Colours ──────────────────────────────────────────────────
GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

ok()   { echo -e "  ${GREEN}✓${NC}  $1"; }
warn() { echo -e "  ${YELLOW}⚠${NC}  $1"; }
fail() { echo -e "  ${RED}✗${NC}  $1"; }
info() { echo -e "  ${CYAN}▸${NC}  $1"; }
section() { echo -e "\n${BOLD}${CYAN}── $1 ──────────────────────────────────────────${NC}"; }

# ── Paths ─────────────────────────────────────────────────────
RKT_DIR="$HOME/rocket-support"
RKT_REPO="git@github.com:vedang-rocket/rkt-support-tool.git"
ENGINE_DIR="$RKT_DIR/engine"
VENV_DIR="$ENGINE_DIR/.venv"
VENV_PY="$VENV_DIR/bin/python3"
GLOBAL_CLAUDE="$HOME/.claude"

# Track warnings for final summary
WARNINGS=()

# ── 1. Clone or update ────────────────────────────────────────
section "1/6  Clone / Update rkt-support-tool"

# Detect if we're already running from inside the repo
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || echo "")"
if [[ "$SCRIPT_DIR" == "$RKT_DIR" ]]; then
  info "Running from $RKT_DIR — pulling latest..."
  git -C "$RKT_DIR" pull --quiet 2>/dev/null && ok "Pulled latest" || warn "Pull failed — using existing code"
elif [[ -d "$RKT_DIR/.git" ]]; then
  info "Updating existing installation..."
  git -C "$RKT_DIR" pull --quiet 2>/dev/null && ok "Updated $RKT_DIR" || warn "Pull failed — using existing code"
else
  info "Cloning rkt-support-tool → $RKT_DIR"
  if git clone --quiet "$RKT_REPO" "$RKT_DIR" 2>/dev/null; then
    ok "Cloned → $RKT_DIR"
  else
    fail "Clone failed — check SSH key for github.com"
    WARNINGS+=("SSH clone failed — set up SSH key for github.com (vedang-rocket)")
    # If running via curl pipe, we can't continue without the repo
    [[ -d "$RKT_DIR" ]] || { echo -e "\n${RED}Cannot continue without repo. Exiting.${NC}"; exit 1; }
  fi
fi

# ── 2. Python venv ────────────────────────────────────────────
section "2/6  Python venv + dependencies"

if ! command -v python3 &>/dev/null; then
  fail "python3 not found — install via: brew install python"
  WARNINGS+=("python3 not installed")
else
  ok "python3 $(python3 --version 2>&1 | awk '{print $2}')"

  if [[ ! -d "$VENV_DIR" ]]; then
    info "Creating venv at $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
    ok "venv created"
  else
    ok "venv already exists"
  fi

  info "Installing/updating Python packages..."
  PACKAGES=(numpy semgrep scikit-learn scipy requests beautifulsoup4)
  "$VENV_PY" -m pip install --quiet --upgrade "${PACKAGES[@]}" 2>/dev/null \
    && ok "Packages ready: ${PACKAGES[*]}" \
    || warn "Some packages failed to install — engine may have reduced functionality"
fi

# ── 3. PATH setup ─────────────────────────────────────────────
section "3/6  PATH + environment"

ZSHRC="$HOME/.zshrc"
BASHRC="$HOME/.bashrc"

_add_to_shell() {
  local file="$1"
  local line="$2"
  local label="$3"
  if [[ -f "$file" ]] && grep -qF "$line" "$file" 2>/dev/null; then
    ok "$label already in $file"
  else
    echo "" >> "$file"
    echo "$line" >> "$file"
    ok "Added $label → $file"
  fi
}

PATH_LINE='export PATH="$HOME/rocket-support/bin:$PATH"'
ROCKET_BASE_LINE='export ROCKET_BASE="git@github-rocket:vedang-rocket"'

# Add to zshrc (primary on macOS)
_add_to_shell "$ZSHRC" "$PATH_LINE" "PATH"
_add_to_shell "$ZSHRC" "$ROCKET_BASE_LINE" "ROCKET_BASE"

# Also add to bashrc if it exists (for bash users / CI)
if [[ -f "$BASHRC" ]]; then
  _add_to_shell "$BASHRC" "$PATH_LINE" "PATH"
  _add_to_shell "$BASHRC" "$ROCKET_BASE_LINE" "ROCKET_BASE"
fi

# Apply to current session
export PATH="$HOME/rocket-support/bin:$PATH"
export ROCKET_BASE="git@github-rocket:vedang-rocket"

# ── 4. Global Claude tools ────────────────────────────────────
section "4/6  Global Claude hooks + skills"

mkdir -p "$GLOBAL_CLAUDE/hooks" "$GLOBAL_CLAUDE/skills"
ok "~/.claude/{hooks,skills} directories ready"

# Copy hooks
if [[ -d "$ENGINE_DIR/hooks" ]]; then
  cp "$ENGINE_DIR/hooks/"*.sh "$GLOBAL_CLAUDE/hooks/" 2>/dev/null && \
    chmod +x "$GLOBAL_CLAUDE/hooks/"*.sh 2>/dev/null
  ok "Hooks installed → ~/.claude/hooks/"
else
  info "No engine/hooks/ directory — skipping hook copy"
fi

# Copy skills
if [[ -d "$ENGINE_DIR/skills" ]]; then
  cp "$ENGINE_DIR/skills/"*.md "$GLOBAL_CLAUDE/skills/" 2>/dev/null
  ok "Skills installed → ~/.claude/skills/"
else
  info "No engine/skills/ directory — skipping skill copy"
fi

# Merge engine/mcp.json into ~/.claude/mcp.json
if [[ -f "$ENGINE_DIR/mcp.json" ]]; then
  info "Merging engine/mcp.json → ~/.claude/mcp.json..."
  python3 - << PYEOF
import json, os, sys

src_path = "$ENGINE_DIR/mcp.json"
dst_path = "$GLOBAL_CLAUDE/mcp.json"

with open(src_path) as f:
    src = json.load(f)

dst = {}
if os.path.exists(dst_path):
    try:
        with open(dst_path) as f:
            dst = json.load(f)
    except Exception:
        dst = {}

if "mcpServers" not in dst:
    dst["mcpServers"] = {}

added = []
for name, cfg in src.get("mcpServers", {}).items():
    if name not in dst["mcpServers"]:
        dst["mcpServers"][name] = cfg
        added.append(name)

with open(dst_path, "w") as f:
    json.dump(dst, f, indent=2)

if added:
    print(f"  \033[0;32m✓\033[0m  MCP servers added: {', '.join(added)}")
else:
    print("  \033[0;32m✓\033[0m  MCP servers already present")
PYEOF
else
  info "No engine/mcp.json — skipping MCP merge"
fi

# Merge engine/settings.json hooks into ~/.claude/settings.json
if [[ -f "$ENGINE_DIR/settings.json" ]]; then
  info "Merging engine/settings.json hooks → ~/.claude/settings.json..."
  python3 - << PYEOF
import json, os

src_path = "$ENGINE_DIR/settings.json"
dst_path = "$GLOBAL_CLAUDE/settings.json"

with open(src_path) as f:
    src = json.load(f)

dst = {}
if os.path.exists(dst_path):
    try:
        with open(dst_path) as f:
            dst = json.load(f)
    except Exception:
        dst = {}

if "hooks" not in dst:
    dst["hooks"] = {}

src_hooks = src.get("hooks", {})
added_events = []
for event, entries in src_hooks.items():
    if event not in dst["hooks"]:
        dst["hooks"][event] = entries
        added_events.append(event)
    # else: don't overwrite existing hooks for that event

with open(dst_path, "w") as f:
    json.dump(dst, f, indent=2)

if added_events:
    print(f"  \033[0;32m✓\033[0m  Hook events added: {', '.join(added_events)}")
else:
    print("  \033[0;32m✓\033[0m  Settings hooks already present")
PYEOF
else
  info "No engine/settings.json — skipping settings merge"
fi

# ── 5. Seed brain.db ─────────────────────────────────────────
section "5/6  Seed brain.db"

if [[ -f "$VENV_PY" && -f "$ENGINE_DIR/rkt_smart.py" ]]; then
  info "Seeding fix database..."
  SEED_OUTPUT=$("$VENV_PY" "$ENGINE_DIR/rkt_smart.py" --seed-db 2>&1) && {
    PATTERN_COUNT=$(echo "$SEED_OUTPUT" | grep -oE '[0-9]+ pattern' | head -1 || echo "")
    ok "brain.db seeded${PATTERN_COUNT:+ ($PATTERN_COUNT)}"
  } || warn "brain.db seed failed — run manually: python3 engine/rkt_smart.py --seed-db"
else
  warn "Skipping brain.db seed — venv or rkt_smart.py not found"
  WARNINGS+=("brain.db not seeded — run: cd ~/rocket-support && python3 engine/rkt_smart.py --seed-db")
fi

# ── 6. Checks ────────────────────────────────────────────────
section "6/6  System checks"

# Claude Code
if command -v claude &>/dev/null; then
  CLAUDE_VER=$(claude --version 2>/dev/null | head -1 || echo "installed")
  ok "Claude Code: $CLAUDE_VER"
else
  warn "Claude Code not found"
  WARNINGS+=("Install Claude Code: npm install -g @anthropic-ai/claude-code")
fi

# SSH key for github-rocket
if ssh -T git@github-rocket 2>&1 | grep -q "successfully authenticated"; then
  ok "SSH key: github-rocket authenticated"
else
  warn "SSH key for github-rocket not configured"
  WARNINGS+=("Set up SSH host alias 'github-rocket' → add to ~/.ssh/config")
fi

# semgrep
if [[ -f "$VENV_DIR/bin/semgrep" ]]; then
  SG_VER=$("$VENV_DIR/bin/semgrep" --version 2>/dev/null | head -1 || echo "installed")
  ok "semgrep: $SG_VER"
elif command -v semgrep &>/dev/null; then
  ok "semgrep: $(semgrep --version 2>/dev/null | head -1)"
else
  warn "semgrep not found"
  WARNINGS+=("semgrep missing — install via venv: pip install semgrep")
fi

# python3
ok "python3: $(python3 --version 2>&1)"

# ── Final summary ─────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}  rkt install complete${NC}"
echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
ok "rkt installed → $RKT_DIR/bin/rkt"
ok "rkt-main installed → $RKT_DIR/bin/rkt-main"
[[ -d "$VENV_DIR" ]] && ok "Python engine ready ($VENV_DIR)" || fail "Python engine not ready"
ok "Global hooks installed → ~/.claude/hooks/"
ok "Global skills installed → ~/.claude/skills/"

if [[ ${#WARNINGS[@]} -gt 0 ]]; then
  echo ""
  echo -e "  ${YELLOW}⚠  Manual steps needed:${NC}"
  for w in "${WARNINGS[@]}"; do
    echo -e "    ${YELLOW}–${NC} $w"
  done
fi

echo ""
echo -e "  ${BOLD}Reload your shell, then:${NC}"
echo -e "    ${CYAN}rkt cliently${NC}            → diagnose client repo"
echo -e "    ${CYAN}rkt-main cliently${NC}        → full setup + diagnosis"
echo -e "    ${CYAN}rkt ~/Downloads/project${NC}  → local folder"
echo ""
echo -e "  ${BOLD}Reload now:${NC}  source ~/.zshrc"
echo ""
