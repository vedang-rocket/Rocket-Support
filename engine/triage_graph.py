"""
triage_graph.py — Linear triage pipeline for rkt.

Pipeline (all nodes always run in order):
  fingerprint → chain_walker → schema → semgrep → fs_checks
              → context_filter → deduplicate → db_lookup
              → score_and_route → symptom_rank → validate_fix → build_summary

Entry point:
  run_triage(workspace_path, issue_description, port) -> final state dict
"""

import os
import sys
import time
from typing import Any, Dict, List, Optional

from typing_extensions import TypedDict

# ── Engine imports (call existing functions, never rewrite) ───────────────────

ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ENGINE_DIR)

import fingerprint as fp
import chain_walker
import schema_checker
import rkt_engine
import db as fix_db
import tracer as _tracer
from context_filter import filter_findings
from dedup import deduplicate
from symptom_ranker import rank_findings

try:
    import probe_scanner as _probe_scanner
    _PROBE_AVAILABLE = True
except ImportError:
    _PROBE_AVAILABLE = False


# ── State schema ──────────────────────────────────────────────────────────────

class TriageState(TypedDict):
    workspace_path:     str
    issue_description:  str
    port:               int

    fingerprint:        dict
    cw_findings:        list
    schema_findings:    list
    semgrep_findings:   list
    fs_issues:          list
    db_match:           Optional[dict]

    # After context_filter
    filtered_findings:  list          # active (non-suppressed) pre-score entries
    suppressed_findings: list         # [{...entry, suppression_reason}]

    # After deduplicate
    deduped_findings:   list          # cross-layer merged pre-score entries

    # After score_and_route
    findings_scored:    list          # [{source, finding, fix_mode, confidence, evidence, symptom_match}]
    overall_confidence: float
    primary_category:   str
    fix_mode:           str           # AUTO | GUIDED | CLAUDE | MANUAL
    auto_fixable_count: int

    # After symptom_rank
    symptom_category:   Optional[str]

    # After validate_fix (oxc gate — empty list means all valid or oxc not installed)
    fix_plan:               Optional[Any]
    oxc_validation_errors:  list
    oxc_context:            str

    timings:            dict
    summary:            str


# ── Scoring helpers ───────────────────────────────────────────────────────────

def _score_cw_finding(f: Dict[str, Any]) -> tuple:
    """Return (fix_mode, confidence) for a chain_walker finding."""
    chain = (f.get("chain") or "").upper()
    issue = (f.get("issue") or "").lower()
    broken_at = (f.get("broken_at") or "").lower()

    if chain == "STRIPE":
        return ("AUTO", 0.99)
    if chain == "AUTH":
        if "middleware" in issue or "middleware" in broken_at:
            return ("MANUAL", 0.85)
        if "server.ts" in broken_at:
            return ("AUTO", 0.97)
    return ("GUIDED", 0.75)


def _score_semgrep_finding(f: Dict[str, Any]) -> tuple:
    """Return (fix_mode, confidence) for a semgrep finding."""
    rule_id = (f.get("check_id") or "").lower()

    if rule_id == "probe-scanner-failed":
        return ("MANUAL", 0.20)
    if any(kw in rule_id for kw in ("webhook", "cookies", "auth-helpers")):
        return ("AUTO", 0.97)
    if "missing-dynamic" in rule_id or "dynamic" in rule_id:
        return ("AUTO", 0.95)
    if "getsession" in rule_id or "get-session" in rule_id:
        return ("AUTO", 0.97)
    return ("GUIDED", 0.75)


def _score_schema_finding(f: Dict[str, Any]) -> tuple:
    """Return (fix_mode, confidence) for a schema_checker finding."""
    check = (f.get("check") or "").lower()
    if "rls" in check:
        return ("GUIDED", 0.88)
    if "trigger" in check or "on_auth" in check:
        return ("GUIDED", 0.90)
    return ("GUIDED", 0.72)


def _overall_fix_mode(avg_conf: float, auto_count: int) -> str:
    if avg_conf >= 0.85 and auto_count > 0:
        return "AUTO"
    if avg_conf >= 0.60:
        return "GUIDED"
    if avg_conf >= 0.40:
        return "CLAUDE"
    return "MANUAL"


