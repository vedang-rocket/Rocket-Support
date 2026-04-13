#!/usr/bin/env node
/**
 * beforeShellExecution Hook
 * - Blocks dangerous commands (rm -rf, DROP TABLE, DELETE without WHERE)
 * - Blocks dev servers outside tmux (they eat the session log)
 * - Blocks commands containing embedded API secrets
 * - Git push review reminder in strict mode
 *
 * Exit code 2 = hard block (Cursor shows error, does not execute)
 */
const { readStdin, hookEnabled } = require('./adapter');

function splitSegments(cmd) {
  return cmd.split(/\s*(?:&&|\|\||;|\|)\s*/).map(s => s.trim()).filter(Boolean);
}

readStdin().then(raw => {
  try {
    const input = JSON.parse(raw || '{}');
    const cmd = String(input.command || input.args?.command || '');

    // 1. Block dangerous patterns
    if (hookEnabled('pre:shell:block-dangerous', ['minimal', 'standard', 'strict'])) {
      if (/rm\s+-rf\s+[\/~]/.test(cmd)) {
        console.error('[Rocket] BLOCKED: recursive delete from root/home is forbidden');
        process.exit(2);
      }
      if (/DROP\s+(TABLE|DATABASE)/i.test(cmd)) {
        console.error('[Rocket] BLOCKED: DROP TABLE/DATABASE must be run manually in Supabase SQL Editor');
        process.exit(2);
      }
      if (/DELETE\s+FROM\s+\w+\s*(?:;|$)/i.test(cmd) && !/WHERE/i.test(cmd)) {
        console.error('[Rocket] BLOCKED: DELETE without WHERE would wipe entire table. Add a WHERE condition.');
        process.exit(2);
      }
      if (/git\s+push\s+(--force|-f)\b/.test(cmd)) {
        console.error('[Rocket] BLOCKED: force push not allowed. Rewrite history manually if needed.');
        process.exit(2);
      }
      if (/npm\s+publish\b/.test(cmd)) {
        console.error('[Rocket] BLOCKED: npm publish must be run manually.');
        process.exit(2);
      }
      if (/npx\s+prisma\s+db\s+push\s+--force-reset/.test(cmd)) {
        console.error('[Rocket] BLOCKED: --force-reset wipes database. Run manually if intentional.');
        process.exit(2);
      }
    }

    // 2. Block dev servers outside tmux
    if (hookEnabled('pre:shell:dev-server-block', ['standard', 'strict']) && process.platform !== 'win32') {
      const segments = splitSegments(cmd);
      const tmuxLauncher = /^\s*tmux\s+(new|new-session|new-window|split-window)\b/;
      const devPattern = /\b(npm\s+run\s+dev|pnpm(?:\s+run)?\s+dev|yarn\s+dev|bun\s+run\s+dev)\b/;
      const hasBlockedDev = segments.some(s => devPattern.test(s) && !tmuxLauncher.test(s));
      if (hasBlockedDev) {
        console.error('[Rocket] BLOCKED: dev server must run in tmux to preserve logs.');
        console.error('[Rocket] Use: tmux new-session -d -s dev "npm run dev"');
        process.exit(2);
      }
    }

    // 3. Block commands with embedded secrets
    if (hookEnabled('pre:shell:secrets-guard', ['minimal', 'standard', 'strict'])) {
      const secretPatterns = [
        /sk_live_[a-zA-Z0-9]{20,}/,
        /sk_test_[a-zA-Z0-9]{20,}/,
        /sbp_[a-f0-9]{40}/,
        /eyJ[a-zA-Z0-9_-]{50,}\.[a-zA-Z0-9_-]{50,}/,
        /ghp_[a-zA-Z0-9]{36}/,
        /AKIA[A-Z0-9]{16}/,
      ];
      if (secretPatterns.some(p => p.test(cmd))) {
        console.error('[Rocket] BLOCKED: command appears to contain an API key or token.');
        console.error('[Rocket] Use environment variables or .env file instead of embedding secrets in commands.');
        process.exit(2);
      }
    }

    // 4. Cost estimate on git commit or push (standard + strict)
    if (hookEnabled('pre:shell:cost-estimate', ['standard', 'strict'])) {
      if (/\bgit\s+(commit|push)\b/.test(cmd) && !/--no-cost-check/.test(cmd)) {
        try {
          const riskMapPath = path.join(process.cwd(), 'memory-bank', 'risk-map.json');
          const costsPath   = path.join(process.cwd(), 'memory-bank', 'costs.jsonl');
          const configPath  = path.join(process.cwd(), 'cursor.config');

          if (fs.existsSync(configPath) && fs.existsSync(costsPath)) {
            const config  = JSON.parse(fs.readFileSync(configPath, 'utf8'));
            const budget  = config.budget;
            if (budget?.monthly_limit_usd) {
              // Quick check: sum this month's costs from costs.jsonl
              const month   = new Date().toISOString().slice(0, 7); // YYYY-MM
              const lines   = fs.readFileSync(costsPath, 'utf8').split('\n').filter(Boolean);
              let total = 0;
              for (const line of lines) {
                try {
                  const row = JSON.parse(line);
                  if (row.timestamp?.startsWith(month) && row.estimated_cost_usd) {
                    total += Number(row.estimated_cost_usd);
                  }
                } catch (_) {}
              }
              const pct = (total / budget.monthly_limit_usd) * 100;
              if (pct >= budget.warning_threshold_pct) {
                console.error(`[Rocket Budget] ⚠️  Monthly AI costs: $${total.toFixed(2)} / $${budget.monthly_limit_usd} (${Math.round(pct)}% of budget)`);
                console.error(`[Rocket Budget]    Run /budget for details. Pass --no-cost-check to skip this warning.`);
              }
            }
          }
        } catch (_) {}
      }
    }

    // 5. Git push reminder in strict mode
    if (hookEnabled('pre:shell:git-push-reminder', ['strict']) && /\bgit\s+push\b/.test(cmd)) {
      console.error('[Rocket] Review changes before push: git diff origin/main...HEAD');
    }

  } catch (_) {}

  process.stdout.write(raw || '');
}).catch(() => process.exit(0));
