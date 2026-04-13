#!/usr/bin/env node
/**
 * beforeReadFile Hook
 * Warns (does NOT block) when the agent reads sensitive files.
 * Useful for audit trail — lets you know when .env files are being read.
 */
const { readStdin } = require('./adapter');

readStdin().then(raw => {
  try {
    const input = JSON.parse(raw || '{}');
    const filePath = input.path || input.file || '';
    if (/\.(env|key|pem)$|\.env\.|credentials|secret/i.test(filePath)) {
      console.error('[Rocket] WARNING: Reading sensitive file: ' + filePath);
      console.error('[Rocket] Ensure this data is not exposed in outputs.');
    }
  } catch (_) {}
  process.stdout.write(raw || '');
}).catch(() => process.exit(0));
