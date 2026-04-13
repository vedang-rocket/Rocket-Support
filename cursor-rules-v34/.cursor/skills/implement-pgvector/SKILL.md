---
name: implement-pgvector
description: >
  add vector search to rocket project, implement AI semantic search supabase pgvector,
  store OpenAI embeddings supabase, similarity search postgres, RAG retrieval augmented generation,
  add embedding column to table, create match function supabase, vector similarity search nextjs,
  pgvector not working, semantic search implementation, AI search feature,
  HNSW index pgvector, cosine distance vector search, text-embedding-3-small
globs: ["**/*.ts", "**/*.tsx", "**/*.sql"]
alwaysApply: false
---

# Skill: Implement pgvector (AI Semantic Search)

**Stack**: Next.js App Router + Supabase pgvector + OpenAI embeddings
**When to use**: Adding any AI-powered search, recommendation, or similarity feature to a Rocket project

---

## The Complete 6-Step Implementation

### Step 1 — Enable pgvector
```sql
-- Run in Supabase SQL Editor (or via supabase/migrations/[timestamp]_pgvector.sql)
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;
```

### Step 2 — Add embedding column to your table
```sql
-- Add to existing table OR create new one
-- OpenAI text-embedding-3-small = 1536 dimensions
-- OpenAI text-embedding-3-large = 3072 dimensions (more accurate, more expensive)
-- open source gte-small = 384 dimensions (free, runs in Edge Function)

ALTER TABLE your_table ADD COLUMN embedding VECTOR(1536);

-- OR create fresh table
CREATE TABLE documents (
  id BIGINT PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
  content TEXT NOT NULL,
  embedding VECTOR(1536),
  user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
CREATE POLICY "users_own_docs" ON documents FOR ALL USING (auth.uid() = user_id);
```

### Step 3 — Add HNSW index (do this AFTER loading initial data)
```sql
-- HNSW: fast, accurate, good for most apps
CREATE INDEX ON documents USING hnsw (embedding vector_cosine_ops);

-- IVFFlat: cheaper, slightly less accurate (needs 1000+ rows to help)
-- CREATE INDEX ON documents USING ivfflat (embedding vector_l2_ops) WITH (lists = 100);
```

### Step 4 — Create the match function (required — PostgREST doesn't support vector ops directly)
```sql
CREATE OR REPLACE FUNCTION match_documents(
  query_embedding VECTOR(1536),
  match_threshold FLOAT DEFAULT 0.78,  -- 0.0-1.0, higher = more similar required
  match_count INT DEFAULT 5
)
RETURNS TABLE(id BIGINT, content TEXT, similarity FLOAT)
LANGUAGE sql STABLE SECURITY INVOKER AS $$
  SELECT id, content, 1 - (embedding <=> query_embedding) AS similarity
  FROM documents
  WHERE embedding IS NOT NULL
    AND 1 - (embedding <=> query_embedding) > match_threshold
  ORDER BY embedding <=> query_embedding
  LIMIT match_count;
$$;
```

### Step 5 — Store embeddings from Next.js (server-side only)
```typescript
// lib/embeddings.ts — utility for generating and storing embeddings
import OpenAI from 'openai'

const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY })

export async function generateEmbedding(text: string): Promise<number[]> {
  const response = await openai.embeddings.create({
    model: 'text-embedding-3-small',
    input: text.replace(/\n/g, ' '),  // normalize whitespace
  })
  return response.data[0].embedding
}

// app/api/documents/route.ts — store a document with its embedding
import { createClient } from '@/lib/supabase/server'

export async function POST(request: Request) {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) return Response.json({ error: 'Unauthorized' }, { status: 401 })

  const { content } = await request.json()

  // Generate embedding server-side (never expose OPENAI_API_KEY to browser)
  const embedding = await generateEmbedding(content)

  const { data, error } = await supabase
    .from('documents')
    .insert({ content, embedding, user_id: user.id })
    .select()
    .single()

  if (error) return Response.json({ error: error.message }, { status: 500 })
  return Response.json({ data }, { status: 201 })
}
```

### Step 6 — Search (query with embedding)
```typescript
// app/api/search/route.ts
import { generateEmbedding } from '@/lib/embeddings'

export async function POST(request: Request) {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) return Response.json({ error: 'Unauthorized' }, { status: 401 })

  const { query } = await request.json()

  // Generate embedding for the search query
  const queryEmbedding = await generateEmbedding(query)

  // Call the match function via RPC
  const { data, error } = await supabase.rpc('match_documents', {
    query_embedding: queryEmbedding,
    match_threshold: 0.78,
    match_count: 5,
  })

  if (error) return Response.json({ error: error.message }, { status: 500 })
  return Response.json({ results: data })
}
```

---

## Common Mistakes

| Mistake | Fix |
|---|---|
| Querying vectors directly with `.select()` | Always use `.rpc('match_function', ...)` |
| Different model for storage vs query | Must use the SAME embedding model for both |
| Adding HNSW index before any data | Add the index AFTER you have data — empty index does nothing |
| Not handling `null` embeddings | Add `WHERE embedding IS NOT NULL` to your match function |
| Storing embeddings in the browser | Embeddings require `OPENAI_API_KEY` — server-side only |
| Using `NEXT_PUBLIC_OPENAI_API_KEY` | Never — that exposes your key to every user |

---

## Environment Variables Needed
```bash
OPENAI_API_KEY=sk-...   # Server-only, never NEXT_PUBLIC_
# In Netlify: add to environment variables
```

---

## Cost Estimates (OpenAI text-embedding-3-small)
- ~$0.02 per 1 million tokens
- Average document of 500 words ≈ 750 tokens ≈ $0.000015
- 10,000 documents ≈ $0.15 to embed once
- Search queries: each query = 1 embedding call = fractions of a cent

## Verify It Works
```sql
-- Check embeddings are stored
SELECT id, content, embedding IS NOT NULL AS has_embedding FROM documents LIMIT 5;

-- Test the match function directly in SQL Editor
SELECT * FROM match_documents(
  (SELECT embedding FROM documents LIMIT 1),  -- use an existing embedding as test query
  0.5,   -- low threshold for testing
  3
);
```
