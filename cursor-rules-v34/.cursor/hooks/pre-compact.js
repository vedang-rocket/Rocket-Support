#!/usr/bin/env node
/**
 * preCompact Hook
 * Saves a marker to the session log BEFORE context compaction.
 * Ensures you can see where compaction happened in the session history.
 */
const { readStdin } = require('./adapter');
const fs = require('fs');
const path = require('path');

readStdin().then(raw => {
  try {
    const sessionsDir = path.join(process.cwd(), '.cursor', 'sessions');
    if (!fs.existsSync(sessionsDir)) fs.mkdirSync(sessionsDir, { recursive: true });

    const today = new Date().toISOString().slice(0, 10);
    const timeStr = new Date().toLocaleTimeString('en-US', { hour12: false });
    const sessionFile = path.join(sessionsDir, `${today}.log`);
    fs.appendFileSync(sessionFile, `\n[${timeStr}] ⚡ Context compaction triggered — state above this line is summarized\n`);

    console.error('[Rocket] State saved before context compaction.');
  } catch (_) {}
  process.stdout.write(raw || '');
}).catch(() => process.exit(0));
