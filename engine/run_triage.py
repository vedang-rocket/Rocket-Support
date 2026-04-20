#!/usr/bin/env python3
"""Clean wrapper for triage_graph — no progress noise, just JSON output."""
import sys
import os
import json
import warnings

warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import triage_graph as tg


def main():
    repo_path = sys.argv[1] if len(sys.argv) > 1 else ""
    issue     = sys.argv[2] if len(sys.argv) > 2 else ""
    port      = int(sys.argv[3]) if len(sys.argv) > 3 else 3000

    if not repo_path or not os.path.isdir(repo_path):
        print(json.dumps({"error": f"Invalid path: {repo_path}"}))
        sys.exit(1)

    state = tg.run_triage(repo_path, issue, port)

    fp = state.get("fingerprint") or {}

    def _serialise_finding(s):
        src     = s.get("source", "")
        f       = s.get("finding", {})
        conf    = s.get("confidence", 0.0)
        mode    = s.get("fix_mode", "")
        ev      = s.get("evidence", [src])
        matched = s.get("symptom_match", False)

        if src == "chain_walker":
            file_path = f.get("broken_at", "")
            line      = 0
            desc      = f.get("issue", "")
            fix_hint  = f.get("fix", "")
            category  = (f.get("chain") or "").upper()
        elif src == "semgrep":
            file_path = f.get("path", "")
            line      = f.get("start", {}).get("line", 0)
            desc      = f.get("extra", {}).get("message", "")[:120]
            fix_hint  = f.get("extra", {}).get("fix", "")
            rule_id   = (f.get("check_id") or "").split(".")[-1]
            category  = rule_id
        else:
            file_path = f.get("file", "")
            line      = f.get("line", 0)
            desc      = f.get("message", "")
            fix_hint  = ""
            category  = ""

        return {
            "fix_mode":      mode,
            "confidence":    round(conf, 3),
            "source":        src,
            "evidence":      ev,
            "symptom_match": matched,
            "category":      category,
            "file":          file_path,
            "line":          line,
            "description":   desc,
            "fix_hint":      fix_hint,
        }

    result = {
        "fix_mode":           state.get("fix_mode", "MANUAL"),
        "workspace_path":     repo_path,
        "issue_description":  issue,
        "overall_confidence": state.get("overall_confidence", 0),
        "auto_fixable_count": state.get("auto_fixable_count", 0),
        "summary":            state.get("summary", ""),
        "primary_category":   state.get("primary_category", "UNKNOWN"),
        "symptom_category":   state.get("symptom_category"),
        "fingerprint": {
            "project_type":   fp.get("project_type", "Unknown"),
            "next_version":   fp.get("next_version", ""),
            "has_supabase":   fp.get("has_supabase", False),
            "has_stripe":     fp.get("has_stripe", False),
        },
        "findings_scored": [_serialise_finding(s) for s in state.get("findings_scored", [])],
    }

    result_file = "/tmp/rkt_triage_result.json"
    with open(result_file, "w") as f:
        json.dump(result, f)

    # Print summary to stdout for bash to capture and display
    print(result["summary"])


if __name__ == "__main__":
    main()
