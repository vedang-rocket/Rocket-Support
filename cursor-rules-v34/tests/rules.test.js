/**
 * rules.test.js — Rule file integrity, hooks.json, mcp.json, project structure
 */
import { describe, it, expect } from 'vitest'
import { readFileSync, readdirSync, existsSync } from 'fs'
import { resolve, join }                         from 'path'

const ROOT      = new URL('../', import.meta.url).pathname
const RULES_DIR = join(ROOT, '.cursor', 'rules')
const HOOKS_CFG = join(ROOT, '.cursor', 'hooks.json')
const MCP_CFG   = join(ROOT, '.cursor', 'mcp.json')

const allRules  = readdirSync(RULES_DIR).filter(f => f.endsWith('.mdc'))

// ── Rule file integrity ───────────────────────────────────────────────────────

describe('Rule files — count and baseline', () => {
  it('has at least 60 rule files', () => {
    expect(allRules.length).toBeGreaterThanOrEqual(60)
  })

  it('has exactly 2 alwaysApply: true rules', () => {
    const always = allRules.filter(f =>
      readFileSync(join(RULES_DIR, f), 'utf8').includes('alwaysApply: true')
    )
    expect(always).toHaveLength(2)
    expect(always).toContain('rocket-cursor-behavior.mdc')
    expect(always).toContain('rocket-quick-reference.mdc')
  })

  it('no rule file exceeds 500 lines', () => {
    const over = allRules.filter(f => {
      const lines = readFileSync(join(RULES_DIR, f), 'utf8').split('\n').length
      return lines > 500
    })
    expect(over).toHaveLength(0)
  })

  it('no rule file has Flutter or Dart references', () => {
    const flagged = allRules.filter(f => {
      const c = readFileSync(join(RULES_DIR, f), 'utf8').toLowerCase()
      return /flutter\b|\.dart\b|apk\b/.test(c)
    })
    expect(flagged).toHaveLength(0)
  })
})

describe('Rule files — frontmatter validity', () => {
  it('every rule has opening --- and closing ---', () => {
    const invalid = allRules.filter(f => {
      const c = readFileSync(join(RULES_DIR, f), 'utf8')
      return !c.startsWith('---') || !c.match(/^---\r?\n[\s\S]*?\r?\n---/)
    })
    expect(invalid).toHaveLength(0)
  })

  it('every rule has a description field', () => {
    const missing = allRules.filter(f => {
      const c = readFileSync(join(RULES_DIR, f), 'utf8')
      return !c.match(/^---[\s\S]*?description:/m)
    })
    expect(missing).toHaveLength(0)
  })
})

describe('Rule files — key files exist', () => {
  const required = [
    'rocket-cursor-behavior.mdc',
    'rocket-quick-reference.mdc',
    'rocket-supabase-auth-sessions.mdc',
    'rocket-supabase-production.mdc',
    'rocket-supabase-realtime.mdc',
    'rocket-supabase-rag.mdc',
    'rocket-supabase-queues.mdc',
    'rocket-nextjs-patterns.mdc',
    'rocket-nextjs-deployment.mdc',
    'rocket-netlify.mdc',
    'rocket-ai-streaming.mdc',
    'rocket-cursor-automations.mdc',
    'rocket-supabase-branching.mdc',
    'rocket-supabase-observability.mdc',
    'rocket-stripe-sync-engine.mdc',
  ]
  for (const name of required) {
    it(`${name} exists`, () => {
      expect(existsSync(join(RULES_DIR, name)), `Missing rule: ${name}`).toBe(true)
    })
  }
})

// ── hooks.json ───────────────────────────────────────────────────────────────

describe('hooks.json', () => {
  const cfg = JSON.parse(readFileSync(HOOKS_CFG, 'utf8'))

  it('is valid JSON', () => { expect(cfg).toBeTruthy() })

  it('version is integer 1', () => { expect(cfg.version).toBe(1) })

  it('has all 14 required hook events', () => {
    const required = [
      'sessionStart','sessionEnd','beforeShellExecution','afterShellExecution',
      'afterFileEdit','beforeMCPExecution','afterMCPExecution','beforeReadFile',
      'beforeSubmitPrompt','beforeTabFileRead','subagentStart','subagentStop',
      'preCompact','stop',
    ]
    const events = Object.keys(cfg.hooks)
    for (const ev of required) {
      expect(events, `Missing hook event: ${ev}`).toContain(ev)
    }
  })

  it('all handlers use node (not shell scripts)', () => {
    for (const [ev, handlers] of Object.entries(cfg.hooks)) {
      for (const h of handlers) {
        expect(h.command, `${ev} must use node`).toMatch(/^node /)
        expect(h.command).not.toMatch(/\.sh$/)
      }
    }
  })
})

// ── mcp.json ─────────────────────────────────────────────────────────────────

describe('mcp.json', () => {
  const cfg = JSON.parse(readFileSync(MCP_CFG, 'utf8'))

  it('is valid JSON', () => { expect(cfg).toBeTruthy() })

  it('has mcpServers key', () => { expect(cfg).toHaveProperty('mcpServers') })

  it('supabase server configured', () => {
    expect(cfg.mcpServers).toHaveProperty('supabase')
  })

  it('supabase uses --project-ref flag', () => {
    expect(cfg.mcpServers.supabase.args).toContain('--project-ref')
  })

  it('supabase uses --read-only flag for safety', () => {
    expect(cfg.mcpServers.supabase.args).toContain('--read-only')
  })

  it('supabase uses SUPABASE_ACCESS_TOKEN env var', () => {
    expect(cfg.mcpServers.supabase.env).toHaveProperty('SUPABASE_ACCESS_TOKEN')
  })

  it('memory server configured', () => {
    expect(cfg.mcpServers).toHaveProperty('memory')
  })

  it('no hardcoded live API keys in config', () => {
    const raw = JSON.stringify(cfg)
    expect(raw).not.toMatch(/sk_live_[a-zA-Z0-9]{20,}/)
    expect(raw).not.toMatch(/sbp_[a-f0-9]{40}/)
  })
})

// ── project structure ─────────────────────────────────────────────────────────

describe('Project structure', () => {
  const dirs = [
    '.cursor/rules', '.cursor/hooks', '.cursor/commands',
    '.cursor/skills', '.cursor/notepads', 'agents', 'memory-bank',
    'memory-bank/instincts', 'memory-bank/promoted-rules',
  ]
  for (const d of dirs) {
    it(`${d}/ exists`, () => {
      expect(existsSync(join(ROOT, d)), `Missing directory: ${d}`).toBe(true)
    })
  }

  it('no legacy hooks-scripts directory', () => {
    expect(existsSync(join(ROOT, '.cursor', 'hooks-scripts'))).toBe(false)
  })

  it('VERSION file says V32', () => {
    const v = readFileSync(join(ROOT, 'VERSION'), 'utf8').trim()
    expect(v).toBe('V32')
  })

  it('instinct-promoter.js exists in hooks', () => {
    expect(existsSync(join(ROOT, '.cursor', 'hooks', 'instinct-promoter.js'))).toBe(true)
  })
})
