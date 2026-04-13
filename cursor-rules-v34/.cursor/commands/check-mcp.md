# Purpose: Diagnose MCP server connection status — run this if MCP tools aren't working

MCP servers fail silently. No error, no warning — tools just don't appear.
This command surfaces exactly what's broken and how to fix it.

## Step 1 — Check if MCP servers are listed in Cursor

```
Open Cursor → Settings → Tools & MCP
You should see: supabase, stripe, memory

Green dot = connected ✅
Red dot or missing = not connected ❌
```

If all three show green → MCP is working. Type a test query:
```
Use Supabase MCP to list all tables in this database.
```
If that works, you're done. If not, continue below.

---

## Step 2 — Verify mcp.json format is correct

The most common cause of Supabase MCP failure is wrong argument format.

**Correct format** (V19):
```json
{
  "mcpServers": {
    "supabase": {
      "command": "npx",
      "args": [
        "-y", "@supabase/mcp-server-supabase@latest",
        "--project-ref", "YOUR_PROJECT_REF",
        "--read-only"
      ],
      "env": { "SUPABASE_ACCESS_TOKEN": "sbp_YOUR_PAT" }
    }
  }
}
```

**Wrong formats that cause silent failure:**
- `--supabase-url` → `ERR_PARSE_ARGS_UNKNOWN_OPTION` (old V18 format, broken)
- `--supabase-service-role-key` → same error (wrong credential type)
- PAT as CLI arg instead of env block → credentials not loaded
- Service role key instead of Personal Access Token → wrong auth

**Get your project ref:** From your Supabase URL: `https://[PROJECT_REF].supabase.co`
**Get your PAT:** https://supabase.com/dashboard/account/tokens → Generate new token

---

## Step 3 — Test Supabase MCP manually in terminal

```bash
# Replace with your actual values
SUPABASE_ACCESS_TOKEN="sbp_your_pat_here" \
  npx -y @supabase/mcp-server-supabase@latest \
  --project-ref "your_project_ref" \
  --read-only &

MCP_PID=$!
sleep 5

if kill -0 $MCP_PID 2>/dev/null; then
  echo "✅ Supabase MCP started successfully"
  kill $MCP_PID
else
  echo "❌ Supabase MCP failed — check project ref and PAT"
fi
```

---

## Step 4 — Test Stripe MCP manually

```bash
# Check Stripe key exists in .env
grep "STRIPE_SECRET_KEY" .env 2>/dev/null || grep "STRIPE_SECRET_KEY" .env.local 2>/dev/null
# Should show: STRIPE_SECRET_KEY=sk_test_... or sk_live_...

# Key must start with sk_test_ or sk_live_ — never pk_test_
```

If this project has no Stripe, remove the stripe section from mcp.json entirely.

---

## Step 5 — Check Node.js version

```bash
node --version
# Must be 18.0.0 or higher
# If lower: brew upgrade node
```

---

## Step 6 — Check env file has required variables

```bash
echo "=== MCP Credential Check ==="
# Check .env (Rocket standard) or .env.local (Next.js standard)
ENV_FILE=".env"
[ -f ".env.local" ] && ENV_FILE=".env.local"
echo "Using: $ENV_FILE"

for var in NEXT_PUBLIC_SUPABASE_URL STRIPE_SECRET_KEY; do
  val=$(grep "^$var=" "$ENV_FILE" 2>/dev/null | cut -d'=' -f2-)
  if [ -n "$val" ]; then
    echo "✅ $var = ${val:0:20}..."
  else
    echo "❌ $var = MISSING from $ENV_FILE"
  fi
done

echo ""
echo "NOTE: SUPABASE_ACCESS_TOKEN (your PAT) goes in mcp.json env block directly,"
echo "not in your .env file. Get it from supabase.com/dashboard/account/tokens"
```

---

## Step 7 — Force Cursor to reload MCP servers

```
Cursor → Command Palette (Cmd+Shift+P) → "Reload Window"
Wait 15–20 seconds for MCP servers to connect
Then check Settings → Tools & MCP again
```

---

## Common Failure Causes and Fixes

| Symptom | Cause | Fix |
|---|---|---|
| Server not listed in Cursor | `mcp.json` not at `.cursor/mcp.json` | Confirm file location at project root |
| Red dot + `ERR_PARSE_ARGS` | Old `--supabase-url` format | Use `--project-ref` + env block (see Step 2) |
| Red dot + "Connection closed" | Wrong credentials format | PAT in env block, project-ref in args |
| Red dot + "spawn error" | Node.js not on PATH | `brew install node` |
| Green dot but no tables found | Wrong project-ref | Must match YOUR_REF in supabase.co URL |
| Stripe `Invalid tool` error | Old `--tools` flag in mcp.json | Remove `--tools=...` from Stripe args entirely |
| Memory `ETARGET` error | Bad version pin | Remove version pin, use `@modelcontextprotocol/server-memory` |
| All green but tools missing | Over 40 MCP tools total | Remove servers you don't need |

---

## Nuclear Reset

```bash
# Clear npx cache and force fresh downloads
rm -rf ~/.npm/_npx

# Reload Cursor
# Cmd+Shift+P → "Reload Window"
```

After reload, wait 30 seconds and check Settings → Tools & MCP again.