# ── Graph nodes ───────────────────────────────────────────────────────────────

def node_fingerprint(state: TriageState) -> dict:
    t0 = time.perf_counter()
    with _tracer.trace("PHASE2", "fingerprint") as trace_token:
        result = fp.fingerprint(state["workspace_path"])
        trace_token.set_result(
            result,
            f"type={result.get('project_type', 'Unknown')} confidence={result.get('confidence', 0):.2f}",
        )
    elapsed = (time.perf_counter() - t0) * 1000
    timings = dict(state.get("timings") or {})
    timings["fingerprint_ms"] = round(elapsed, 1)
    return {"fingerprint": result, "timings": timings}


def node_chain_walker(state: TriageState) -> dict:
    t0 = time.perf_counter()
    with _tracer.trace("PHASE2", "chain_walker") as trace_token:
        findings = chain_walker.walk(state["workspace_path"])
        trace_token.set_result(findings, f"findings={len(findings)}")
        logger = _tracer.get_logger()
        if logger:
            logger.set_finding("chain_walker findings", len(findings))
    elapsed = (time.perf_counter() - t0) * 1000
    timings = dict(state.get("timings") or {})
    timings["chain_walker_ms"] = round(elapsed, 1)
    return {"cw_findings": findings, "timings": timings}


def node_schema(state: TriageState) -> dict:
    t0 = time.perf_counter()
    with _tracer.trace("PHASE2", "schema_checker") as trace_token:
        findings = schema_checker.check(state["workspace_path"])
        fail_count = len(schema_checker.failures(findings)) if findings else 0
        trace_token.set_result(findings, f"findings={fail_count}")
        logger = _tracer.get_logger()
        if logger:
            logger.set_finding("schema_checker findings", fail_count)
    elapsed = (time.perf_counter() - t0) * 1000
    timings = dict(state.get("timings") or {})
    timings["schema_ms"] = round(elapsed, 1)
    return {"schema_findings": findings, "timings": timings}


def node_semgrep(state: TriageState) -> dict:
    t0 = time.perf_counter()
    tool_name = "probe_scanner" if _PROBE_AVAILABLE else "semgrep"
    with _tracer.trace("PHASE2", tool_name) as trace_token:
        if _PROBE_AVAILABLE:
            result = _probe_scanner.run_probe_scanner(state["workspace_path"])
        else:
            result = rkt_engine.run_semgrep(state["workspace_path"], autofix=False)
        trace_findings = list(result.get("findings") or [])
        trace_token.set_result(trace_findings, f"findings={len(trace_findings)}")
        logger = _tracer.get_logger()
        if logger:
            logger.set_finding("probe_scanner findings", len(trace_findings))
    elapsed = (time.perf_counter() - t0) * 1000
    timings = dict(state.get("timings") or {})
    timings["semgrep_ms"] = round(elapsed, 1)
    findings = list(result.get("findings") or [])
    errors = result.get("errors", []) or []
    available = result.get("available", True)

    if (available is False) or (not findings and errors):
        scanner_name = "probe" if _PROBE_AVAILABLE else "semgrep"
        errors_text = "; ".join(str(e) for e in errors) if errors else "scanner unavailable"
        findings.append(
            {
                "source": "probe",
                "check_id": "probe-scanner-failed",
                "path": state["workspace_path"],
                "start": {"line": 1, "col": 1},
                "end": {"line": 1, "col": 1},
                "extra": {
                    "message": f"{scanner_name} scan unreliable: {errors_text}",
                    "severity": "ERROR",
                    "fix": "",
                    "metadata": {"category": "BUILD", "confidence": "LOW"},
                },
            }
        )
    return {"semgrep_findings": findings, "timings": timings}


