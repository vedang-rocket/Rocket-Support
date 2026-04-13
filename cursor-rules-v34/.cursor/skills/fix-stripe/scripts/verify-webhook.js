#!/usr/bin/env node
/**
 * Stripe Setup Verification Script
 * Run: node .cursor/skills/fix-stripe/scripts/verify-webhook.js
 * 
 * Checks your Stripe environment configuration before debugging
 */

const fs = require('fs')
const path = require('path')

// Load .env.local
// Rocket uses .env; Next.js standard is .env.local — check both
let envPath = path.join(process.cwd(), '.env')
if (!fs.existsSync(envPath)) envPath = path.join(process.cwd(), '.env.local')
