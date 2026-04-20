"""
triage_graph.py — LangGraph StateGraph orchestrator for rkt triage pipeline.

Pipeline (linear, all nodes always run):
  fingerprint → chain_walker → schema → semgrep → fs_checks
              → context_filter → deduplicate → db_lookup
              → score_and_route → symptom_rank → build_summary → END

Entry point:
  run_triage(workspace_path, issue_description, port) -> final state dict
"""

import os
import sys
import time
from typing import Any, Dict, List, Optional

from typing_extensions import TypedDict
from langgraph.graph import StateGraph, END

# ── Engine imports (call existing functions, never rewrite) ───────────────────

ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ENGINE_DIR)

import fingerprint as fp
import chain_walker
import schema_checker
import rkt_engine
import db as fix_db
from context_filter import filter_findings
from dedup import deduplicate
from symptom_ranker import rank_findings


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

    if any(kw in rule_id for kw in ("webhook", "cookies", "auth-helpers")):
        return ("AUTO", 0.97)
    if "missing-dynamic" in rule_id or "dynamic" in rule_id:
        return ("AUTO", 0.95)
    if "getsession" in rule_id or "get-session" in rule_id:
        return ("AUTO", 0.97)
    return ("GUIDED", 0.75)


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
    result = fp.fingerprint(state["workspace_path"])
    elapsed = (time.perf_counter() - t0) * 1000
    timings = dict(state.get("timings") or {})
    timings["fingerprint_ms"] = round(elapsed, 1)
    return {"fingerprint": result, "timings": timings}


def node_chain_walker(state: TriageState) -> dict:
    t0 = time.perf_counter()
    findings = chain_walker.walk(state["workspace_path"])
    elapsed = (time.perf_counter() - t0) * 1000
    timings = dict(state.get("timings") or {})
    timings["chain_walker_ms"] = round(elapsed, 1)
    return {"cw_findings": findings, "timings": timings}


def node_schema(state: TriageState) -> dict:
    t0 = time.perf_counter()
    findings = schema_checker.check(state["workspace_path"])
    elapsed = (time.perf_counter() - t0) * 1000
    timings = dict(state.get("timings") or {})
    timings["schema_ms"] = round(elapsed, 1)
    return {"schema_findings": findings, "timings": timings}


def node_semgrep(state: TriageState) -> dict:
    t0 = time.perf_counter()
    result = rkt_engine.run_semgrep(state["workspace_path"], autofix=False)
    elapsed = (time.perf_counter() - t0) * 1000
    timings = dict(state.get("timings") or {})
    timings["semgrep_ms"] = round(elapsed, 1)
    findings = result.get("findings", [])
    return {"semgrep_findings": findings, "timings": timings}


def node_fs_checks(state: TriageState) -> dict:
    t0 = time.perf_counter()
    issues = rkt_engine.fs_checks(state["workspace_path"])
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
    for f in (state.get("semgrep_findings") or []):
        raw.append({"source": "semgrep", "finding": f, "fix_mode": "GUIDED", "confidence": 0.75})
    for f in (state.get("fs_issues") or []):
        raw.append({"source": "fs_checks", "finding": f, "fix_mode": "GUIDED", "confidence": 0.75})

    result = filter_findings(raw, workspace)
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
    deduped = deduplicate(state.get("filtered_findings") or [])
    elapsed = (time.perf_counter() - t0) * 1000
    timings = dict(state.get("timings") or {})
    timings["dedup_ms"] = round(elapsed, 1)
    return {"deduped_findings": deduped, "timings": timings}


def node_symptom_rank(state: TriageState) -> dict:
    t0 = time.perf_counter()
    ranked, symptom_cat = rank_findings(
        state.get("findings_scored") or [],
        state.get("issue_description") or "",
    )
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
    query = f"{state['issue_description']} {fp_result.get('common_failure', '')} {fp_result.get('project_type', '')}"
    match = rkt_engine.db_lookup(query.strip(), category=category)
    elapsed = (time.perf_counter() - t0) * 1000
    timings = dict(state.get("timings") or {})
    timings["db_lookup_ms"] = round(elapsed, 1)
    return {"db_match": match, "timings": timings}


def node_score_and_route(state: TriageState) -> dict:
    scored: List[Dict[str, Any]] = []

    # Score deduped pre-scored entries (produced by node_deduplicate)
    for entry in (state.get("deduped_findings") or []):
        src = entry.get("source", "")
        f = entry.get("finding", {})
        evidence = entry.get("evidence", [src])

        if src == "chain_walker":
            mode, conf = _score_cw_finding(f)
        elif src == "semgrep":
            mode, conf = _score_semgrep_finding(f)
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
            elif src == "semgrep":
                rule = (f.get("check_id") or "").split(".")[-1]
                path = f.get("path", "")
                line = f.get("start", {}).get("line", "?")
                msg  = f"{rule} @ {path}:{line}"
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


# ── Graph assembly ────────────────────────────────────────────────────────────

def _build_graph() -> Any:
    g = StateGraph(TriageState)

    g.add_node("fingerprint",      node_fingerprint)
    g.add_node("chain_walker",     node_chain_walker)
    g.add_node("schema",           node_schema)
    g.add_node("semgrep",          node_semgrep)
    g.add_node("fs_checks",        node_fs_checks)
    g.add_node("context_filter",   node_context_filter)
    g.add_node("deduplicate",      node_deduplicate)
    g.add_node("db_lookup",        node_db_lookup)
    g.add_node("score_and_route",  node_score_and_route)
    g.add_node("symptom_rank",     node_symptom_rank)
    g.add_node("build_summary",    node_build_summary)

    g.set_entry_point("fingerprint")
    g.add_edge("fingerprint",      "chain_walker")
    g.add_edge("chain_walker",     "schema")
    g.add_edge("schema",           "semgrep")
    g.add_edge("semgrep",          "fs_checks")
    g.add_edge("fs_checks",        "context_filter")
    g.add_edge("context_filter",   "deduplicate")
    g.add_edge("deduplicate",      "db_lookup")
    g.add_edge("db_lookup",        "score_and_route")
    g.add_edge("score_and_route",  "symptom_rank")
    g.add_edge("symptom_rank",     "build_summary")
    g.add_edge("build_summary",    END)

    return g.compile()


_GRAPH = None


def _get_graph():
    global _GRAPH
    if _GRAPH is None:
        _GRAPH = _build_graph()
    return _GRAPH


# ── Public entry point ────────────────────────────────────────────────────────

def run_triage(workspace_path: str, issue_description: str, port: int = 3000) -> Dict[str, Any]:
    """
    Run the full triage pipeline on workspace_path.
    Returns the final state dict.
    """
    initial: TriageState = {
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
        "timings":             {},
        "summary":             "",
    }
    graph  = _get_graph()
    result = graph.invoke(initial)
    return dict(result)