def node_fs_checks(state: TriageState) -> dict:
    t0 = time.perf_counter()
    with _tracer.trace("PHASE2", "fs_checks") as trace_token:
        issues = rkt_engine.fs_checks(state["workspace_path"])
        trace_token.set_result(issues, f"findings={len(issues)}")
    elapsed = (time.perf_counter() - t0) * 1000
    timings = dict(state.get("timings") or {})
    timings["fs_checks_ms"] = round(elapsed, 1)
    return {"fs_issues": issues, "timings": timings}


def node_context_filter(state: TriageState) -> dict:
    t0 = time.perf_counter()
    workspace = state["workspace_path"]

    # Wrap raw findings with source tags for filter_findings
    raw: List[Dict[str, Any]] = []
    for f in (state.get("cw_findings") or []):
        raw.append({"source": "chain_walker", "finding": f, "fix_mode": "GUIDED", "confidence": 0.75})
    _scan_src = "probe" if _PROBE_AVAILABLE else "semgrep"
    for f in (state.get("semgrep_findings") or []):
        raw.append({"source": _scan_src, "finding": f, "fix_mode": "GUIDED", "confidence": 0.75})
    for f in (state.get("fs_issues") or []):
        raw.append({"source": "fs_checks", "finding": f, "fix_mode": "GUIDED", "confidence": 0.75})
    for f in (state.get("schema_findings") or []):
        if not f.get("found", True):  # found=False means the required pattern is missing
            mode, conf = _score_schema_finding(f)
            raw.append({"source": "schema", "finding": f, "fix_mode": mode, "confidence": conf})

    with _tracer.trace("PHASE2", "context_filter") as trace_token:
        result = filter_findings(raw, workspace)
        trace_token.set_output(f"in={len(raw)} out={len(result.get('active', []))}")
    elapsed = (time.perf_counter() - t0) * 1000
    timings = dict(state.get("timings") or {})
    timings["context_filter_ms"] = round(elapsed, 1)
    return {
        "filtered_findings": result["active"],
        "suppressed_findings": result["suppressed"],
        "timings": timings,
    }


def node_deduplicate(state: TriageState) -> dict:
    t0 = time.perf_counter()
    before = state.get("filtered_findings") or []
    with _tracer.trace("PHASE2", "dedup") as trace_token:
        deduped = deduplicate(before)
        trace_token.set_output(f"in={len(before)} out={len(deduped)}")
        logger = _tracer.get_logger()
        if logger:
            logger.set_finding("after dedup", len(deduped))
    elapsed = (time.perf_counter() - t0) * 1000
    timings = dict(state.get("timings") or {})
    timings["dedup_ms"] = round(elapsed, 1)
    return {"deduped_findings": deduped, "timings": timings}


def node_symptom_rank(state: TriageState) -> dict:
    t0 = time.perf_counter()
    with _tracer.trace("PHASE2", "symptom_ranker") as trace_token:
        ranked, symptom_cat = rank_findings(
            state.get("findings_scored") or [],
            state.get("issue_description") or "",
        )
        top = ""
        if ranked:
            top = (ranked[0].get("finding") or {}).get("chain") or ranked[0].get("source", "")
        trace_token.set_output(f"top={top or '-'} symptom={symptom_cat or '-'}")
        logger = _tracer.get_logger()
        if logger and top:
            logger.set_finding("top finding", top)
    elapsed = (time.perf_counter() - t0) * 1000
    timings = dict(state.get("timings") or {})
    timings["symptom_rank_ms"] = round(elapsed, 1)
    return {
        "findings_scored": ranked,
        "symptom_category": symptom_cat,
        "timings": timings,
    }


def node_db_lookup(state: TriageState) -> dict:
    t0 = time.perf_counter()
    fp_result  = state.get("fingerprint") or {}
    category   = fp_result.get("category")
    query = state["issue_description"].strip() or fp_result.get("common_failure", "")
    match = rkt_engine.db_lookup(query.strip(), category=category)
    elapsed = (time.perf_counter() - t0) * 1000
    timings = dict(state.get("timings") or {})
    timings["db_lookup_ms"] = round(elapsed, 1)
    return {"db_match": match, "timings": timings}


