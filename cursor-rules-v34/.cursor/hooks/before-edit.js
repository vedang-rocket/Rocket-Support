#!/usr/bin/env node
/**
 * beforeEdit Hook — Risk-aware file edit warning
 *
 * When a file is about to be edited, checks memory-bank/risk-map.json.
 * If the file has a HIGH risk score, injects a warning into the context.
 *
 * Cursor hook event: beforeFileEdit (fires before an edit is written)
 * Note: if Cursor exposes beforeEdit as a distinct event, wire it in hooks.json.
 * Currently this supplements afterFileEdit for risk-based context injection.
 *
 * Exit 0 always — never blocks edits. Warns only.
 */
'use strict';
const { readStdin, hookEnabled } = require('./adapter');
const fs   = require('fs');
const path = require('path');

readStdin().then(raw => {
  try {
    if (!hookEnabled('pre:edit:risk-warn', ['standard', 'strict'])) {
      process.stdout.write(raw || '');
      return;
    }

    const input    = JSON.parse(raw || '{}');
    const filePath = input.path || input.file || input.args?.filePath || '';
    if (!filePath) { process.stdout.write(raw || ''); return; }

    const riskMapPath = path.join(process.cwd(), 'memory-bank', 'risk-map.json');
    if (!fs.existsSync(riskMapPath)) { process.stdout.write(raw || ''); return; }

    const riskMap = JSON.parse(fs.readFileSync(riskMapPath, 'utf8'));
    const relPath = path.relative(process.cwd(), path.resolve(filePath));

    // Find the file in the risk map (match by suffix to handle relative/absolute variants)
    const entry = (riskMap.files || []).find(f =>
      relPath.endsWith(f.path) || f.path.endsWith(relPath)
    );

    if (!entry || entry.risk_level !== 'high') {
      process.stdout.write(raw || '');
      return;
    }

    // Build contextual warning based on dominant pattern
    const patternMessages = {
      'bug-history':    `This file has ${entry.factors?.past_bug_count ?? 'multiple'} recorded bug(s) in fixes-applied.md. Review existing logic before adding new code.`,
      'high-churn':     `This file changes frequently (${entry.factors?.change_frequency ?? 'often'} commits). High churn = high coupling risk. Add tests before modifying.`,
      'complex-logic':  `High conditional density detected. Trace every code path carefully. Consider extracting logic into named helper functions.`,
      'async-heavy':    `Contains ${entry.factors?.useEffect_count ?? 'multiple'} useEffect(s) and nested async calls. Watch for race conditions and stale closures.`,
      'type-unsafe':    `Contains ${entry.factors?.any_casts ?? 'multiple'} 'as any' casts — TypeScript safety is bypassed. Validate types before trusting this data.`,
    };

    const detail = patternMessages[entry.dominant_pattern]
      || entry.warning
      || 'Review carefully before editing.';

    const warning = [
      `[Rocket Risk] ⚠️  HIGH RISK FILE (score: ${entry.risk_score}/100)`,
      `  Pattern: ${entry.dominant_pattern}`,
      `  ${detail}`,
      `  Run /risk-scan to refresh the risk map.`,
    ].join('\n');

    console.error(warning);

  } catch (_) {}

  process.stdout.write(raw || '');
}).catch(() => process.exit(0));
