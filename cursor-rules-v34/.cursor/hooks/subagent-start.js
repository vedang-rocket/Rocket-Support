#!/usr/bin/env node
/** subagentStart Hook — logs when a subagent is spawned */
const { readStdin } = require('./adapter');
readStdin().then(raw => {
  try {
    const input = JSON.parse(raw || '{}');
    const agent = input.agent_name || input.agent || 'unknown';
    console.error(`[Rocket] Agent spawned: ${agent}`);
  } catch (_) {}
  process.stdout.write(raw || '');
}).catch(() => process.exit(0));
