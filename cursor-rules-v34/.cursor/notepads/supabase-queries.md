# Notepad: Supabase Query Patterns
# Reference with: @notepad-supabase-queries

Common Supabase query patterns for Rocket.new projects.

```typescript
// Server Component — always use server client
import { createClient } from '@/lib/supabase/server'
const supabase = await createClient()

// Fetch with type safety
const { data, error } = await supabase
  .from('profiles')
  .select('*')
  .eq('id', user.id)
  .single() // use when guaranteed 1 row

// Use maybeSingle() when row might not exist
const { data } = await supabase
  .from('profiles')
  .select('*')
  .eq('id', userId)
  .maybeSingle()

// Insert with return
const { data, error } = await supabase
  .from('posts')
  .insert({ title: 'Hello', user_id: user.id })
  .select()
  .single()

// Update
const { error } = await supabase
  .from('profiles')
  .update({ display_name: 'New Name' })
  .eq('id', user.id)

// Delete
const { error } = await supabase
  .from('posts')
  .delete()
  .eq('id', postId)
  .eq('user_id', user.id) // always scope to user

// Real-time subscription (client component only)
useEffect(() => {
  const channel = supabase
    .channel('table-changes')
    .on('postgres_changes',
      { event: '*', schema: 'public', table: 'messages' },
      (payload) => setMessages(prev => [...prev, payload.new as Message])
    )
    .subscribe()
  return () => { supabase.removeChannel(channel) }
}, [])
```
