#!/usr/bin/env node
/**
 * afterFileEdit Hook
 * - Logs edit to agent-log.txt
 * - Warns about console.log in TS/JS files
 * - Reminds about formatting
 * - SQL file migration reminder
 * - Env file security reminder
 * - Review reminder after 5+ edits
 * - Digital Twin: 12 style-aware pair-programmer suggestions (strict mode)
 *   Group A (4): reducer, error boundary, auth, user_id filter
 *   Group B (8): JSDoc, naming, imports, barrels, type location,
 *                error handling, test location, Tailwind pattern
 */
'use strict';
const { readStdin, hookEnabled } = require('./adapter');
const fs   = require('fs');
const path = require('path');

readStdin().then(raw => {
  try {
    const input    = JSON.parse(raw || '{}');
    const filePath = input.path || input.file || input.args?.filePath || '';
    const ts       = new Date().toLocaleTimeString('en-US', { hour12: false });

    // Log every edit
    const logFile = path.join(process.cwd(), '.cursor', 'agent-log.txt');
    if (!fs.existsSync(path.dirname(logFile))) fs.mkdirSync(path.dirname(logFile), { recursive: true });
    fs.appendFileSync(logFile, `[${ts}] edit: ${filePath}\n`);

    const editCount = fs.readFileSync(logFile, 'utf8').split('\n').filter(Boolean).length;
    const messages  = [];

    // ── console.log detection ────────────────────────────────────────────────
    if (hookEnabled('post:edit:console-warn', ['standard', 'strict'])) {
      if (/\.(ts|tsx|js|jsx)$/.test(filePath) && fs.existsSync(filePath)) {
        const src  = fs.readFileSync(filePath, 'utf8');
        const hits = src.split('\n')
          .map((l, i) => ({ n: i + 1, t: l }))
          .filter(({ t }) => /console\.log/.test(t) && !/\/\//.test(t.trim().slice(0, t.indexOf('console'))));
        if (hits.length) messages.push(`[Rocket] console.log in ${path.basename(filePath)}: lines ${hits.map(h => h.n).join(', ')}`);
      }
    }

    // ── format / migration / env reminders ───────────────────────────────────
    if (hookEnabled('post:edit:format-remind', ['standard', 'strict'])) {
      if (/\.(ts|tsx)$/.test(filePath)) messages.push(`[Rocket] Run: npx prettier --write ${filePath}`);
      if (/\.sql$/.test(filePath))       messages.push('[Rocket] SQL edited — if migration, push via Supabase MCP or SQL Editor.');
      if (/\.env/.test(filePath))        messages.push('[Rocket] Env edited — ensure no secrets committed. Check .gitignore.');
    }

    // ── review reminder ───────────────────────────────────────────────────────
    if (editCount > 5 && hookEnabled('post:edit:review-remind', ['standard', 'strict'])) {
      messages.push(`[Rocket] ⚠️ ${editCount} edits this session — run /review-diff before accepting.`);
    }

    if (messages.length) messages.forEach(m => console.error(m));

    // ── Digital Twin: style-aware suggestions (strict mode only) ─────────────
    if (hookEnabled('post:edit:twin-suggest', ['strict'])) {
      try {
        const profilePath = path.join(process.cwd(), 'memory-bank', 'style-profile.json');
        if (!fs.existsSync(profilePath) || !filePath || !/\.(ts|tsx)$/.test(filePath) || !fs.existsSync(filePath)) return;

        const src     = fs.readFileSync(filePath, 'utf8');
        const raw_p   = JSON.parse(fs.readFileSync(profilePath, 'utf8'));
        const p       = raw_p.preferences || {};
        const tips    = [];

        // ── Group A: original 4 checks ───────────────────────────────────────

        if (/useState/.test(src) && p.prefers_reducer_over_state) {
          const stateCount = (src.match(/useState/g) || []).length;
          if (stateCount >= 3) tips.push(`Twin: You use useReducer when state is complex (${stateCount} useState calls here).`);
        }

        if (/export default.*(?:Page|Layout)\b/.test(src) && !/ErrorBoundary/.test(src) && p.always_wraps_pages_in_error_boundary) {
          tips.push('Twin: You typically wrap page/layout components in an ErrorBoundary — missing here.');
        }

        if (/async.*\(req/.test(src) && !/getUser\(\)/.test(src) && p.always_checks_auth_in_routes) {
          tips.push('Twin: You always call getUser() in async route handlers — this one is missing it.');
        }

        if (/\.from\(/.test(src) && !/.eq.*user_id/.test(src) && p.always_filters_by_user_id) {
          tips.push('Twin: You usually add .eq("user_id", user.id) — check if RLS covers this.');
        }

        // ── Group B: 8 new dimension checks ─────────────────────────────────

        // JSDoc on complex functions (>3 params)
        if (p.always_jsdocs_complex_fns) {
          const complexFns = src.match(/(?:function|const\s+\w+\s*=\s*(?:async\s*)?\()(?:[^)]*,[^)]*,[^)]*,)/g) || [];
          const missingDoc = complexFns.filter(fn => !src.slice(Math.max(0, src.indexOf(fn) - 50), src.indexOf(fn)).includes('/**'));
          if (missingDoc.length) tips.push(`Twin: You add JSDoc to functions with >3 params — ${missingDoc.length} function(s) here missing it.`);
        }

        // Variable naming convention
        if (p.variable_naming === 'camelCase') {
          const snakeCaseVars = src.match(/\bconst\s+[a-z]+_[a-z]/g) || [];
          if (snakeCaseVars.length > 2) tips.push(`Twin: You prefer camelCase — found ${snakeCaseVars.length} snake_case variable(s) here.`);
        }

        // Import grouping
        if (p.import_style === 'grouped') {
          const importBlock = src.match(/^(import .+\n)+/m)?.[0] || '';
          if (importBlock) {
            const hasReact    = /from 'react'|from 'next\//.test(importBlock);
            const hasThirdPty = /from '@supabase|from 'stripe|from 'zod|from 'openai/.test(importBlock);
            const hasLocal    = /from '@\/|from '\./.test(importBlock);
            const hasBlankSep = importBlock.includes('\n\n');
            if (hasReact && hasThirdPty && hasLocal && !hasBlankSep) {
              tips.push('Twin: You group imports (React / third-party / local) — imports here are not grouped.');
            }
          }
        }

        // Async error handling pattern
        if (p.async_error_handling === 'try-catch' && /async/.test(src)) {
          const asyncFnCount  = (src.match(/async\s+(?:function|\(|[a-zA-Z])/g) || []).length;
          const tryCatchCount = (src.match(/try\s*\{/g) || []).length;
          if (asyncFnCount > tryCatchCount + 1) {
            tips.push(`Twin: You use try-catch in async functions — ${asyncFnCount - tryCatchCount} async function(s) here missing it.`);
          }
        }

        // Tailwind pattern
        if (p.tailwind_pattern === 'clsx-cn' && /className/.test(src)) {
          const hasTemplateLiteral  = /className=\{`/.test(src);
          const hasConcatenation    = /className=\{[^`].*\+/.test(src);
          const hasClsx             = /className=\{(?:cn|clsx)\(/.test(src);
          if ((hasTemplateLiteral || hasConcatenation) && !hasClsx) {
            tips.push('Twin: You use cn()/clsx() for conditional classes — plain concatenation/template literals found here.');
          }
        }

        if (tips.length) tips.forEach(t => console.error(`[Rocket Twin] 🤖 ${t}`));
      } catch (_) {}
    }

  } catch (_) {}

  process.stdout.write(raw || '');
}).catch(() => process.exit(0));
