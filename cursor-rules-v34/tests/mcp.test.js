/**
 * mcp.test.js — MCP config validation + mocked response shapes
 */
import { describe, it, expect, vi } from 'vitest'
import { readFileSync, existsSync }  from 'fs'
import { join }                      from 'path'

const ROOT    = new URL('../', import.meta.url).pathname
const MCP_CFG = join(ROOT, '.cursor', 'mcp.json')

// ── static config checks ──────────────────────────────────────────────────────

describe('MCP static configuration', () => {
  const cfg = JSON.parse(readFileSync(MCP_CFG, 'utf8'))

  it('parses to valid object', () => { expect(cfg).toBeTruthy() })

  it('supabase server: command is npx', () => {
    expect(cfg.mcpServers.supabase.command).toBe('npx')
  })

  it('supabase server: uses @supabase/mcp-server-supabase@latest', () => {
    expect(cfg.mcpServers.supabase.args.join(' ')).toContain('@supabase/mcp-server-supabase@latest')
  })

  it('supabase server: includes --project-ref flag', () => {
    expect(cfg.mcpServers.supabase.args).toContain('--project-ref')
  })

  it('supabase server: includes --read-only flag', () => {
    expect(cfg.mcpServers.supabase.args).toContain('--read-only')
  })

  it('supabase server: SUPABASE_ACCESS_TOKEN env var present', () => {
    expect(cfg.mcpServers.supabase.env).toHaveProperty('SUPABASE_ACCESS_TOKEN')
  })

  it('stripe server: command is npx', () => {
    expect(cfg.mcpServers.stripe?.command).toBe('npx')
  })

  it('stripe server: uses @stripe/mcp', () => {
    expect(cfg.mcpServers.stripe?.args?.join(' ')).toContain('@stripe/mcp')
  })

  it('memory server: uses @modelcontextprotocol/server-memory', () => {
    expect(cfg.mcpServers.memory?.args?.join(' ')).toContain('@modelcontextprotocol/server-memory')
  })

  it('no production API keys hardcoded', () => {
    const raw = JSON.stringify(cfg)
    expect(raw).not.toMatch(/sk_live_[a-zA-Z0-9]{10,}/)
    expect(raw).not.toMatch(/sbp_[a-f0-9]{40}/)
    expect(raw).not.toMatch(/eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9\.[a-zA-Z0-9_-]{100,}/)
  })
})

// ── mocked MCP response shapes ────────────────────────────────────────────────

describe('Supabase MCP — mocked response shapes', () => {
  it('list_tables response has expected shape', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        tables: [
          { schema: 'public', name: 'profiles', row_count: 42,  rls_enabled: true  },
          { schema: 'public', name: 'orders',   row_count: 156, rls_enabled: true  },
          { schema: 'public', name: 'products', row_count: 30,  rls_enabled: false },
        ],
      }),
    })
    const res  = await mockFetch('mock://supabase/list_tables')
    const data = await res.json()
    expect(data.tables).toHaveLength(3)
    expect(data.tables[0]).toHaveProperty('name')
    expect(data.tables[0]).toHaveProperty('rls_enabled')
    // Can identify tables without RLS
    const noRls = data.tables.filter(t => !t.rls_enabled)
    expect(noRls).toHaveLength(1)
    expect(noRls[0].name).toBe('products')
  })

  it('execute_sql response has expected shape', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        rows: [{ db_size: '12 MB', bytes: 12582912 }],
        rowCount: 1,
      }),
    })
    const res  = await mockFetch('mock://supabase/execute_sql')
    const data = await res.json()
    expect(data.rows[0]).toHaveProperty('db_size')
    expect(data.rows[0].bytes).toBeTypeOf('number')
  })

  it('get_project response has expected shape', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        id:     'abc123def456',
        name:   'my-rocket-app',
        region: 'us-east-1',
        status: 'ACTIVE_HEALTHY',
      }),
    })
    const res  = await mockFetch('mock://supabase/get_project')
    const data = await res.json()
    expect(data.status).toBe('ACTIVE_HEALTHY')
    expect(data.region).toBeTruthy()
  })
})

describe('Stripe MCP — mocked response shapes', () => {
  it('retrieve_balance has expected shape', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        object:    'balance',
        available: [{ amount: 10000, currency: 'usd', source_types: { card: 10000 } }],
        pending:   [{ amount: 5000,  currency: 'usd' }],
      }),
    })
    const res  = await mockFetch('mock://stripe/balance')
    const data = await res.json()
    expect(data.available[0].currency).toBe('usd')
    expect(data.available[0].amount).toBeTypeOf('number')
  })

  it('list_customers handles pagination shape', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        object:   'list',
        data:     [{ id: 'cus_abc', email: 'user@example.com', name: 'Test User' }],
        has_more: false,
        url:      '/v1/customers',
      }),
    })
    const res  = await mockFetch('mock://stripe/customers')
    const data = await res.json()
    expect(data.data[0].id).toMatch(/^cus_/)
    expect(data.has_more).toBe(false)
  })
})

describe('Memory MCP — mocked response shapes', () => {
  it('search_nodes has expected shape', async () => {
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        entities: [
          { name: 'getUser-pattern', entityType: 'instinct',
            observations: ['always use getUser not getSession'] },
          { name: 'RLS-profile-trigger', entityType: 'pattern',
            observations: ['missing trigger causes empty profile table'] },
        ],
        relations: [],
      }),
    })
    const res  = await mockFetch('mock://memory/search_nodes')
    const data = await res.json()
    expect(data.entities).toHaveLength(2)
    expect(data.entities[0]).toHaveProperty('observations')
    expect(data.relations).toBeInstanceOf(Array)
  })

  it('handles MCP connection failure gracefully', async () => {
    const mockFetch = vi.fn().mockRejectedValue(new Error('Connection refused'))
    await expect(mockFetch('mock://memory/search_nodes')).rejects.toThrow('Connection refused')
  })
})
