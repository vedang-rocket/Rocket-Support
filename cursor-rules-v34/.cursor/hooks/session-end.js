#!/usr/bin/env node
/**
 * sessionEnd Hook
 * Parses the actual JSONL transcript to extract user messages,
 * tools used, and files modified. Writes structured session summary.
 * Also writes cost estimate to memory-bank/costs.jsonl.
 */
const { readStdin, hookEnabled } = require('./adapter');
const fs = require('fs');
const path = require('path');

function extractSessionSummary(transcriptPath) {
  if (!transcriptPath || !fs.existsSync(transcriptPath)) return null;

  const content = fs.readFileSync(transcriptPath, 'utf8');
  const lines = content.split('\n').filter(Boolean);
  const userMessages = [];
  const toolsUsed = new Set();
  const filesModified = new Set();

  for (const line of lines) {
    try {
      const entry = JSON.parse(line);

      // Collect user messages
      const rawContent = entry.message?.content ?? entry.content;
      if (entry.type === 'user' || entry.role === 'user' || entry.message?.role === 'user') {
        const text = typeof rawContent === 'string'
          ? rawContent
          : Array.isArray(rawContent)
            ? rawContent.map(c => c?.text || '').join(' ')
            : '';
        if (text.trim()) userMessages.push(text.trim().slice(0, 200));
      }

      // Collect tool use from direct entries
      if (entry.type === 'tool_use' || entry.tool_name) {
        const toolName = entry.tool_name || entry.name || '';
        if (toolName) toolsUsed.add(toolName);
        const filePath = entry.tool_input?.file_path || entry.input?.file_path || '';
        if (filePath && (toolName === 'Edit' || toolName === 'Write')) filesModified.add(filePath);
      }

      // Collect tool use from assistant message blocks (Claude Code JSONL)
      if (entry.type === 'assistant' && Array.isArray(entry.message?.content)) {
        for (const block of entry.message.content) {
          if (block.type === 'tool_use') {
            const toolName = block.name || '';
            if (toolName) toolsUsed.add(toolName);
            const filePath = block.input?.file_path || '';
            if (filePath && (toolName === 'Edit' || toolName === 'Write')) filesModified.add(filePath);
          }
        }
      }
    } catch (_) {}
  }

  if (userMessages.length === 0) return null;
  return {
    userMessages: userMessages.slice(-10),
    toolsUsed: Array.from(toolsUsed).slice(0, 20),
    filesModified: Array.from(filesModified).slice(0, 30),
    totalMessages: userMessages.length,
  };
}

function estimateCost(model, inputTokens, outputTokens) {
  const rates = {
    haiku: { in: 0.8, out: 4.0 },
    sonnet: { in: 3.0, out: 15.0 },
    opus: { in: 15.0, out: 75.0 },
    composer: { in: 1.5, out: 7.5 },
  };
  const m = String(model || '').toLowerCase();
  let r = rates.sonnet;
  if (m.includes('haiku')) r = rates.haiku;
  if (m.includes('opus')) r = rates.opus;
  if (m.includes('composer') || m.includes('cursor')) r = rates.composer;
  return Math.round(((inputTokens / 1e6) * r.in + (outputTokens / 1e6) * r.out) * 1e6) / 1e6;
}

readStdin().then(raw => {
  if (!hookEnabled('stop:session-end', ['minimal', 'standard', 'strict'])) {
    process.stdout.write(raw || '');
    process.exit(0);
  }

  try {
    const input = JSON.parse(raw || '{}');
    const transcriptPath = input.transcript_path;
    const model = input.model || input._cursor?.model || 'unknown';
    const usage = input.usage || input.token_usage || {};
    const inputTokens = Number(usage.input_tokens || usage.prompt_tokens || 0);
    const outputTokens = Number(usage.output_tokens || usage.completion_tokens || 0);

    const sessionsDir = path.join(process.cwd(), '.cursor', 'sessions');
    if (!fs.existsSync(sessionsDir)) fs.mkdirSync(sessionsDir, { recursive: true });

    const today = new Date().toISOString().slice(0, 10);
    const timeStr = new Date().toLocaleTimeString('en-US', { hour12: false });
    const sessionFile = path.join(sessionsDir, `${today}.log`);

    // Extract summary from transcript
    const summary = extractSessionSummary(transcriptPath);

    let entry = `\n--- ${today} ${timeStr} ---\n`;
    if (summary) {
      entry += `Tasks (${summary.totalMessages} messages):\n`;
      summary.userMessages.forEach(m => { entry += `  - ${m.replace(/\n/g, ' ')}\n`; });
      if (summary.filesModified.length > 0) {
        entry += `Files modified: ${summary.filesModified.slice(0, 8).join(', ')}\n`;
      }
      if (summary.toolsUsed.length > 0) {
        entry += `Tools: ${summary.toolsUsed.slice(0, 10).join(', ')}\n`;
      }
    }
    entry += `Model: ${model}\n`;

    fs.appendFileSync(sessionFile, entry);

    // Write cost estimate to memory-bank
    if (inputTokens > 0 || outputTokens > 0) {
      const memBankDir = path.join(process.cwd(), 'memory-bank');
      if (!fs.existsSync(memBankDir)) fs.mkdirSync(memBankDir, { recursive: true });
      const costsFile = path.join(memBankDir, 'costs.jsonl');
      const row = {
        timestamp: new Date().toISOString(),
        model,
        input_tokens: inputTokens,
        output_tokens: outputTokens,
        estimated_cost_usd: estimateCost(model, inputTokens, outputTokens),
      };
      fs.appendFileSync(costsFile, JSON.stringify(row) + '\n');
    }

    // Observation for instinct system
    const obsFile = path.join(process.cwd(), 'memory-bank', 'observations.jsonl');
    const obs = {
      timestamp: new Date().toISOString(),
      event: 'session_end',
      files_modified: summary?.filesModified?.length || 0,
      tools_used: summary?.toolsUsed || [],
      message_count: summary?.totalMessages || 0,
      model,
    };
    fs.appendFileSync(obsFile, JSON.stringify(obs) + '\n');

  } catch (_) {}

  // Auto-promotion: run instinct promoter in background (non-blocking)
  try {
    const { execFile } = require('child_process');
    execFile('node', [path.join(__dirname, 'instinct-promoter.js')], {
      cwd: process.cwd(),
      timeout: 30000,
    }, () => {}); // fire-and-forget — errors are swallowed intentionally
  } catch (_) {}

  process.stdout.write(raw || '');
}).catch(() => process.exit(0));
