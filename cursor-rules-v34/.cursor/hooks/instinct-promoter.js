#!/usr/bin/env node
/**
 * Instinct Auto-Promotion Engine — V32
 *
 * Scans memory-bank/instincts/*.yaml for instincts meeting promotion thresholds:
 *   confidence >= 0.9 AND evidence_count >= 5
 *
 * Pipeline:
 *   1. Scan all instinct files, skip below threshold
 *   2. Conflict detection: pattern vs existing rule content
 *      → conflict  → write to memory-bank/conflicts.md, skip
 *      → no conflict → write draft to memory-bank/promoted-rules/<slug>.draft.md
 *   3. Auto-approve drafts older than AUTO_APPROVE_MS (5 min)
 *      → apply: append section to .cursor/rules/rocket-<domain>-learned.mdc
 *      → log to memory-bank/promotion-log.md
 *
 * Usage:
 *   node .cursor/hooks/instinct-promoter.js           (scan + auto-approve pending)
 *   node .cursor/hooks/instinct-promoter.js --apply <slug>   (force-apply one draft)
 *   node .cursor/hooks/instinct-promoter.js --status         (print pending count)
 */

'use strict';
const fs   = require('fs');
const path = require('path');

const CWD              = process.cwd();
const INSTINCTS_DIR    = path.join(CWD, 'memory-bank', 'instincts');
const PROMOTED_DIR     = path.join(CWD, 'memory-bank', 'promoted-rules');
const CONFLICTS_FILE   = path.join(CWD, 'memory-bank', 'conflicts.md');
const PROMOTION_LOG    = path.join(CWD, 'memory-bank', 'promotion-log.md');
const RULES_DIR        = path.join(CWD, '.cursor', 'rules');

const CONFIDENCE_MIN   = 0.9;
const EVIDENCE_MIN     = 5;
const AUTO_APPROVE_MS  = 5 * 60 * 1000; // 5 minutes

// ── helpers ──────────────────────────────────────────────────────────────────

function ensureDir(d) { if (!fs.existsSync(d)) fs.mkdirSync(d, { recursive: true }); }

