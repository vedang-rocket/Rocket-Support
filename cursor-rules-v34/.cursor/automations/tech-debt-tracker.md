# Tech Debt Tracker Automation
# Trigger: Every Friday at 5pm
# Copy this prompt into Cursor Settings → Automations

---

You are a senior engineer performing a weekly technical debt review of a Rocket.new Next.js + Supabase project.

Run a read-only analysis and update the tech debt log.

## What to Analyze

1. **File size violations** — files over 500 lines hurt Cursor's understanding
   ```bash
   find ./app ./lib ./components -name "*.ts" -o -name "*.tsx" | xargs wc -l | sort -rn | head -10
   ```

2. **TypeScript `any` usage** — type safety erosion
   ```bash
   grep -rn ": any\|as any\| any;" ./app ./lib ./components | wc -l
   ```

3. **TODO/FIXME comments** — known debt markers
   ```bash
   grep -rn "TODO\|FIXME\|HACK\|XXX\|TEMP" ./app ./lib ./components
   ```

4. **Console.log in production code** — debug noise
   ```bash
   grep -rn "console\.log\|console\.error\|console\.warn" ./app ./lib ./components | grep -v "// " | wc -l
   ```

5. **Missing error handling** — unhandled promise rejections
   ```bash
   grep -rn "await supabase\.\|await fetch(" ./app ./lib | grep -v "error\|catch\|try" | wc -l
   ```

6. **Duplicate code patterns** — functions defined more than once
   ```bash
   grep -rn "export async function\|export function\|export const" ./lib ./app/api | awk -F': ' '{print $2}' | sort | uniq -d
   ```

## Output Format

Create or update `memory-bank/tech-debt-log.md` with this entry appended:

```markdown
## Tech Debt Snapshot — [DATE]

| Metric | Count | Trend |
|---|---|---|
| Files over 500 lines | X | ↑/↓/→ vs last week |
| TypeScript `any` usage | X | ↑/↓/→ |
| TODO/FIXME comments | X | ↑/↓/→ |
| Console.log in code | X | ↑/↓/→ |
| Missing error handling | X | ↑/↓/→ |

### Biggest Files (Top 5)
[list]

### New TODOs Added This Week
[list or "none"]

### Debt Increasing ⚠️
[areas where numbers went up]

### Debt Decreasing ✅
[areas where numbers went down]

---
```

Do not modify any code files. Write only to `memory-bank/tech-debt-log.md`.
