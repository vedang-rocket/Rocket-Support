# TROUBLESHOOTING.md — Rocket Cursor Rules V19

Common setup and runtime problems with exact solutions.

---

## MCP Problems

### Problem: Supabase MCP shows red dot / "Client closed"
**Most common cause**: Wrong argument format

Check `.cursor/mcp.json` — the correct format is:
```json
"supabase": {
  "command": "npx",
  "args": [
    "-y", "@supabase/mcp-server-supabase@latest",
    "--project-ref", "YOUR_PROJECT_REF",
    "--read-only"
  ],
  "env": { "SUPABASE_ACCESS_TOKEN": "sbp_YOUR_PAT" }
}
```

Common mistakes that break it:
- Using `--supabase-url` instead of `--project-ref` → `ERR_PARSE_ARGS_UNKNOWN_OPTION`
- Putting the URL instead of the project ref (the short code, not the full URL)
- Putting the PAT as a CLI arg instead of in `env` block
- PAT is expired or revoked → generate a new one at supabase.com/dashboard/account/tokens

### Problem: Supabase MCP connects but `list_tables` fails with "project_id required"
The server needs `--project-ref` in the args (not just the access token).
Make sure your mcp.json has `"--project-ref", "YOUR_REF"` in the args array.

### Problem: Stripe MCP shows "Invalid tool" error
The `--tools` flag was removed from `@stripe/mcp`. Remove it from your mcp.json.
Correct format: `"args": ["-y", "@stripe/mcp"]` with no `--tools` flag.

### Problem: Memory MCP fails with "No matching version"
Remove the version pin. Use: `"args": ["-y", "@modelcontextprotocol/server-memory"]`

### Problem: MCP shows green but tools don't appear in Cursor
Cursor caps at 40 MCP tools total. If you have many servers, some tools get dropped.
Run `/check-mcp` to see what's actually available.

### Problem: MCP credentials keep getting lost when switching projects
This is expected — credentials are per-project in mcp.json.
Workflow: open project → update mcp.json with that project's credentials → Reload Window.
30 seconds per project.

---

## Hook Problems

### Problem: Hooks not firing at all
```bash
# Confirm scripts are executable
ls -la .cursor/hooks-scripts/*.sh | grep "^-rwx"
# If any show "-rw-" (not executable):
chmod +x .cursor/hooks-scripts/*.sh
```

### Problem: session-learning.sh errors on session end
Check if `jq` is available: `which jq`
The script has a fallback if jq is missing, but results may be less accurate.
Install: `brew install jq`

### Problem: block-dangerous.sh blocking a legitimate command
Add `ECC_DISABLED_HOOKS=block-dangerous` to your shell environment temporarily.
Or edit the script — the `is_dangerous()` function lists all blocked patterns.

### Problem: secrets-guard.sh blocking a command that doesn't contain secrets
The patterns are conservative. If a false positive occurs:
`ECC_DISABLED_HOOKS=secrets-guard` to disable temporarily.

---

## Rules Problems

### Problem: Rules not auto-loading (auto-load rules never trigger)
Rules load based on description matching. If a rule isn't loading:
1. Check the description contains trigger phrases that match your message
2. Ask Cursor: "Which rules are you applying?" — it will list them
3. Manually reference: `@rules/rocket-supabase.mdc` to force-load

### Problem: "Applying rules: none" at start of every response
The always-on rules (`rocket-cursor-behavior.mdc`, `rocket-quick-reference.mdc`) should always load.
If they don't: confirm `.cursor/rules/` is inside the project root (not a subfolder).

### Problem: Rules referring to old file names after V19 split
V19 split three large files:
- `rocket-code-patterns.mdc` → `rocket-code-patterns-core.mdc` + `rocket-code-patterns-payments.mdc`
- `rocket-error-fixes.mdc` → `rocket-error-fixes-nextjs.mdc` + `rocket-error-fixes-stripe-deploy.mdc`
- `rocket-feature-playbooks.mdc` → `rocket-feature-playbooks-core.mdc` + `rocket-feature-playbooks-advanced.mdc`

Update any references to the old file names.

---

## Instinct System Problems

### Problem: observations.jsonl is empty after sessions
Check that `session-learning.sh` is executable and in hooks.json.
The hook only writes when files were edited (`FILES_EDITED > 0`).
View sessions that ran: `ls .cursor/sessions/`

### Problem: /instinct-status shows no instincts
Instincts are created by `/reflect` or `/learn-eval` — they don't write themselves.
Run one of these after a session where something interesting happened.
`observations.jsonl` is the raw data; instincts are extracted from it manually.

---

## General Cursor Problems

### Problem: Changes keep reverting silently (Zombie Revert)
Three confirmed causes in Cursor March 2026:
1. **Agent Review Tab conflict** → Close the Agent Review Tab (X button) before applying fixes
2. **Cloud sync conflict** → Exclude project from iCloud/Dropbox sync
3. **Format On Save** → Settings → Editor → Format On Save → OFF

After applying a fix: run `git diff` to confirm the change actually persisted.

### Problem: Cursor replaces code with `// ... existing code ...` (Lazy Delete)
This is a confirmed Cursor bug. The diff deletes your actual code.
**Always reject diffs containing this pattern.**
```bash
grep -r "\.\.\. existing code\|// \.\.\. rest\|# \.\.\. existing" .
```
If found: reject the diff, start fresh chat, use tighter scope constraints.

### Problem: Agent keeps modifying files outside the task scope
Add explicit scope-lock at the start of your prompt:
"SCOPE LOCK: only touch [file1] and [file2]. Do NOT modify any other file."
Use the relevant slash command (`/fix-auth`, `/fix-database`) — they enforce scope-lock automatically.

---

## First-Time Setup Checklist

```
[ ] Node.js 18+ installed (node --version)
[ ] .cursor/ copied to project root (not a subfolder)
[ ] chmod +x .cursor/hooks-scripts/*.sh
[ ] mcp.json filled with project ref + PAT + Stripe key
[ ] .cursor/mcp.json added to .gitignore
[ ] Cursor reloaded (Cmd+Shift+P → Reload Window)
[ ] MCP shows green: Settings → Tools & MCP
[ ] Test: "Use Supabase MCP to list all tables"
[ ] First command: /audit-codebase
```
