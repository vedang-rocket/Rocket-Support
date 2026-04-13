# Purpose: Explicitly route this task to the right model by complexity and budget

## Usage
/model-route [task description]
Example: /model-route fix the Stripe webhook signature error
Example: /model-route refactor the entire auth system across 8 files
Example: /model-route add a simple loading spinner to the dashboard

## What I Will Do

Analyze the task and recommend the optimal model with reasoning.

## Routing Decision Tree

```
1. Is this a single-line completion or variable rename?
   → cursor-small (💚 cheapest)

2. Is this reading/explaining code or a simple lookup?
   → cursor-small or deepseek via OpenRouter (💚 cheapest)

3. Is this a standard agent task (slash command, multi-file fix, plan execution)?
   → cursor-composer (💛 standard — DEFAULT for 90% of tasks)

4. Does this require BOTH auth + payments changes simultaneously?
   → claude-opus (🔴 expensive — only for this specific combination)

5. Does this refactor touch 10+ files with shared interfaces?
   → claude-opus (🔴 expensive)

6. Does this require designing a new DB schema integrating with existing tables?
   → claude-opus (🔴 expensive)

7. Complex TypeScript generics or algorithmic logic?
   → o3-mini (🟠 premium)

8. Everything else that needs reasoning with explanation?
   → claude-sonnet (🟠 premium)
```

## Output Format

```
TASK: [task description]

COMPLEXITY SIGNALS:
  Files affected: [estimate]
  Domains involved: [auth / payments / database / UI / ...]
  Novel architecture needed: [yes/no]
  Explanation required: [yes/no]

RECOMMENDED MODEL: cursor-composer
BUDGET TIER: 💛 Standard
REASON: Multi-file agent task — no deep architectural reasoning needed

⚠️ MAX MODE WARNING: [only shown if recommending Opus/Sonnet in Max Mode]
Estimated tokens: ~[n]K. At Max Mode pricing this costs [estimate].
Confirm before proceeding.

Ready to proceed with cursor-composer? [yes → continue with task]
```
