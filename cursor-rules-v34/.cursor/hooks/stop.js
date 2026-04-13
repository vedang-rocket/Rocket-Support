#!/usr/bin/env node
/**
 * stop Hook — runs after every agent response
 * Delegates to session-end.js for transcript parsing.
 * Also checks for console.log in recently modified files.
 */
const { readStdin, hookEnabled } = require('./adapter');
const { execFileSync } = require('child_process');
const path = require('path');

readStdin().then(raw => {
  if (hookEnabled('stop:session-end', ['minimal', 'standard', 'strict'])) {
    try {
      execFileSync('node', [path.join(__dirname, 'session-end.js')], {
        input: raw || '',
        stdio: ['pipe', 'pipe', 'inherit'],
        timeout: 10000,
        cwd: process.cwd(),
      });
    } catch (_) {}
  }
  process.stdout.write(raw || '');
}).catch(() => process.exit(0));
