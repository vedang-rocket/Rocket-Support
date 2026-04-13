/**
 * promoter.test.js — Auto-promotion engine unit tests
 *
 * Creates isolated tmp workspaces so tests never touch the real rule files.
 */
import { describe, it, expect, afterEach } from 'vitest'
import { mkdtempSync, rmSync, mkdirSync,
         writeFileSync, readFileSync,
         readdirSync, existsSync }          from 'fs'
import { join }                             from 'path'
import { tmpdir }                           from 'os'
import { spawnSync }                        from 'child_process'

const PROMOTER = new URL('../.cursor/hooks/instinct-promoter.js', import.meta.url).pathname

// Per-test temporary workspace
let ws
function makeWS() {
  ws = mkdtempSync(join(tmpdir(), 'rkt-prom-'))
  mkdirSync(join(ws, 'memory-bank', 'instincts'),     { recursive: true })
  mkdirSync(join(ws, '.cursor', 'rules'),             { recursive: true })
}

afterEach(() => { if (ws && existsSync(ws)) rmSync(ws, { recursive: true, force: true }) })

function run(...args) {
  return spawnSync('node', [PROMOTER, ...args], {
    encoding: 'utf8', timeout: 15000, cwd: ws,
  })
}

function writeInstinct(id, confidence, evidenceCount, domain = 'auth', extraBody = '') {
  const content = `---
id: ${id}
trigger: "when this pattern occurs"
confidence: ${confidence}
domain: ${domain}
source: session-observation
created: 2026-01-01
last_seen: 2026-03-01
evidence_count: ${evidenceCount}
---

# ${id}

## Action
${extraBody || `Always use getUser() not getSession() on the server side.`}

## Evidence
- 2026-01-15 SaaS App: observed issue
`
  writeFileSync(join(ws, 'memory-bank', 'instincts', `${id}.yaml`), content)
}

// ── threshold checks ──────────────────────────────────────────────────────────

describe('Threshold enforcement', () => {
  it('skips instinct with confidence < 0.9', () => {
    makeWS()
    writeInstinct('low-conf', 0.7, 6)
    const r = run()
    expect(r.status).toBe(0)
    const promoted = join(ws, 'memory-bank', 'promoted-rules')
    const drafts = existsSync(promoted) ? readdirSync(promoted).filter(f => f.endsWith('.draft.md')) : []
    expect(drafts).toHaveLength(0)
  })

  it('skips instinct with evidence_count < 5', () => {
    makeWS()
    writeInstinct('low-evi', 0.95, 3)
    run()
    const promoted = join(ws, 'memory-bank', 'promoted-rules')
    const drafts = existsSync(promoted) ? readdirSync(promoted).filter(f => f.endsWith('.draft.md')) : []
    expect(drafts).toHaveLength(0)
  })

  it('skips instinct at exactly threshold boundary (conf=0.89, evi=4)', () => {
    makeWS()
    writeInstinct('boundary', 0.89, 4)
    run()
    const promoted = join(ws, 'memory-bank', 'promoted-rules')
    const drafts = existsSync(promoted) ? readdirSync(promoted).filter(f => f.endsWith('.draft.md')) : []
    expect(drafts).toHaveLength(0)
  })

  it('promotes instinct at exactly threshold (conf=0.9, evi=5)', () => {
    makeWS()
    writeInstinct('at-threshold', 0.9, 5)
    run()
    const promoted = join(ws, 'memory-bank', 'promoted-rules')
    const drafts = existsSync(promoted) ? readdirSync(promoted).filter(f => f.endsWith('.draft.md')) : []
    expect(drafts).toHaveLength(1)
  })
})

// ── draft creation ────────────────────────────────────────────────────────────

describe('Draft creation', () => {
  it('creates a draft file for qualifying instinct', () => {
    makeWS()
    writeInstinct('qualifies', 0.95, 7)
    const r = run()
    expect(r.status).toBe(0)
    const promoted = join(ws, 'memory-bank', 'promoted-rules')
    const drafts = readdirSync(promoted).filter(f => f.endsWith('.draft.md'))
    expect(drafts).toHaveLength(1)
  })

  it('draft contains required frontmatter fields', () => {
    makeWS()
    writeInstinct('with-fields', 0.92, 6, 'database')
    run()
    const promoted = join(ws, 'memory-bank', 'promoted-rules')
    const draft = readFileSync(join(promoted, readdirSync(promoted)[0]), 'utf8')
    expect(draft).toMatch(/instinct_id:/)
    expect(draft).toMatch(/confidence: 0\.92/)
    expect(draft).toMatch(/evidence_count: 6/)
    expect(draft).toMatch(/auto_approve_after:/)
    expect(draft).toMatch(/status: pending/)
    expect(draft).toMatch(/target_rule: rocket-database-learned\.mdc/)
  })

  it('does not create duplicate draft on second run', () => {
    makeWS()
    writeInstinct('no-dup', 0.95, 8)
    run()
    run() // second run
    const promoted = join(ws, 'memory-bank', 'promoted-rules')
    const drafts = readdirSync(promoted).filter(f => f.endsWith('.draft.md'))
    expect(drafts).toHaveLength(1)
  })

  it('handles multiple qualifying instincts — creates one draft each', () => {
    makeWS()
    writeInstinct('first',  0.91, 6, 'auth')
    writeInstinct('second', 0.93, 7, 'stripe')
    writeInstinct('third',  0.95, 9, 'database')
    run()
    const promoted = join(ws, 'memory-bank', 'promoted-rules')
    const drafts = readdirSync(promoted).filter(f => f.endsWith('.draft.md'))
    expect(drafts).toHaveLength(3)
  })
})

