# What's New in V34

V34 polishes the three rough edges identified in the V33 expert review —
zero-friction first use, a richer digital twin, and more precise cost detection.

---

## Fix 1 — Zero Friction on First Use

**Updated: `INSTALL.md`** — fixed stale V20 title, added steps 3–5 to the first-session workflow

The first-session workflow now includes three one-time setup steps:

```
3. /index-components       — build components.json from your component library
4. /learn-test-patterns    — index existing tests so /generate-tests matches your style
5. /learn-style            — build the digital twin style profile from your recent edits
```

These run once, take ~30 seconds each, and are refreshed automatically by weekly automations
after that. The instruction block explains this is a one-time setup, not a regular ritual.

**Updated: `agents/feature-generator.md`** — fallback when components.json is empty

Instead of silently using no context, the agent now explicitly notes:
"components.json not yet populated — run /index-components after setup to enable component reuse"
and proceeds with generation anyway. The feature generates immediately; you can refactor
to reuse components after indexing.

**Updated: `agents/test-generator.md`** — complete default mock pattern when test-patterns.json is missing

Rather than "use Rocket defaults (shown below)" with no actual defaults, the fallback now
includes the full working mock pattern:

```typescript
vi.mock('@/lib/supabase/server', () => ({
  createClient: vi.fn().mockResolvedValue({
    auth: { getUser: vi.fn().mockResolvedValue({ data: { user: { id: 'test-user-id' } }, error: null }) },
    from: vi.fn().mockReturnThis(), select: vi.fn().mockReturnThis(),
    eq: vi.fn().mockReturnThis(), single: vi.fn().mockResolvedValue({ data: null, error: null }),
  }),
}))
```

Generated tests using the default pattern include a comment at the top:
`// ⚠️ Using Rocket default patterns. Run /learn-test-patterns to match your existing test style.`

---

## Fix 2 — Richer Digital Twin (8 new style dimensions)

**Updated: `agents/digital-twin.md`** — expanded from 10 to 18 style dimensions

**Updated: `memory-bank/style-profile.json`** — schema updated with 8 new fields

**Updated: `.cursor/hooks/after-file-edit.js`** — 5 new twin suggestion checks (12 total)

The 8 new dimensions:

| Dimension | What it detects | Example suggestion |
|---|---|---|
| `comment_style` | `//` vs `/* */` vs `/** JSDoc */` dominance | — |
| `always_jsdocs_complex_fns` | JSDoc on functions with >3 params | "You add JSDoc to functions with >3 params — 2 functions here missing it." |
| `variable_naming` | camelCase vs snake_case in const declarations | "You prefer camelCase — found 3 snake_case variables here." |
| `import_style` | grouped (React/third-party/local separated by blank lines) vs flat | "You group imports by type — imports here are not grouped." |
| `uses_barrel_exports` | index.ts re-exports in component folders | — |
| `type_location` | inline / colocated / centralized TypeScript types | — |
| `async_error_handling` | try-catch vs .catch() vs error boundary | "You use try-catch in async functions — 2 async functions here missing it." |
| `tailwind_pattern` | cn()/clsx() vs template literals vs concatenation | "You use cn()/clsx() for conditional classes — plain concatenation found here." |

The hook's twin suggestion block now has 12 checks: the original 4 (reducer, error boundary,
auth, user_id filter) plus 5 of the new 8 that lend themselves to inline detection
(JSDoc, naming, imports, async error handling, Tailwind pattern).

---

## Fix 3 — Expanded Cost-Alert Heuristics (7 new patterns, 12 total)

**Updated: `.cursor/skills/estimate-cost/SKILL.md`** — 12 cost-impacting patterns in 3 groups

**Updated: `.cursor/commands/budget.md`** — dashboard now shows new cost categories

### 7 new patterns added

| Pattern | Detection | Typical impact |
|---|---|---|
| Model upgrade | `gpt-4o` replacing `gpt-4o-mini` in diff | +3–10× per call — flagged as HIGH |
| New embedding call | `embeddings.create` / `generateEmbedding` | +$0.02/1M tokens |
| New Realtime channel | `.channel(` subscription added | +1 connection/active user |
| New Storage upload | `.storage.` + `.upload(` | +$0.021/GB/month + egress |
| New auth signup path | `auth.signUp` in public route | potential MAU tier change |
| Large batch upsert | `.upsert([` with >100-item literal | write amplification warning |
| New Cron job | `cron.schedule(` in SQL/CLI | fixed invocations warning |

The report output now includes a Recommendation section for over-budget scenarios
(e.g., "The model upgrade from gpt-4o-mini to gpt-4o will push costs 38% over budget.
Consider keeping gpt-4o-mini for most calls, using gpt-4o only for complex tasks.")

The `/budget` dashboard example now includes: Edge Function calls, Realtime connections,
Storage + egress, and Auth MAU as separate line items in both the cost summary and
the top cost sources list.

---

## Counts

| | V33 | V34 |
|---|---|---|
| Rules | 61 | 61 |
| Hook JS | 17 | 17 (after-file-edit.js significantly enhanced) |
| Agents | 11 | 11 (digital-twin.md significantly enhanced) |
| Skills | 15 | 15 (estimate-cost/SKILL.md significantly enhanced) |
| Commands | 40 | 40 (budget.md updated) |
| Total files | 198 | 198 |
