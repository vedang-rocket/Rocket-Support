# Notepad: RLS Setup Template
# Reference with: @notepad-rls-setup

Standard RLS policies for a new Rocket.new table.
Replace `your_table` with the actual table name.

```sql
-- Enable RLS
ALTER TABLE public.your_table ENABLE ROW LEVEL SECURITY;

-- SELECT: users see only their own rows
CREATE POLICY "your_table_select_own"
ON public.your_table FOR SELECT
USING (auth.uid() = user_id);

-- INSERT: users can only insert their own rows
CREATE POLICY "your_table_insert_own"
ON public.your_table FOR INSERT
WITH CHECK (auth.uid() = user_id);

-- UPDATE: users can only update their own rows
CREATE POLICY "your_table_update_own"
ON public.your_table FOR UPDATE
USING (auth.uid() = user_id)
WITH CHECK (auth.uid() = user_id);

-- DELETE: users can only delete their own rows
CREATE POLICY "your_table_delete_own"
ON public.your_table FOR DELETE
USING (auth.uid() = user_id);
```

For public read + owner write pattern:
```sql
CREATE POLICY "your_table_public_read"
ON public.your_table FOR SELECT USING (true);

CREATE POLICY "your_table_owner_write"
ON public.your_table FOR ALL
USING (auth.uid() = user_id)
WITH CHECK (auth.uid() = user_id);
```
