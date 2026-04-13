#!/usr/bin/env node
/**
 * beforeTabFileRead Hook
 * Blocks Cursor's Tab feature from reading sensitive files.
 * Exit code 2 = hard block.
 */
const { readStdin } = require('./adapter');

readStdin().then(raw => {
  try {
    const input = JSON.parse(raw || '{}');
    const filePath = input.path || input.file || '';
    if (/\.(env|key|pem)$|\.env\.|credentials|secret/i.test(filePath)) {
      console.error('[Rocket] BLOCKED: Tab cannot read sensitive file: ' + filePath);
      process.exit(2);
    }
  } catch (_) {}
  process.stdout.write(raw || '');
}).catch(() => process.exit(0));