def node_score_and_route(state: TriageState) -> dict:
    with _tracer.trace("PHASE3", "score_and_route") as trace_token:
        result = _score_and_route_impl(state)
        trace_token.set_output(
            f"mode={result.get('fix_mode')} confidence={result.get('overall_confidence')}"
        )
        return result


def _score_and_route_impl(state: TriageState) -> dict:
    scored: List[Dict[str, Any]] = []

    # Score deduped pre-scored entries (produced by node_deduplicate)
    for entry in (state.get("deduped_findings") or []):
        src = entry.get("source", "")
        f = entry.get("finding", {})
        evidence = entry.get("evidence", [src])

        if src == "chain_walker":
            mode, conf = _score_cw_finding(f)
        elif src in ("semgrep", "probe"):
            mode, conf = _score_semgrep_finding(f)
        elif src == "schema":
            mode, conf = _score_schema_finding(f)
        else:
            mode, conf = "GUIDED", 0.75

        # Merged entries already have promoted confidence from dedup step
        merged_conf = entry.get("confidence", conf)
        if merged_conf > conf:
            conf = merged_conf

        scored.append({
            "source": src,
            "finding": f,
            "fix_mode": mode,
            "confidence": conf,
            "evidence": evidence,
        })

    # Compute overall
    auto_count = sum(1 for s in scored if s["fix_mode"] == "AUTO")
    if scored:
        avg_conf = sum(s["confidence"] for s in scored) / len(scored)
    else:
        avg_conf = 0.0

    # db_match boosts confidence when no direct findings exist or findings are weak.
    # Cap at 0.74 (high-MED) — a pattern match alone never triggers AUTO.
    db_match = state.get("db_match")
    if db_match and (not scored or avg_conf < 0.60):
        db_conf = min(float(db_match.get("_score", 0.75)), 0.74)
        if db_conf > avg_conf:
            avg_conf = db_conf

    overall_mode = _overall_fix_mode(avg_conf, auto_count)

    # Primary category from fingerprint or most common finding
    fp_result = state.get("fingerprint") or {}
    primary_category = fp_result.get("category") or "OTHER"

    return {
        "findings_scored":    scored,
        "overall_confidence": round(avg_conf, 3),
        "primary_category":   primary_category,
        "fix_mode":           overall_mode,
        "auto_fixable_count": auto_count,
    }


# Available for future use when fix_plan is populated at triage time.
# Not in _PIPELINE — fix_plan is built in diagnose_output.py after run_triage().
def node_validate_fix(state: TriageState) -> dict:
    """Run oxlint on any fix proposals if oxc is available. Non-blocking."""
    fix_plan = state.get("fix_plan")
    if not fix_plan:
        return {}
    try:
        import sys as _sys
        _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from fix_validator import validate_fix_plan, validation_errors_to_context
        workspace = state.get("workspace_path", "")
        errors = validate_fix_plan(fix_plan, workspace)
        if errors:
            ctx = validation_errors_to_context(errors)
            return {"oxc_validation_errors": errors, "oxc_context": ctx}
    except Exception:
        pass
    return {"oxc_validation_errors": []}


