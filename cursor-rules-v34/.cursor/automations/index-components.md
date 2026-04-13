# Component Library Indexer Automation
# Trigger: Weekly on Sunday at 10pm, or run /index-components manually
# Copy this prompt into Cursor Settings → Automations

---

You are a component library cataloguer for a Rocket.new Next.js project.

## Task

Scan the codebase and build a component index that the feature-generator can use
to reuse existing components instead of generating duplicates.

## Step 1 — Discover components

Glob: components/**/*.tsx, app/_components/**/*.tsx, ui/**/*.tsx
For each file:
  - Extract the default export component name
  - Extract all named prop types from the function signature or Props interface
  - Extract any JSDoc comments (/** ... */)
  - Note whether it's a 'use client' component or server component
  - Extract the import path relative to project root

## Step 2 — Write components.json

Write to components.json at project root:

{
  "generated_at": "[ISO timestamp]",
  "components": [
    {
      "name": "Button",
      "file": "components/ui/Button.tsx",
      "type": "client",
      "props": ["variant: 'primary' | 'secondary' | 'ghost'", "size: 'sm' | 'md' | 'lg'", "onClick: () => void", "disabled?: boolean", "children: ReactNode"],
      "description": "Primary action button with variant and size support",
      "usage_example": "<Button variant=\"primary\" size=\"md\">Save Changes</Button>"
    }
  ]
}

## Step 3 — Log

Write one line to .cursor/agent-log.txt:
"[DATE] COMPONENT INDEX: N components indexed → components.json"
