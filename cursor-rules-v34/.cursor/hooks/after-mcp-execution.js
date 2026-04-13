#!/usr/bin/env node
/**
 * afterMCPExecution Hook
 * Logs MCP tool results for audit trail.
 */
const { readStdin } = require('./adapter');
const fs = require('fs');
const path = require('path');

readStdin().then(raw => {
  try {
    const input = JSON.parse(raw || '{}');
    const server = input.server || input.mcp_server || 'unknown';
    const tool = input.tool || input.mcp_tool || 'unknown';
    const status = input.error ? 'FAILED' : 'OK';
    const timestamp = new Date().toISOString();
    const logFile = path.join(process.cwd(), '.cursor', 'mcp-audit.log');
    fs.appendFileSync(logFile, `[${timestamp}] RESULT: ${server}/${tool} -> ${status}\n`);
  } catch (_) {}
  process.stdout.write(raw || '');
}).catch(() => process.exit(0));