def node_build_summary(state: TriageState) -> dict:
    fp_result   = state.get("fingerprint") or {}
    scored      = state.get("findings_scored") or []
    suppressed  = state.get("suppressed_findings") or []
    db_match    = state.get("db_match")
    timings     = state.get("timings") or {}
    total_ms    = sum(timings.values())
    symptom_cat = state.get("symptom_category")

    lines = []

    # Header
    lines.append("═" * 60)
    lines.append(f"  RKT TRIAGE REPORT")
    lines.append("═" * 60)

    # Project
    lines.append(f"  Project type : {fp_result.get('project_type', 'Unknown')}  "
                 f"(confidence {fp_result.get('confidence', 0):.0%})")
    lines.append(f"  Next.js      : {fp_result.get('next_version') or 'unknown'}")
    lines.append(f"  Supabase     : {'yes' if fp_result.get('has_supabase') else 'no'}  "
                 f"Stripe: {'yes' if fp_result.get('has_stripe') else 'no'}")
    lines.append(f"  Port         : {state.get('port', 3000)}")
    lines.append("")

    # Issue
    lines.append(f"  Issue        : {state.get('issue_description', '')}")
    if symptom_cat:
        lines.append(f"  Symptom cat  : {symptom_cat} (matched from issue description)")
    lines.append(f"  Fix mode     : {state.get('fix_mode', '?')}  "
                 f"(avg confidence {state.get('overall_confidence', 0):.0%})")
    lines.append(f"  Auto-fixable : {state.get('auto_fixable_count', 0)} finding(s)")
    lines.append("")

    # Active findings
    if scored:
        lines.append("  FINDINGS:")
        for s in scored:
            src      = s["source"]
            f        = s["finding"]
            mode     = s["fix_mode"]
            conf     = s["confidence"]
            evidence = s.get("evidence", [src])
            matched  = s.get("symptom_match", False)
            ev_str   = "+".join(evidence) if len(evidence) > 1 else src
            tag      = f"[{mode}:{conf:.0%}]"
            marker   = "★ " if matched else "  "

            if src == "chain_walker":
                msg = f.get("issue", "")
            elif src in ("semgrep", "probe"):
                rule = (f.get("check_id") or "").split(".")[-1]
                path = f.get("path", "")
                line = f.get("start", {}).get("line", "?")
                msg  = f"{rule} @ {path}:{line}"
            elif src == "schema":
                msg = f.get("fix_hint") or f.get("check", "")
            else:  # fs_checks
                msg = f.get("message", "")

            confirmed = "  ✓ confirmed" if len(evidence) > 1 else ""
            lines.append(f"  {marker}{tag:18s} [{ev_str:20s}] {msg}{confirmed}")
    else:
        lines.append("  FINDINGS: none")
    lines.append("")

    # Suppressed
    if suppressed:
        lines.append(f"  SUPPRESSED ({len(suppressed)}): ")
        for s in suppressed:
            src = s.get("source", "")
            f = s.get("finding", {})
            reason = s.get("suppression_reason", "")
            path = f.get("path") or f.get("broken_at") or ""
            lines.append(f"    [{src}] {path} — {reason}")
        lines.append("")

    # DB match
    if db_match:
        lines.append(f"  KNOWN FIX    : {db_match.get('pattern', '')}")
        lines.append(f"  Category     : {db_match.get('category', '')}  "
                     f"(score {db_match.get('_score', 0):.2f})")
    lines.append("")

    # Timings
    timing_str = "  ".join(f"{k}={v:.0f}ms" for k, v in timings.items())
    lines.append(f"  Timings: {timing_str}  total={total_ms:.0f}ms")
    lines.append("═" * 60)

    return {"summary": "\n".join(lines)}


# ── Pipeline definition ───────────────────────────────────────────────────────

_PIPELINE = [
    node_fingerprint,
    node_chain_walker,
    node_schema,
    node_semgrep,
    node_fs_checks,
    node_context_filter,
    node_deduplicate,
    node_db_lookup,
    node_score_and_route,
    node_symptom_rank,
    node_build_summary,
]


# ── Public entry point ────────────────────────────────────────────────────────

def run_triage(workspace_path: str, issue_description: str, port: int = 3000) -> Dict:
    _tracer.init_if_env()
    state: Dict = {
        "workspace_path":      os.path.abspath(os.path.expanduser(workspace_path)),
        "issue_description":   issue_description,
        "port":                port,
        "fingerprint":         {},
        "cw_findings":         [],
        "schema_findings":     [],
        "semgrep_findings":    [],
        "fs_issues":           [],
        "db_match":            None,
        "filtered_findings":   [],
        "suppressed_findings": [],
        "deduped_findings":    [],
        "findings_scored":     [],
        "overall_confidence":  0.0,
        "primary_category":    "OTHER",
        "fix_mode":            "MANUAL",
        "auto_fixable_count":  0,
        "symptom_category":    None,
        "fix_plan":            None,
        "oxc_validation_errors": [],
        "oxc_context":         "",
        "timings":             {},
        "summary":             "",
    }
    for node_fn in _PIPELINE:
        state.update(node_fn(state))
    return state
