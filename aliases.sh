# ============================================================
#  Rocket.new Support Engineer aliases
#  Add to your ~/.zshrc:  source ~/rocket-support/aliases.sh
# ============================================================

export RKT_HOME="$HOME/rocket-support"
export PATH="$RKT_HOME/bin:$PATH"

# ── core commands ────────────────────────────────────────
# rkt <url>             — full headless diagnose + fix
# rkt-open <url>        — interactive session (complex issues)
# rkt --parallel <urls> — 3-5 repos at once

# ── speed aliases ────────────────────────────────────────
alias rktl="rkt --log"                    # show recent queries
alias rktu="rkt --update"                 # pull latest patterns

# ── tmux layout for parallel work ────────────────────────
# Opens 4 panes — one per query
rkt-multi() {
  if [[ $# -eq 0 ]]; then
    echo "Usage: rkt-multi <url1> <url2> [url3] [url4]"
    return 1
  fi

  local urls=("$@")
  local session="rkt-support-$$"

  # Create tmux session
  tmux new-session -d -s "$session" -x 220 -y 50

  # First pane — first URL
  tmux send-keys -t "$session" "rkt ${urls[0]}" Enter

  # Additional panes
  for i in "${!urls[@]}"; do
    [[ $i -eq 0 ]] && continue
    tmux split-window -t "$session" -h 2>/dev/null || tmux split-window -t "$session" -v
    tmux send-keys -t "$session" "rkt ${urls[$i]}" Enter
    tmux select-layout -t "$session" tiled
  done

  # Attach
  tmux attach-session -t "$session"
}

# ── quick diagnosis without cloning ──────────────────────
# Paste an error message, get the likely fix immediately
rkt-error() {
  local error_msg="$1"
  echo "$error_msg" | claude -p \
    "You are a Rocket.new expert. This is an error from a Rocket.new project (Next.js + Supabase + Tailwind + Netlify).
     Give me the exact fix in under 5 lines. No explanation, just the fix.
     Error: $error_msg" \
    --append-system-prompt "$(cat "$RKT_HOME/CLAUDE.md")" \
    --output-format text
}

# ── check if a repo has the most common issues ───────────
# Fast scan without full Claude — pure bash, <5 seconds
rkt-scan() {
  local url="$1"
  local tmp="/tmp/rkt-scan-$$"
  git clone --depth=1 --quiet "$url" "$tmp" 2>/dev/null

  echo "=== Quick scan: $(basename "$url" .git) ==="

  # Auth
  local session_hits
  session_hits=$(grep -rn "getSession()" "$tmp/app" "$tmp/lib" "$tmp/middleware.ts" 2>/dev/null | wc -l | tr -d ' ')
  [[ "$session_hits" -gt 0 ]] && echo "❌ AUTH: getSession() found ($session_hits times)" || echo "✓  Auth pattern ok"

  # Middleware
  [[ -f "$tmp/middleware.ts" ]] && echo "✓  Middleware at root" || echo "❌ MIDDLEWARE: missing from root"
  [[ -f "$tmp/app/middleware.ts" ]] && echo "❌ MIDDLEWARE: in /app (wrong!)"

  # Supabase package
  grep -q "auth-helpers-nextjs" "$tmp/package.json" 2>/dev/null && echo "❌ SUPABASE: deprecated auth-helpers" || echo "✓  Supabase package ok"

  # Stripe
  grep -rn "request\.json()" "$tmp/app/api/webhooks" 2>/dev/null | grep -q . && echo "❌ STRIPE: request.json() in webhook" || echo "✓  Stripe webhook ok"

  # Env
  for v in NEXT_PUBLIC_SUPABASE_URL NEXT_PUBLIC_SUPABASE_ANON_KEY SUPABASE_SERVICE_ROLE_KEY; do
    grep -q "^$v=" "$tmp/.env" "$tmp/.env.local" 2>/dev/null && echo "✓  $v" || echo "❌ ENV: $v missing"
  done

  rm -rf "$tmp"
}


