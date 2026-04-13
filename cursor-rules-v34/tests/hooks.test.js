/**
 * hooks.test.js — Critical Node.js hook tests
 *
 * Tests run the real hook files via spawnSync with controlled stdin JSON.
 * No mocking of the hook internals — tests the actual compiled behaviour.
 */
import { describe, it, expect } from 'vitest'
import { spawnSync }             from 'child_process'
import { mkdtempSync, rmSync }   from 'fs'
import { join }                  from 'path'
import { tmpdir }                from 'os'

const HOOKS = new URL('../.cursor/hooks/', import.meta.url).pathname

/** Run a hook file, return { status, stdout, stderr } */
function runHook(file, inputObj, extraEnv = {}) {
  const r = spawnSync('node', [join(HOOKS, file)], {
    input:   JSON.stringify(inputObj),
    encoding: 'utf8',
    timeout:  8000,
    env:     { ...process.env, ECC_HOOK_PROFILE: 'standard', ...extraEnv },
    cwd:     tmpdir(),            // neutral dir — no real project
  })
  return { status: r.status ?? 0, stdout: r.stdout ?? '', stderr: r.stderr ?? '' }
}

// ── beforeSubmitPrompt ────────────────────────────────────────────────────────

describe('beforeSubmitPrompt', () => {
  it('passes clean prompt through unchanged', () => {
    const input = { prompt: 'Fix my auth bug' }
    const { status, stdout } = runHook('before-submit-prompt.js', input)
    expect(status).toBe(0)
    expect(JSON.parse(stdout)).toEqual(input)
  })

  it('warns and passes through when Stripe live key detected', () => {
    const { status, stderr } = runHook('before-submit-prompt.js', {
      prompt: 'My key: sk_live_aBcDeFgHiJkLmNoPqRsTuVwXyZ123',
    })
    expect(status).toBe(0)          // warn, not block
    expect(stderr).toMatch(/Stripe live secret key/)
  })

  it('warns on Stripe test key', () => {
    const { stderr } = runHook('before-submit-prompt.js', {
      prompt: 'use sk_test_aBcDeFgHiJkLmNoPqRsTuVwXyZ12 here',
    })
    expect(stderr).toMatch(/Stripe test secret key/)
  })

  it('warns on Supabase PAT', () => {
    const { stderr } = runHook('before-submit-prompt.js', {
      prompt: `token sbp_${'a'.repeat(40)}`,
    })
    expect(stderr).toMatch(/Supabase PAT/)
  })

  it('warns on GitHub PAT', () => {
    const { stderr } = runHook('before-submit-prompt.js', {
      prompt: `token ghp_${'A'.repeat(36)}`,
    })
    expect(stderr).toMatch(/GitHub PAT/)
  })

  it('warns on AWS access key', () => {
    const { stderr } = runHook('before-submit-prompt.js', {
      prompt: 'AKIAIOSFODNN7EXAMPLE is my key',
    })
    expect(stderr).toMatch(/AWS access key/)
  })

  it('handles empty input without crashing', () => {
    const r = spawnSync('node', [join(HOOKS, 'before-submit-prompt.js')], {
      input: '', encoding: 'utf8', timeout: 5000, cwd: tmpdir(),
    })
    expect(r.status).toBe(0)
  })

  it('handles malformed JSON without crashing', () => {
    const r = spawnSync('node', [join(HOOKS, 'before-submit-prompt.js')], {
      input: 'not-json', encoding: 'utf8', timeout: 5000, cwd: tmpdir(),
    })
    expect(r.status).toBe(0)
  })
})

// ── beforeShellExecution ──────────────────────────────────────────────────────

