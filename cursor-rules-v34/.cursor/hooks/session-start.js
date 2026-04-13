#!/usr/bin/env node
/**
 * sessionStart Hook
 * Loads previous session summary into Claude's context automatically.
 * Runs before the user types their first message.
 *
 * stdout → injected into Claude's context
 * stderr → shown as user-facing messages
 */
const { readStdin, hookEnabled } = require('./adapter');
const fs = require('fs');
const path = require('path');
const os = require('os');

function getSessionsDir() {
  return path.join(process.cwd(), '.cursor', 'sessions');
}

function getInstinctsDir() {
  return path.join(process.cwd(), 'memory-bank', 'instincts');
}

function detectProjectType() {
  const cwd = process.cwd();
  const pkg = path.join(cwd, 'package.json');
  const env = path.join(cwd, '.env');
  const envLocal = path.join(cwd, '.env.local');

  const signals = [];

  if (fs.existsSync(pkg)) {
    try {
      const p = JSON.parse(fs.readFileSync(pkg, 'utf8'));
      const deps = { ...p.dependencies, ...p.devDependencies };
      if (deps['stripe']) signals.push('stripe');
      if (deps['openai'] || deps['@anthropic-ai/sdk']) signals.push('ai');
      if (deps['@supabase/ssr'] || deps['@supabase/supabase-js']) signals.push('supabase');
      if (deps['next']) signals.push('nextjs');
      if (deps['react'] && !deps['next']) signals.push('react-vite');
    } catch (_) {}
  }

  const envFile = fs.existsSync(envLocal) ? envLocal : fs.existsSync(env) ? env : null;
  if (envFile) {
    const content = fs.readFileSync(envFile, 'utf8');
    if (/STRIPE_SECRET_KEY/.test(content)) signals.push('stripe');
    if (/OPENAI_API_KEY|ANTHROPIC_API_KEY/.test(content)) signals.push('ai');
    if (/NEXT_PUBLIC_SUPABASE/.test(content)) signals.push('supabase');
  }

  if (signals.includes('stripe') && signals.includes('supabase')) return 'SaaS App';
  if (signals.includes('ai') && signals.includes('supabase')) return 'AI App';
  if (signals.includes('stripe')) return 'E-Commerce/SaaS';
  if (signals.includes('nextjs')) return 'Next.js App';
  if (signals.includes('react-vite')) return 'React Vite App';
  return 'Rocket.new Web App';
}

async function main() {
  if (!hookEnabled('session:start', ['minimal', 'standard', 'strict'])) {
    process.exit(0);
  }

  const sessionsDir = getSessionsDir();
  const instinctsDir = getInstinctsDir();
  const contextParts = [];

  // Load most recent session summary
  if (fs.existsSync(sessionsDir)) {
    const files = fs.readdirSync(sessionsDir)
      .filter(f => f.endsWith('.log'))
      .sort()
      .reverse();

    if (files.length > 0) {
      const latest = path.join(sessionsDir, files[0]);
      const content = fs.readFileSync(latest, 'utf8');
      if (content && content.trim().length > 50) {
        contextParts.push(`## Previous Session Summary\n${content.slice(0, 1500)}`);
      }
    }
  }

  // Load memory-bank context
  const activeIssues = path.join(process.cwd(), 'memory-bank', 'active-issues.md');
  if (fs.existsSync(activeIssues)) {
    const content = fs.readFileSync(activeIssues, 'utf8').trim();
    if (content && !content.includes('<!-- Auto-written') && content.length > 30) {
      contextParts.push(`## Active Issues\n${content.slice(0, 800)}`);
    }
  }

  // Count instincts available
  if (fs.existsSync(instinctsDir)) {
    const instincts = fs.readdirSync(instinctsDir).filter(f => f.endsWith('.yaml'));
    if (instincts.length > 0) {
      contextParts.push(`## Instincts Available\n${instincts.length} learned instinct(s) in memory-bank/instincts/\nRun /instinct-status to review them before starting.`);
    }
  }

  // Detect project type
  const projectType = detectProjectType();
  contextParts.push(`## Project Context\nType: ${projectType} | Stack: Next.js + Supabase @supabase/ssr + Tailwind + Netlify`);

  if (contextParts.length > 0) {
    process.stdout.write(contextParts.join('\n\n') + '\n');
  }

  process.exit(0);
}

main().catch(() => process.exit(0));