/** Parse ---\nkey: val\n--- frontmatter into plain object */
function parseFrontmatter(text) {
  const m = text.match(/^---\r?\n([\s\S]*?)\r?\n---/);
  if (!m) return {};
  const obj = {};
  for (const line of m[1].split(/\r?\n/)) {
    const colon = line.indexOf(':');
    if (colon < 1) continue;
    const k = line.slice(0, colon).trim();
    const v = line.slice(colon + 1).trim().replace(/^["']|["']$/g, '');
    obj[k] = v;
  }
  return obj;
}

/** Everything after the closing --- */
function bodyAfterFrontmatter(text) {
  return text.replace(/^---\r?\n[\s\S]*?\r?\n---\r?\n?/, '').trim();
}

/** slug-safe id */
function toSlug(s) {
  return String(s || 'instinct-' + Date.now())
    .toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
}

/** Load all existing rule file contents keyed by filename */
function loadRules() {
  if (!fs.existsSync(RULES_DIR)) return {};
  return Object.fromEntries(
    fs.readdirSync(RULES_DIR)
      .filter(f => f.endsWith('.mdc'))
      .map(f => [f, fs.readFileSync(path.join(RULES_DIR, f), 'utf8')])
  );
}

// ── conflict detection ────────────────────────────────────────────────────────

/**
 * Returns { conflictingRule: string } or null.
 * Checks three signals:
 *  a) instinct says "never X" but an existing rule says "always X" (or vice-versa)
 *  b) instinct domain matches rule filename and same keyword appears with opposite polarity
 *  c) hardcoded known-bad pairs
 */
function detectConflict(fm, body, rules) {
  const instinctLower = body.toLowerCase();
  const domain        = (fm.domain || '').toLowerCase();

  // Hardcoded contradiction pairs [instinct-pattern, rule-anti-pattern]
  const pairs = [
    [/\bnever\s+use\s+getSession\b/i, /\bgetSession\b.*recommended|use\s+getSession\b/i],
    [/\balways\s+use\s+getUser\b/i,   /\bgetSession\b.*preferred|avoid.*getUser\b/i],
    [/\btransaction\s+mode\b/i,       /\bsession\s+mode.*preferred\b/i],
    [/\bservice_role.*server.only\b/i,/\bNEXT_PUBLIC.*service_role\b/i],
  ];

  for (const [ruleName, ruleContent] of Object.entries(rules)) {
    // Only check domain-relevant rules when domain is set
    if (domain && !ruleName.toLowerCase().includes(domain)) continue;

    for (const [instPat, rulePat] of pairs) {
      if (instPat.test(body) && rulePat.test(ruleContent)) {
        return { conflictingRule: ruleName };
      }
    }

    // Generic: instinct says NEVER <word>, rule says USE/ALWAYS <word>
    const neverMatches = body.match(/\bnever\s+(?:use\s+)?(\w+)/gi) || [];
    for (const nm of neverMatches) {
      const keyword = nm.replace(/\bnever\s+(?:use\s+)?/i, '').trim();
      if (!keyword || keyword.length < 4) continue;
      const antiPat = new RegExp(`\\b(?:use|always|prefer)\\s+${keyword}\\b`, 'i');
      if (antiPat.test(ruleContent)) return { conflictingRule: ruleName, keyword };
    }
  }
  return null;
}

// ── write conflict report ─────────────────────────────────────────────────────

function writeConflict(fm, body, conflict) {
  ensureDir(path.dirname(CONFLICTS_FILE));
  const header = fs.existsSync(CONFLICTS_FILE)
    ? fs.readFileSync(CONFLICTS_FILE, 'utf8')
    : '# Promotion Conflicts\n\nReview and resolve before re-running the promoter.\n';
  const entry = `
## Conflict — ${new Date().toISOString()}

**Instinct**: \`${fm.id || 'unknown'}\`  
**Confidence**: ${fm.confidence} | **Evidence**: ${fm.evidence_count}  
**Conflicts with rule**: \`${conflict.conflictingRule}\`${conflict.keyword ? ` (keyword: \`${conflict.keyword}\`)` : ''}

**Instinct body**:
${body}

**Resolution**: Compare the instinct against \`${conflict.conflictingRule}\`.
- If the instinct is correct: update the rule to match, then delete this entry and re-run the promoter.
- If the rule is correct: delete the instinct YAML file.

---
`;
  fs.writeFileSync(CONFLICTS_FILE, header + entry);
  console.log(`[Promoter] ⚠  Conflict logged → memory-bank/conflicts.md  (${fm.id})`);
}

// ── write draft ───────────────────────────────────────────────────────────────

function writeDraft(fm, body) {
  ensureDir(PROMOTED_DIR);
  const slug      = toSlug(fm.id);
  const draftPath = path.join(PROMOTED_DIR, `${slug}.draft.md`);

  // Don't overwrite a pending draft
  if (fs.existsSync(draftPath)) {
    const existing = fs.readFileSync(draftPath, 'utf8');
    if (!existing.includes('status: applied')) {
      console.log(`[Promoter] ⏳ Draft already pending: ${slug}.draft.md`);
      return null;
    }
  }

  const autoApproveAt = new Date(Date.now() + AUTO_APPROVE_MS).toISOString();
  const targetRule    = `rocket-${fm.domain || 'general'}-learned.mdc`;

  const draft = `---
instinct_id: ${fm.id || 'unknown'}
confidence: ${fm.confidence}
evidence_count: ${fm.evidence_count}
domain: ${fm.domain || 'general'}
created: ${new Date().toISOString()}
auto_approve_after: ${autoApproveAt}
target_rule: ${targetRule}
status: pending
---

# Proposed Rule Promotion: ${fm.id || 'Unnamed'}

Instinct meets threshold (confidence ≥ ${CONFIDENCE_MIN}, evidence ≥ ${EVIDENCE_MIN}).

## Instinct Content

${body}

## Target

Will be added to: \`.cursor/rules/${targetRule}\`

**Auto-approves at**: ${autoApproveAt}

To **cancel**: delete this file before the deadline.  
To **approve now**: run \`node .cursor/hooks/instinct-promoter.js --apply ${slug}\`
`;
  fs.writeFileSync(draftPath, draft);
  console.log(`[Promoter] 📝 Draft created → memory-bank/promoted-rules/${slug}.draft.md`);
  console.log(`[Promoter]    Auto-approves at: ${autoApproveAt}`);
  return { draftPath, slug };
}

// ── apply promotion ───────────────────────────────────────────────────────────

function applyDraft(draftPath) {
  const content = fs.readFileSync(draftPath, 'utf8');
  if (content.includes('status: applied')) return; // already done

  const fm       = parseFrontmatter(content);
  const bodyMatch = content.match(/## Instinct Content\r?\n\r?\n([\s\S]*?)\r?\n\r?\n## Target/);
  if (!bodyMatch) {
    console.error(`[Promoter] ❌ Could not parse body from ${path.basename(draftPath)}`);
    return;
  }
  const body       = bodyMatch[1].trim();
  const targetRule = fm.target_rule || `rocket-${fm.domain || 'general'}-learned.mdc`;
  const rulePath   = path.join(RULES_DIR, targetRule);

  if (!fs.existsSync(rulePath)) {
    const domain  = (fm.domain || 'general');
    const domainC = domain.charAt(0).toUpperCase() + domain.slice(1);
    const newFile = `---
description: >
  auto-promoted learned patterns for ${domain} — promoted from instinct system
  when confidence >= ${CONFIDENCE_MIN} across >= ${EVIDENCE_MIN} distinct sessions
globs: ["**/*.ts", "**/*.tsx", "**/*.sql"]
alwaysApply: false
---

# Auto-Promoted Learned Patterns — ${domainC}

These patterns were automatically promoted from the instinct system after reaching
≥${CONFIDENCE_MIN} confidence across ≥${EVIDENCE_MIN} sessions. Do not edit manually —
run \`/reflect\` to add new patterns, and the promoter will handle the rest.

---

## ${fm.instinct_id || fm.id || 'Pattern'}

${body}
`;
    ensureDir(RULES_DIR);
    fs.writeFileSync(rulePath, newFile);
    console.log(`[Promoter] ✅ Created new rule file: ${targetRule}`);
  } else {
    const existing = fs.readFileSync(rulePath, 'utf8');
    const section  = `\n---\n\n## ${fm.instinct_id || fm.id || 'Pattern'}\n\n${body}\n`;
    fs.writeFileSync(rulePath, existing.trimEnd() + '\n' + section);
    console.log(`[Promoter] ✅ Appended to: ${targetRule}`);
  }

  // Mark draft applied
  fs.writeFileSync(draftPath, content.replace('status: pending', 'status: applied'));

  // Append to promotion log
  ensureDir(path.dirname(PROMOTION_LOG));
  const logLine = `- ${new Date().toISOString()} | PROMOTED | ${fm.instinct_id || fm.id} `
    + `| confidence=${fm.confidence} | evidence=${fm.evidence_count} | → ${targetRule}\n`;
  fs.appendFileSync(PROMOTION_LOG, logLine);
}

// ── check pending auto-approvals ──────────────────────────────────────────────

function processPendingDrafts() {
  if (!fs.existsSync(PROMOTED_DIR)) return;
  const now = Date.now();
  for (const file of fs.readdirSync(PROMOTED_DIR)) {
    if (!file.endsWith('.draft.md')) continue;
    const draftPath = path.join(PROMOTED_DIR, file);
    const content   = fs.readFileSync(draftPath, 'utf8');
    if (content.includes('status: applied')) continue;
    const m = content.match(/auto_approve_after:\s*(.+)/);
    if (!m) continue;
    if (now >= new Date(m[1].trim()).getTime()) {
      console.log(`[Promoter] ⏰ Auto-approving: ${file}`);
      applyDraft(draftPath);
    }
  }
}

// ── main ──────────────────────────────────────────────────────────────────────

function main() {
  const args = process.argv.slice(2);

  // --apply <slug>
  if (args[0] === '--apply') {
    const slug      = args[1];
    const draftPath = path.join(PROMOTED_DIR, `${slug}.draft.md`);
    if (!fs.existsSync(draftPath)) {
      console.error(`[Promoter] ❌ Draft not found: ${slug}.draft.md`);
      process.exit(1);
    }
    applyDraft(draftPath);
    return;
  }

  // --status
  if (args[0] === '--status') {
    if (!fs.existsSync(PROMOTED_DIR)) { console.log('[Promoter] No promoted-rules dir. Nothing pending.'); return; }
    const pending = fs.readdirSync(PROMOTED_DIR)
      .filter(f => f.endsWith('.draft.md'))
      .filter(f => !fs.readFileSync(path.join(PROMOTED_DIR, f), 'utf8').includes('status: applied'));
    console.log(`[Promoter] ${pending.length} draft(s) pending approval:`);
    pending.forEach(f => console.log(`  ${f}`));
    return;
  }

  // Default: process pending auto-approvals, then scan instincts
  processPendingDrafts();

  if (!fs.existsSync(INSTINCTS_DIR)) {
    console.log('[Promoter] No instincts directory found. Nothing to promote.');
    return;
  }

  const yamlFiles   = fs.readdirSync(INSTINCTS_DIR).filter(f => f.endsWith('.yaml'));
  const existingRules = loadRules();
  let drafted = 0, conflicted = 0, skipped = 0;

  for (const file of yamlFiles) {
    const filePath = path.join(INSTINCTS_DIR, file);
    const text     = fs.readFileSync(filePath, 'utf8');
    const fm       = parseFrontmatter(text);
    const body     = bodyAfterFrontmatter(text);

    const confidence   = parseFloat(fm.confidence   || '0');
    const evidenceCount = parseInt(fm.evidence_count || '0', 10);

    if (confidence < CONFIDENCE_MIN || evidenceCount < EVIDENCE_MIN) {
      skipped++;
      continue;
    }

    // Skip already-applied
    const slug      = toSlug(fm.id);
    const draftPath = path.join(PROMOTED_DIR, `${slug}.draft.md`);
    if (fs.existsSync(draftPath) && fs.readFileSync(draftPath, 'utf8').includes('status: applied')) {
      skipped++;
      continue;
    }

    const conflict = detectConflict(fm, body, existingRules);
    if (conflict) {
      writeConflict(fm, body, conflict);
      conflicted++;
      continue;
    }

    const result = writeDraft(fm, body);
    if (result) drafted++;
    else skipped++;
  }

  console.log(`[Promoter] Scan complete — drafted: ${drafted}, conflicts: ${conflicted}, skipped: ${skipped}`);
}

main();