// ── conflict detection ────────────────────────────────────────────────────────

describe('Conflict detection', () => {
  it('writes conflict report when instinct contradicts existing rule', () => {
    makeWS()
    // Existing rule says getSession is preferred
    writeFileSync(join(ws, '.cursor', 'rules', 'rocket-auth.mdc'),
      'use getSession to retrieve the current user session on the server')
    // Instinct says NEVER getSession
    writeInstinct('never-getsession', 0.93, 6, 'auth',
      'Never use getSession on server side. Use getUser instead.')
    run()
    const conflicts = join(ws, 'memory-bank', 'conflicts.md')
    expect(existsSync(conflicts)).toBe(true)
    expect(readFileSync(conflicts, 'utf8')).toMatch(/Conflict/)
  })

  it('conflicting instinct does NOT create a draft', () => {
    makeWS()
    writeFileSync(join(ws, '.cursor', 'rules', 'rocket-auth.mdc'),
      'use getSession to retrieve the current user session on the server')
    writeInstinct('conflict-inst', 0.93, 6, 'auth',
      'Never use getSession on server side.')
    run()
    const promoted = join(ws, 'memory-bank', 'promoted-rules')
    const drafts = existsSync(promoted) ? readdirSync(promoted).filter(f => f.endsWith('.draft.md')) : []
    expect(drafts).toHaveLength(0)
  })
})

// ── --apply flag ──────────────────────────────────────────────────────────────

describe('--apply flag', () => {
  it('immediately promotes a pending draft to a rule file', () => {
    makeWS()
    writeInstinct('apply-me', 0.95, 6, 'performance')
    run()                         // creates draft
    const promoted = join(ws, 'memory-bank', 'promoted-rules')
    const slug = readdirSync(promoted)[0].replace('.draft.md', '')
    run('--apply', slug)          // force-apply

    const ruleFile = join(ws, '.cursor', 'rules', 'rocket-performance-learned.mdc')
    expect(existsSync(ruleFile)).toBe(true)
    expect(readFileSync(ruleFile, 'utf8')).toMatch(/apply-me/)
  })

  it('marks draft as applied after --apply', () => {
    makeWS()
    writeInstinct('mark-applied', 0.91, 5, 'stripe')
    run()
    const promoted = join(ws, 'memory-bank', 'promoted-rules')
    const slug = readdirSync(promoted)[0].replace('.draft.md', '')
    run('--apply', slug)
    const draftContent = readFileSync(join(promoted, `${slug}.draft.md`), 'utf8')
    expect(draftContent).toMatch(/status: applied/)
  })

  it('appends to existing learned rule file (does not overwrite)', () => {
    makeWS()
    // Pre-create a learned rule file
    writeFileSync(join(ws, '.cursor', 'rules', 'rocket-auth-learned.mdc'),
      '---\ndescription: learned auth patterns\nglobs: []\nalwaysApply: false\n---\n\n# Existing Pattern\n\nSome existing content.\n')

    writeInstinct('append-test', 0.95, 6, 'auth')
    run()
    const slug = readdirSync(join(ws, 'memory-bank', 'promoted-rules'))[0].replace('.draft.md', '')
    run('--apply', slug)

    const rule = readFileSync(join(ws, '.cursor', 'rules', 'rocket-auth-learned.mdc'), 'utf8')
    expect(rule).toMatch(/Existing Pattern/)   // original still there
    expect(rule).toMatch(/append-test/)        // new section added
  })

  it('writes an entry to promotion-log.md', () => {
    makeWS()
    writeInstinct('log-test', 0.93, 7, 'database')
    run()
    const slug = readdirSync(join(ws, 'memory-bank', 'promoted-rules'))[0].replace('.draft.md', '')
    run('--apply', slug)
    const log = readFileSync(join(ws, 'memory-bank', 'promotion-log.md'), 'utf8')
    expect(log).toMatch(/PROMOTED/)
    expect(log).toMatch(/log-test/)
  })

  it('exits non-zero when --apply target does not exist', () => {
    makeWS()
    const r = run('--apply', 'nonexistent-draft')
    expect(r.status).not.toBe(0)
  })
})

// ── --status flag ─────────────────────────────────────────────────────────────

describe('--status flag', () => {
  it('reports 0 pending when no drafts exist', () => {
    makeWS()
    const r = run('--status')
    expect(r.status).toBe(0)
    expect(r.stdout).toMatch(/0|No promoted-rules/)
  })

  it('reports correct count of pending drafts', () => {
    makeWS()
    writeInstinct('pend-a', 0.91, 5, 'auth')
    writeInstinct('pend-b', 0.93, 6, 'stripe')
    run()          // creates 2 drafts
    const r = run('--status')
    expect(r.stdout).toMatch(/2/)
  })
})

// ── empty / edge cases ────────────────────────────────────────────────────────

describe('Edge cases', () => {
  it('exits cleanly when instincts dir does not exist', () => {
    makeWS()
    // instincts dir was created but let's remove it
    rmSync(join(ws, 'memory-bank', 'instincts'), { recursive: true })
    const r = run()
    expect(r.status).toBe(0)
  })

  it('handles instinct YAML with missing fields gracefully', () => {
    makeWS()
    writeFileSync(join(ws, 'memory-bank', 'instincts', 'empty.yaml'), '---\n---\n# Nothing\n')
    const r = run()
    expect(r.status).toBe(0)
  })
})