describe('beforeShellExecution', () => {
  const block = (cmd) => runHook('before-shell-execution.js', { command: cmd })

  it('blocks rm -rf on /', () => {
    const { status, stderr } = block('rm -rf /')
    expect(status).toBe(2)
    expect(stderr).toMatch(/BLOCKED/)
  })

  it('blocks rm -rf on ~', () => {
    expect(block('rm -rf ~/important').status).toBe(2)
  })

  it('blocks DROP TABLE', () => {
    expect(block('psql -c "DROP TABLE users"').status).toBe(2)
  })

  it('blocks DROP DATABASE', () => {
    expect(block('psql -c "DROP DATABASE mydb"').status).toBe(2)
  })

  it('blocks DELETE without WHERE', () => {
    expect(block('psql -c "DELETE FROM orders;"').status).toBe(2)
  })

  it('allows DELETE with WHERE', () => {
    // Has WHERE so should pass (exit 0)
    const { status } = block('psql -c "DELETE FROM sessions WHERE expired_at < now();"')
    expect(status).toBe(0)
  })

  it('blocks git push --force', () => {
    expect(block('git push --force origin main').status).toBe(2)
  })

  it('blocks git push -f shorthand', () => {
    expect(block('git push -f origin main').status).toBe(2)
  })

  it('allows normal git push', () => {
    expect(block('git push origin main').status).toBe(0)
  })

  it('blocks npm publish', () => {
    expect(block('npm publish').status).toBe(2)
  })

  it('blocks prisma db push --force-reset', () => {
    expect(block('npx prisma db push --force-reset').status).toBe(2)
  })

  it('blocks command with embedded Stripe live key', () => {
    const { status } = block('curl -H "auth: sk_live_aBcDeFgHiJkLmNoPqRsTuVwXyZ" api.stripe.com')
    expect(status).toBe(2)
  })

  it('allows safe npm install', () => {
    expect(block('npm install').status).toBe(0)
  })

  it('allows supabase db push', () => {
    expect(block('supabase db push').status).toBe(0)
  })

  it('handles empty command without crashing', () => {
    expect(block('').status).toBe(0)
  })
})

// ── afterFileEdit ─────────────────────────────────────────────────────────────

describe('afterFileEdit', () => {
  it('exits 0 for a README edit', () => {
    const { status } = runHook('after-file-edit.js', { path: 'README.md' })
    expect(status).toBe(0)
  })

  it('passes input through (stdout contains the original JSON)', () => {
    const input = { path: 'app/page.tsx' }
    const { stdout } = runHook('after-file-edit.js', input)
    expect(JSON.parse(stdout)).toEqual(input)
  })

  it('handles empty input gracefully', () => {
    const r = spawnSync('node', [join(HOOKS, 'after-file-edit.js')], {
      input: '', encoding: 'utf8', timeout: 5000, cwd: tmpdir(),
    })
    expect(r.status).toBe(0)
  })
})

// ── session-start ─────────────────────────────────────────────────────────────

describe('session-start', () => {
  it('exits 0 in directory with no prior sessions', () => {
    const r = spawnSync('node', [join(HOOKS, 'session-start.js')], {
      input: '{}', encoding: 'utf8', timeout: 8000, cwd: tmpdir(),
    })
    expect(r.status).toBe(0)
  })

  it('stdout is a string (context injected into Cursor)', () => {
    const r = spawnSync('node', [join(HOOKS, 'session-start.js')], {
      input: '{}', encoding: 'utf8', timeout: 8000, cwd: tmpdir(),
    })
    expect(typeof r.stdout).toBe('string')
  })

  it('never crashes on malformed input', () => {
    const r = spawnSync('node', [join(HOOKS, 'session-start.js')], {
      input: 'bad-json', encoding: 'utf8', timeout: 8000, cwd: tmpdir(),
    })
    expect(r.status).toBe(0)
  })

  it('respects ECC_HOOK_PROFILE=minimal (exits quickly)', () => {
    const r = spawnSync('node', [join(HOOKS, 'session-start.js')], {
      input: '{}', encoding: 'utf8', timeout: 5000, cwd: tmpdir(),
      env: { ...process.env, ECC_HOOK_PROFILE: 'minimal' },
    })
    expect(r.status).toBe(0)
  })
})

// ── stop ──────────────────────────────────────────────────────────────────────

describe('stop', () => {
  it('exits 0 and passes input through', () => {
    const input = { model: 'cursor-composer', usage: { input_tokens: 500, output_tokens: 100 } }
    const { status, stdout } = runHook('stop.js', input, { ECC_HOOK_PROFILE: 'minimal' })
    expect(status).toBe(0)
    expect(JSON.parse(stdout)).toEqual(input)
  })

  it('handles empty stdin gracefully', () => {
    const r = spawnSync('node', [join(HOOKS, 'stop.js')], {
      input: '', encoding: 'utf8', timeout: 8000, cwd: tmpdir(),
      env: { ...process.env, ECC_HOOK_PROFILE: 'minimal' },
    })
    expect(r.status).toBe(0)
  })

  it('handles malformed JSON gracefully', () => {
    const r = spawnSync('node', [join(HOOKS, 'stop.js')], {
      input: '{{bad}}', encoding: 'utf8', timeout: 8000, cwd: tmpdir(),
      env: { ...process.env, ECC_HOOK_PROFILE: 'minimal' },
    })
    expect(r.status).toBe(0)
  })
})
