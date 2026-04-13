# How to Install — Rocket Cursor Rules V34

This guide is written simply. Follow it step by step and you'll be set up in under 5 minutes.

---

## What You're Installing

A folder called `.cursor/` that you drop into any Rocket.new project. It teaches Cursor:
- The exact patterns Rocket uses (Supabase, Next.js, Stripe)
- What mistakes to never make (like `getSession()` instead of `getUser()`)
- How to fix common issues automatically
- How to learn from every session and get smarter over time

---

## Before You Start — One-Time Check

You only need to do this once, ever.

Open your Mac terminal and run:
```bash
node --version
```

If it shows `v18.x.x` or higher — you're good, skip to the next section.

If it says "command not found" or shows a version below 18:
```bash
brew install node
```

That's the only thing you need installed globally.

---

## Setting Up a New Project

Do this every time you receive a Rocket project to fix.

### Step 1 — Unzip and copy the files

Unzip this download. You'll get a folder called `cursor-rules-v20`.

Copy these 5 things into the **root of the Rocket project** (same level as `package.json`):

```
your-rocket-project/
├── package.json          ← already exists in the project
├── .cursor/              ← copy this from cursor-rules-v20
├── memory-bank/          ← copy this from cursor-rules-v20
├── AGENTS.md             ← copy this from cursor-rules-v20
├── cursor.config         ← copy this from cursor-rules-v20
└── .cursorignore         ← copy this from cursor-rules-v20
```

### Step 2 — Open the project in Cursor

File → Open Folder → select the project root (where package.json lives).

**Important:** Open the project root, not a subfolder.

### Step 3 — Fill in the MCP credentials

MCP is the live connection to the project's Supabase database. Without it, Cursor has to guess what's in the database. With it, Cursor can check the actual live data.

Open `.cursor/mcp.json` in any text editor. You'll see two placeholder values to replace:

```json
"--project-ref", "REPLACE_WITH_PROJECT_REF"
"SUPABASE_ACCESS_TOKEN": "REPLACE_WITH_SUPABASE_PAT"
```

**How to get the project ref:**
Look at the Supabase URL in the project's `.env` file:
```
NEXT_PUBLIC_SUPABASE_URL=https://abcdefghijkl.supabase.co
```
The part before `.supabase.co` is your project ref — in this example it's `abcdefghijkl`.

**How to get your Supabase Personal Access Token (PAT):**
1. Go to: https://supabase.com/dashboard/account/tokens
2. Click "Generate new token"
3. Name it "Cursor MCP"
4. Copy the long code starting with `sbp_...`

This token is **yours** — not the project's. You generate it once and reuse it on every project.

**If the project uses Stripe**, also fill in:
```json
"STRIPE_SECRET_KEY": "REPLACE_WITH_STRIPE_SECRET_KEY"
```
Find the Stripe secret key in the project's `.env` file — it starts with `sk_test_` or `sk_live_`.

**If the project does NOT use Stripe**, just delete the entire stripe section from mcp.json.

⚠️ **Important:** Add `.cursor/mcp.json` to the project's `.gitignore` — it contains real API credentials that should never be committed to git.

```bash
echo ".cursor/mcp.json" >> .gitignore
```

### Step 4 — Restart Cursor

Press `Cmd+Shift+P` and type "Reload Window", then press Enter.

Wait about 15 seconds.

### Step 5 — Check MCP is connected

Go to: **Cursor Settings → Tools & MCP**

You should see:
- `supabase` with a **green dot** ✅
- `memory` with a **green dot** ✅
- `stripe` with a green dot (if you filled in the Stripe key) ✅

**If supabase shows red**, go to TROUBLESHOOTING.md — it has step-by-step fixes for every common error.

### Step 6 — Verify everything works

Type this in Cursor chat:
```
Use Supabase MCP to list all tables in this project.
```

If Cursor responds with a real list of table names from the database — everything is working perfectly.

If it gives a generic answer without actual table names — MCP isn't connected. Run `/check-mcp` in Cursor chat and it will diagnose the problem.

---

## Your First Session on a New Project

Always follow this order when you open a project for the first time:

```
1. /check-mcp              — make sure the live database connection works
2. /audit-codebase         — scan the whole project for problems (never skip this)
3. /index-components       — build components.json from your component library
4. /learn-test-patterns    — index existing tests so /generate-tests matches your style
5. /learn-style            — build the digital twin style profile from your recent edits
6. /make-legible           — only needed if the project has messy/unlabeled files
7. the fix command         — /fix-auth, /fix-database, /fix-stripe, etc.
8. /review-diff            — check every change before accepting it
9. /reflect                — at the end, save what you learned
```

Steps 3–5 are **one-time setup** per project — they populate the intelligence files that
power feature generation, test generation, and pair-programming suggestions. They take
about 30 seconds each and run silently in the background.

After the first session, these files are refreshed automatically every week by background
automations (`index-components`, `learn-test-patterns`). You only need to run them manually
after a large refactor that significantly changes your component library or test structure.

---

## Switching to a Different Project

When you move from one project to another:

1. Open `.cursor/mcp.json`
2. Change the `project-ref` to the new project's ref
3. Change the `SUPABASE_ACCESS_TOKEN` if you've generated a new one (usually stays the same)
4. Change `STRIPE_SECRET_KEY` to the new project's key (or remove it if no Stripe)
5. Press `Cmd+Shift+P → Reload Window`
6. Run `/audit-codebase`

That's it. The entire `.cursor/` folder moves with you.

---

## Keeping Credentials Safe

Two rules:

**Rule 1:** `.cursor/mcp.json` always goes in `.gitignore`. It has real API keys in it.

**Rule 2:** Never paste API keys into the Cursor chat. The `beforeSubmitPrompt` hook will warn you if you accidentally do this, but better to never do it in the first place.

---

## What the Hooks Do Automatically

Once installed, these things happen in the background without you doing anything:

| When | What happens automatically |
|---|---|
| You open Cursor on a project | Previous session summary loads into context |
| You make edits | `console.log` statements get flagged with line numbers |
| You run a terminal command | Dangerous commands get blocked before executing |
| You send a message to Cursor | Scanned for accidentally included API keys |
| After each response | Session transcript parsed, cost written to memory-bank/costs.jsonl |
| Before auto-compaction | A marker is saved so you can see where context was summarized |

---

## Troubleshooting

**MCP not connecting?** → See `TROUBLESHOOTING.md` → MCP Problems section

**Hooks not running?** → Make sure you opened the project ROOT in Cursor (not a subfolder)

**Commands like /fix-auth not working?** → Make sure `.cursor/` is at the project root (not inside a `cursor-rules-v20/` subfolder)

**Everything broken after switching projects?** → Update mcp.json credentials → Reload Window → run `/check-mcp`

For anything else: `TROUBLESHOOTING.md` has solutions for 20+ common problems.
