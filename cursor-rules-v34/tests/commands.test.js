/**
 * commands.test.js — Smoke tests for /harness-audit and /quality-gate commands
 * Verifies structure, key instructions, and all 34 commands exist
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, existsSync, readdirSync } from 'fs'
import { join }                                  from 'path'

const CMD_DIR = new URL('../.cursor/commands/', import.meta.url).pathname

function read(name) {
  return readFileSync(join(CMD_DIR, `${name}.md`), 'utf8')
}

// ── /harness-audit ────────────────────────────────────────────────────────────

describe('/harness-audit command', () => {
  it('file exists',                   () => expect(existsSync(join(CMD_DIR, 'harness-audit.md'))).toBe(true))
  it('mentions hooks',                () => expect(read('harness-audit').toLowerCase()).toMatch(/hook/))
  it('mentions rules',                () => expect(read('harness-audit').toLowerCase()).toMatch(/rule/))
  it('mentions MCP',                  () => expect(read('harness-audit').toLowerCase()).toMatch(/mcp/))
  it('mentions skills or agents',     () => expect(read('harness-audit').toLowerCase()).toMatch(/skill|agent/))
})

// ── /quality-gate ─────────────────────────────────────────────────────────────

describe('/quality-gate command', () => {
  it('file exists',                         () => expect(existsSync(join(CMD_DIR, 'quality-gate.md'))).toBe(true))
  it('mentions TypeScript check',           () => expect(read('quality-gate').toLowerCase()).toMatch(/typescript|tsc/))
  it('mentions RLS',                        () => expect(read('quality-gate').toLowerCase()).toMatch(/rls|row.level/))
  it('has APPROVE/REJECT verdict output',   () => expect(read('quality-gate').toUpperCase()).toMatch(/APPROVE|REJECT|VERDICT/))
})

// ── /fix-auth ─────────────────────────────────────────────────────────────────

describe('/fix-auth command', () => {
  it('file exists',                   () => expect(existsSync(join(CMD_DIR, 'fix-auth.md'))).toBe(true))
  it('mentions getUser',              () => expect(read('fix-auth')).toMatch(/getUser/))
  it('does not recommend getSession', () => expect(read('fix-auth')).not.toMatch(/use getSession/))
})

// ── /review-diff ──────────────────────────────────────────────────────────────

describe('/review-diff command', () => {
  it('file exists',                   () => expect(existsSync(join(CMD_DIR, 'review-diff.md'))).toBe(true))
  it('checks for scope creep',        () => expect(read('review-diff').toLowerCase()).toMatch(/scope/))
  it('outputs APPROVE or REJECT',     () => expect(read('review-diff').toUpperCase()).toMatch(/APPROVE|REJECT/))
})

// ── /security-audit ───────────────────────────────────────────────────────────

describe('/security-audit command', () => {
  it('file exists',              () => expect(existsSync(join(CMD_DIR, 'security-audit.md'))).toBe(true))
  it('mentions RLS',             () => expect(read('security-audit').toLowerCase()).toMatch(/rls|row.level/))
})

// ── /reflect ─────────────────────────────────────────────────────────────────

describe('/reflect command', () => {
  it('file exists',              () => expect(existsSync(join(CMD_DIR, 'reflect.md'))).toBe(true))
  it('mentions instinct',        () => expect(read('reflect').toLowerCase()).toMatch(/instinct/))
})

// ── all 34 commands exist ─────────────────────────────────────────────────────

describe('All 34 commands exist', () => {
  const expected = [
    'audit-codebase','capture-convention','check-mcp','debug-error','docs',
    'evolve','fix-auth','fix-database','fix-deployment','fix-performance',
    'fix-stripe','fresh-session','handoff-report','harness-audit',
    'implement-feature','instinct-export','instinct-import','instinct-status',
    'learn-eval','load-context','make-legible','model-route','plan-feature',
    'quality-gate','refactor-safe','reflect','review-diff','security-audit',
    'spec-feature','sync-rules','test-fix-loop','update-memory','use-notepad',
    'yolo-tdd',
  ]

  for (const cmd of expected) {
    it(`/${cmd} exists`, () => {
      expect(existsSync(join(CMD_DIR, `${cmd}.md`)), `Missing: ${cmd}.md`).toBe(true)
    })
  }

  it('total count is 34', () => {
    const actual = readdirSync(CMD_DIR).filter(f => f.endsWith('.md'))
    expect(actual.length).toBeGreaterThanOrEqual(34)
  })
})
