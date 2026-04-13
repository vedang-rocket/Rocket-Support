#!/usr/bin/env node
/**
 * beforeSubmitPrompt Hook
 * Detects secrets in prompts BEFORE they are sent to the AI.
 * Warns but does not block (user may be intentionally sharing for debugging).
 */
const { readStdin } = require('./adapter');

readStdin().then(raw => {
  try {
    const input = JSON.parse(raw || '{}');
    const prompt = input.prompt || input.content || input.message || '';
    const secretPatterns = [
      { pattern: /sk-[a-zA-Z0-9]{20,}/, label: 'OpenAI API key' },
      { pattern: /sk_live_[a-zA-Z0-9]{20,}/, label: 'Stripe live secret key' },
      { pattern: /sk_test_[a-zA-Z0-9]{20,}/, label: 'Stripe test secret key' },
      { pattern: /sbp_[a-f0-9]{40}/, label: 'Supabase PAT' },
      { pattern: /ghp_[a-zA-Z0-9]{36,}/, label: 'GitHub PAT' },
      { pattern: /AKIA[A-Z0-9]{16}/, label: 'AWS access key' },
      { pattern: /xox[bpsa]-[a-zA-Z0-9-]+/, label: 'Slack token' },
      { pattern: /-----BEGIN (RSA |EC )?PRIVATE KEY-----/, label: 'private key' },
    ];
    for (const { pattern, label } of secretPatterns) {
      if (pattern.test(prompt)) {
        console.error(`[Rocket] WARNING: Potential ${label} detected in prompt!`);
        console.error('[Rocket] Remove secrets before submitting. Use environment variables instead.');
        break;
      }
    }
  } catch (_) {}
  process.stdout.write(raw || '');
}).catch(() => process.exit(0));
