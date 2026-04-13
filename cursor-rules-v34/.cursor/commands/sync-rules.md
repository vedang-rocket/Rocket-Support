# Purpose: Sync rules between this project and your master rule repository

The master rule repository is the global brain.
This project's .cursor/ is the local instance.
/sync-rules keeps them connected.

## What This Does

**PULL**: Brings the latest rules from your master repo into this project.
Every improvement you made on Project A is instantly available in Project B.

**PUSH**: When you discover a new pattern here via /capture-convention,
/sync-rules proposes it as a PR to the master repo.
After you merge it, every future project gets it automatically.

---

## Setup (One Time)

### Step 1 — Create your master rule repository
```bash
# Create a new GitHub repo called "cursor-rules" (or whatever you want)
# Then clone it somewhere permanent on your machine:
git clone https://github.com/YOUR_USERNAME/cursor-rules ~/cursor-rules-master

# Copy your current V19 .cursor/ folder into it
cp -r .cursor/* ~/cursor-rules-master/
cd ~/cursor-rules-master
git add -A
git commit -m "initial: V19 rule system"
git push
```

### Step 2 — Store the master repo path
Add to your shell profile (`~/.zshrc` or `~/.bashrc`):
```bash
export CURSOR_RULES_MASTER="$HOME/cursor-rules-master"
```

Then reload: `source ~/.zshrc`

---

## PULL: Get Latest Rules From Master

```bash
# Run from any project root
MASTER="${CURSOR_RULES_MASTER:-$HOME/cursor-rules-master}"

if [ ! -d "$MASTER" ]; then
  echo "❌ Master repo not found at $MASTER"
  echo "Run setup steps above first."
  exit 1
fi

echo "Pulling latest rules from master repo..."

# Update master repo
cd "$MASTER" && git pull && cd -

# Sync rules (preserve project-specific mcp.json)
rsync -av --exclude='mcp.json' "$MASTER/.cursor/" ".cursor/"

echo "✅ Rules synced from master"
echo "Run: git diff .cursor/ to see what changed"
```

---

## PUSH: Propose New Pattern to Master

After running /capture-convention and adding a new rule to rocket-error-fixes.mdc or
rocket-cursor-behavior.mdc, run this to propose it to the master repo:

```bash
MASTER="${CURSOR_RULES_MASTER:-$HOME/cursor-rules-master}"
DATE=$(date '+%Y-%m-%d')
BRANCH="pattern-$(date '+%Y%m%d-%H%M%S')"

# Create a branch in master repo
cd "$MASTER"
git checkout -b "$BRANCH"

# Copy the updated rule files
cp "../$(basename $PWD)/.cursor/rules/rocket-error-fixes.mdc" ".cursor/rules/"
cp "../$(basename $PWD)/.cursor/rules/rocket-cursor-behavior.mdc" ".cursor/rules/"
cp "../$(basename $PWD)/memory-bank/learned-patterns.md" "memory-bank/"

git add -A
git commit -m "pattern: new discovery from $(basename $PWD) on $DATE"
git push origin "$BRANCH"

echo "✅ Branch created: $BRANCH"
echo "Review and merge at: https://github.com/YOUR_USERNAME/cursor-rules/compare/$BRANCH"
cd -
```

---

## MERGE LEARNINGS: Combine learned-patterns.md from multiple projects

```bash
MASTER="${CURSOR_RULES_MASTER:-$HOME/cursor-rules-master}"

# Append this project's new patterns to master (avoids duplicates)
echo "Merging learned-patterns.md..."

# Get entries from this project not in master
comm -23 \
  <(grep "^\[COUNT\|^\[MISTAKE\|^\[PATTERN\]" memory-bank/learned-patterns.md | sort) \
  <(grep "^\[COUNT\|^\[MISTAKE\|^\[PATTERN\]" "$MASTER/memory-bank/learned-patterns.md" | sort) \
  >> "$MASTER/memory-bank/learned-patterns.md"

echo "✅ New patterns merged to master"
```

---

## The Compounding Effect

```
Project 1: discover getSession() bug → /capture-convention → /sync-rules push
Master repo: new rule merged
Project 2: /sync-rules pull → already knows getSession() pattern
Project 3: /sync-rules pull → already knows it
Project 50: Cursor walks into every project knowing every pattern
             discovered across all 49 previous projects
```

This is how the system goes from "smart" to "institutional."

---

## Daily Workflow

**Start of new project:**
```bash
/sync-rules  # pull latest from master first
```

**After discovering a new pattern:**
```bash
/capture-convention  # format the rule
/sync-rules          # push to master
```

**End of week:**
```bash
/sync-rules  # merge this week's learnings to master
```
