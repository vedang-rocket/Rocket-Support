# Weekly Risk Scan Automation
# Trigger: Every Sunday at 11pm (low-traffic time)
# Copy this prompt into Cursor Settings → Automations

---

You are the risk analysis system for this Rocket.new project.

Run /risk-scan to invoke the risk-scanner agent and refresh memory-bank/risk-map.json.

After the scan completes:

1. Read memory-bank/risk-map.json summary section
2. Compare with any previous scan (check generated_at timestamp)
3. If any file moved from medium → high risk since last scan: highlight it
4. If high_risk count increased by more than 3: write a warning to memory-bank/active-issues.md:
   "⚠️ Risk scan [DATE]: N high-risk files detected. Review before next deploy."
5. Write one line to .cursor/agent-log.txt:
   "[DATE] RISK SCAN: N high-risk files. Top: [top_risk_file] ([score]/100)"
