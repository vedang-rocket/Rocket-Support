"""
dedup.py — Cross-layer deduplication of triage findings.

When chain_walker and semgrep both flag the same bug in the same file+category,
merge them into one finding with combined evidence and auto-promoted confidence.

Match criteria (all must be true):
  - Same normalised file path
  - Same category
  - Different source layers
  - Line numbers within LINE_PROXIMITY (semgrep only; chain_walker has no line → match on file+category)

Confidence promotion:
  Two independent sources agreeing → promote one tier: LOW→MED, MED→HIGH, HIGH stays HIGH.
"""

from typing import Any, Dict, List, Set

LINE_PROXIMITY = 5

_CONF_TO_TIER = {"LOW": 1, "MED": 2, "HIGH": 3}
_TIER_TO_FLOAT = {1: 0.65, 2: 0.82, 3: 0.97}


def _conf_label(conf: float) -> str:
    if conf >= 0.90:
        return "HIGH"
    if conf >= 0.70:
        return "MED"
    return "LOW"


def _promote(conf: float) -> float:
    label = _conf_label(conf)
    tier = _CONF_TO_TIER.get(label, 2)
    return _TIER_TO_FLOAT[min(tier + 1, 3)]


def _norm_path(finding: Dict[str, Any], source: str) -> str:
    if source == "semgrep":
        return finding.get("path", "")
    if source == "chain_walker":
        return finding.get("broken_at", "")
    return finding.get("file", "")


def _line(finding: Dict[str, Any], source: str) -> int:
    if source == "semgrep":
        return finding.get("start", {}).get("line", 0)
    return 0  # chain_walker has no line number


def _category(entry: Dict[str, Any]) -> str:
    f = entry.get("finding", {})
    chain = (f.get("chain") or "").upper()
    if chain:
        return chain
    rule_id = (f.get("check_id") or "").lower()
    if any(kw in rule_id for kw in ("auth", "session", "getuser", "dynamic", "middleware", "cookies")):
        return "AUTH"
    if any(kw in rule_id for kw in ("stripe", "webhook")):
        return "STRIPE"
    if any(kw in rule_id for kw in ("supabase", "rls", "timestamptz")):
        return "SUPABASE"
    return "OTHER"


def _lines_close(a: int, b: int) -> bool:
    if a == 0 or b == 0:
        return True  # one side has no line → match on file+category only
    return abs(a - b) <= LINE_PROXIMITY


def deduplicate(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Merge findings from different sources that flag the same bug.

    Input: scored finding entries (each: source, finding, fix_mode, confidence).
    Output: deduplicated list.
      - Merged findings get "evidence": [src1, src2, ...]
      - Single-source findings get "evidence": [src]
      - Merged confidence is promoted one tier above the best member's tier.
    """
    used: Set[int] = set()
    output: List[Dict[str, Any]] = []

    for i, entry_a in enumerate(findings):
        if i in used:
            continue

        src_a = entry_a.get("source", "")
        f_a = entry_a.get("finding", {})
        path_a = _norm_path(f_a, src_a)
        line_a = _line(f_a, src_a)
        cat_a = _category(entry_a)

        partners: List[int] = []

        for j, entry_b in enumerate(findings):
            if j <= i or j in used:
                continue
            src_b = entry_b.get("source", "")
            if src_b == src_a:
                continue  # same layer — not a cross-layer duplicate
            f_b = entry_b.get("finding", {})
            path_b = _norm_path(f_b, src_b)
            line_b = _line(f_b, src_b)
            cat_b = _category(entry_b)

            if path_a and path_a == path_b and cat_a == cat_b and _lines_close(line_a, line_b):
                partners.append(j)

        if partners:
            partner_entries = [findings[j] for j in partners]
            all_sources = [src_a] + [findings[j].get("source", "") for j in partners]
            best_conf = max(
                [entry_a.get("confidence", 0.0)] + [findings[j].get("confidence", 0.0) for j in partners]
            )
            merged = {
                **entry_a,
                "confidence": _promote(best_conf),
                "evidence": all_sources,
            }
            output.append(merged)
            used.add(i)
            for j in partners:
                used.add(j)
        else:
            output.append({**entry_a, "evidence": [src_a]})
            used.add(i)

    return output
