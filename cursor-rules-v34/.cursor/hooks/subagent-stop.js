#!/usr/bin/env node
/** subagentStop Hook — logs when a subagent completes */
const { readStdin } = require('./adapter');
readStdin().then(raw => {
  try {
    const input = JSON.parse(raw || '{}');
    const agent = input.agent_name || input.agent || 'unknown';
    console.error(`[Rocket] Agent completed: ${agent}`);
  } catch (_) {}
  process.stdout.write(raw || '');
}).catch(() => process.exit(0));
