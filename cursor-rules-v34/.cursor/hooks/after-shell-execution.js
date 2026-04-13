#!/usr/bin/env node
/**
 * afterShellExecution Hook
 * - Captures PR URL after gh pr create
 * - Notifies on build completion
 */
const { readStdin, hookEnabled } = require('./adapter');

readStdin().then(raw => {
  try {
    const input = JSON.parse(raw || '{}');
    const cmd = String(input.command || input.args?.command || '');
    const output = String(input.output || input.result || '');

    if (hookEnabled('post:shell:pr-created', ['standard', 'strict']) && /\bgh\s+pr\s+create\b/.test(cmd)) {
      const m = output.match(/https:\/\/github\.com\/[^/]+\/[^/]+\/pull\/\d+/);
      if (m) {
        console.error('[Rocket] PR created: ' + m[0]);
        const pr = m[0].replace(/.+\/pull\/(\d+)/, '$1');
        console.error('[Rocket] To review: gh pr view ' + pr + ' --web');
      }
    }

    if (hookEnabled('post:shell:build-complete', ['standard', 'strict']) && /(npm run build|pnpm build|yarn build|next build)/.test(cmd)) {
      const success = !/error/i.test(output.slice(-200));
      console.error(success ? '[Rocket] Build completed ✅' : '[Rocket] Build completed with errors ❌');
    }
  } catch (_) {}
  process.stdout.write(raw || '');
}).catch(() => process.exit(0));
