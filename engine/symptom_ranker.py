"""
symptom_ranker.py — Re-rank triage findings by client-reported symptom.

Parses the issue description into a category signal (AUTH, STRIPE, SUPABASE,
BUILD, ENV). Findings whose category matches are moved to the front.
Each finding gains a "symptom_match": bool flag.
"""

from typing import Any, Dict, List, Optional, Tuple

SYMPTOM_MAP: Dict[str, List[str]] = {
    "AUTH": [
        "auth", "login", "logout", "session", "token", "jwt", "oauth",
        "redirect", "not authenticated", "unauthorized", "sign in", "sign up",
        "protected", "middleware",
    ],
    "STRIPE": [
        "stripe", "webhook", "payment", "checkout", "subscription", "400",
        "billing", "charge", "invoice", "webhook 400",
    ],
    "SUPABASE": [
        "supabase", "rls", "row level", "policy", "trigger", "profile",
        "dashboard blank", "empty array", "no data", "not showing", "blank",
    ],
    "BUILD": [
        "build", "deploy", "netlify", "vercel", "typescript", "tsc",
        "type error", "compile", "failed to build", "build fails",
    ],
    "ENV": [
        "env", "api key", "secret", "environment variable", "invalid key",
        "anon key", "publishable", "missing key", "invalid api",
    ],
}

_CATEGORY_ALIASES: Dict[str, str] = {
    "AUTH":     "AUTH",
    "STRIPE":   "STRIPE",
    "RLS":      "SUPABASE",
    "SUPABASE": "SUPABASE",
    "BUILD":    "BUILD",
    "ENV":      "ENV",
}


def _detect_symptom_category(issue_description: str) -> Optional[str]:
    text = issue_description.lower()
    scores: Dict[str, int] = {}
    for category, keywords in SYMPTOM_MAP.items():
        hits = sum(1 for kw in keywords if kw in text)
        if hits > 0:
            scores[category] = hits
    if not scores:
        return None
    return max(scores, key=lambda k: scores[k])


def _finding_category(entry: Dict[str, Any]) -> str:
    f = entry.get("finding", {})

    # chain_walker uses "chain"
    chain = (f.get("chain") or "").upper()
    if chain:
        return _CATEGORY_ALIASES.get(chain, chain)

    # semgrep uses rule id keywords
    rule_id = (f.get("check_id") or "").lower()
    if any(kw in rule_id for kw in ("auth", "session", "getuser", "dynamic", "middleware", "auth-helpers", "cookies")):
        return "AUTH"
    if any(kw in rule_id for kw in ("stripe", "webhook")):
        return "STRIPE"
    if any(kw in rule_id for kw in ("supabase", "rls")):
        return "SUPABASE"
    if any(kw in rule_id for kw in ("timestamptz", "schema")):
        return "SUPABASE"

    return "OTHER"


def rank_findings(
    findings: List[Dict[str, Any]],
    issue_description: str,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    Re-rank findings by symptom match. Returns (ranked_findings, primary_symptom_category).

    Symptom-matched findings move to front, preserving internal order.
    Each entry gains "symptom_match": bool.
    """
    if not (issue_description or "").strip():
        return [{**f, "symptom_match": False} for f in findings], None

    primary_category = _detect_symptom_category(issue_description)

    matched: List[Dict[str, Any]] = []
    unmatched: List[Dict[str, Any]] = []

    for entry in findings:
        cat = _finding_category(entry)
        is_match = primary_category is not None and cat == primary_category
        tagged = {**entry, "symptom_match": is_match}
        if is_match:
            matched.append(tagged)
        else:
            unmatched.append(tagged)

    return matched + unmatched, primary_category
