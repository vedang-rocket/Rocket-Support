from __future__ import annotations

import contextlib
import datetime
import json
import os
import platform
import re
import resource
import shutil
import subprocess
import sys
import time
import traceback
from collections import Counter, defaultdict
from typing import Any, Dict, Iterator, List, Optional, Sequence


_LOGGER: Optional["TraceLogger"] = None

# macOS ru_maxrss is in bytes; Linux is in KB. Normalise to KB everywhere.
_MAXRSS_TO_KB: int = 1024 if platform.system() == "Darwin" else 1


def _truncate(value: Any, limit: int = 500) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\n", "\\n")
    return text[:limit]


def _status_for_result(result: Any) -> str:
    if result is None:
        return "EMPTY"
    if result == [] or result == {} or result == "":
        return "EMPTY"
    return "OK"


def _extract_rg_pattern(args: Sequence[str]) -> str:
    skip_next = False
    options_with_values = {
        "-g",
        "--glob",
        "-t",
        "--type",
        "-e",
        "--regexp",
        "--colors",
        "--encoding",
        "--engine",
        "--field-match-separator",
        "--field-context-separator",
        "--iglob",
        "--path-separator",
        "--sort",
        "--sortr",
    }
    for idx, arg in enumerate(args):
        if skip_next:
            skip_next = False
            continue
        if arg in ("-e", "--regexp") and idx + 1 < len(args):
            return args[idx + 1]
        if arg in options_with_values:
            skip_next = True
            continue
        if arg.startswith("-"):
            continue
        return arg
    return ""


def _extract_file_patterns(args: Sequence[str]) -> str:
    patterns: List[str] = []
    for idx, arg in enumerate(args):
        if arg in ("--glob", "-g") and idx + 1 < len(args):
            patterns.append(args[idx + 1])
    return ",".join(patterns)


def _extract_table(sql: str) -> str:
    match = re.search(
        r"\b(?:from|into|update|join)\s+([A-Za-z_][A-Za-z0-9_\.]*)",
        sql,
        re.IGNORECASE,
    )
    return match.group(1) if match else "unknown"


class TraceLogger:
    def __init__(self, thread_id: str, log_path: Optional[str] = None):
        self.thread_id = thread_id
        self.start = time.perf_counter()
        self.phase_times: Dict[str, float] = defaultdict(float)
        self.counts: Counter[str] = Counter()
        self.findings: Dict[str, Any] = {}
        self.log_path = log_path or self._default_log_path(thread_id)
        os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
        self._fh = open(self.log_path, "a", encoding="utf-8", buffering=1)
        if os.environ.get("RKT_TRACE_SUPPRESS_START") != "1":
            self._write(f"[{self.elapsed()}] START rkt-trace thread={thread_id}")

    @staticmethod
    def _default_log_path(thread_id: str) -> str:
        trace_dir = os.path.expanduser("~/.rocket-support/traces")
        stamp = datetime.datetime.now().strftime("%Y%m%dT%H%M%S")
        safe_thread = re.sub(r"[^A-Za-z0-9_.-]+", "_", thread_id)
        return os.path.join(trace_dir, f"{safe_thread}_{stamp}.log")

    def elapsed(self) -> str:
        total_ms = int((time.perf_counter() - self.start) * 1000)
        minutes = total_ms // 60000
        seconds = (total_ms % 60000) // 1000
        millis = total_ms % 1000
        return f"{minutes:02d}:{seconds:02d}.{millis:03d}"

    def _write(self, line: str) -> None:
        sys.__stdout__.write(line + "\n")
        sys.__stdout__.flush()
        self._fh.write(line + "\n")
        self._fh.flush()

    def log(
        self,
        phase: str,
        tool_name: str,
        status: str,
        duration_ms: float,
        input_summary: str = "",
        output_summary: str = "",
        memory_delta_kb: Optional[int] = None,
    ) -> None:
        details = " ".join(
            part
            for part in (
                _truncate(input_summary, 240),
                _truncate(output_summary, 500),
                f"mem_delta_kb={memory_delta_kb}" if memory_delta_kb is not None else "",
            )
            if part
        )
        line = f"[{self.elapsed()}] {phase} {tool_name:<32} {status:<5} {duration_ms:5.0f}ms"
        if details:
            line += f"   {details}"
        self._write(line)

    def log_sub(self, tool_name: str, duration_ms: float, details: str = "") -> None:
        line = f"[{self.elapsed()}]   -> {tool_name:<32} {duration_ms:5.0f}ms"
        if details:
            line += f"  {_truncate(details, 500)}"
        self._write(line)

    def record_phase_time(self, phase: str, duration_ms: float) -> None:
        self.phase_times[phase] += duration_ms

    def increment(self, counter: str, amount: int = 1) -> None:
        self.counts[counter] += amount

    def set_finding(self, key: str, value: Any) -> None:
        self.findings[key] = value

    def print_summary(self) -> None:
        total_ms = (time.perf_counter() - self.start) * 1000
        self._write("")
        self._write("═" * 52)
        self._write(f"TRACE SUMMARY  thread={self.thread_id}")
        self._write("═" * 52)
        self._write(f"Total wall time:     {total_ms / 1000:.3f}s")
        self._write("")
        self._write("Time by phase:")
        for phase in sorted(self.phase_times):
            ms = self.phase_times[phase]
            pct = (ms / total_ms * 100) if total_ms else 0.0
            self._write(f"  {phase:<7} {ms:8.0f}ms  ({pct:4.1f}%)")
        self._write("")
        self._write("Tool call counts:")
        labels = {
            "ripgrep": "ripgrep calls",
            "ast_grep": "ast-grep calls",
            "sqlite3": "sqlite3 queries",
            "claude": "Claude API calls",
            "rsync": "rsync calls",
            "tsc": "tsc calls",
        }
        for key, label in labels.items():
            self._write(f"  {label:<22} {self.counts.get(key, 0)}")
        if self.findings:
            self._write("")
            self._write("Findings:")
            for key in sorted(self.findings):
                self._write(f"  {key:<22} {self.findings[key]}")
        self._write("")
        self._write(f"Log saved to: {self.log_path}")
        self._write("═" * 52)

    def close(self) -> None:
        try:
            self._fh.close()
        except Exception:
            pass


class _TraceToken:
    def __init__(self, phase: str, tool_name: str):
        self.phase = phase
        self.tool_name = tool_name
        self._input = ""
        self._output = ""
        self._empty: Optional[bool] = None

    def set_input(self, summary: str) -> None:
        self._input = summary

    def set_output(self, summary: str) -> None:
        self._output = summary

    def set_result(self, result: Any, summary: str = "") -> None:
        self._empty = _status_for_result(result) == "EMPTY"
        if summary:
            self._output = summary

    def set_empty(self, empty: bool = True) -> None:
        self._empty = empty


class _NullToken(_TraceToken):
    def __init__(self):
        super().__init__("", "")


def init_tracer(thread_id: str) -> TraceLogger:
    global _LOGGER
    log_path = os.environ.get("RKT_TRACE_LOG") or None
    _LOGGER = TraceLogger(thread_id=thread_id, log_path=log_path)
    return _LOGGER


def init_if_env() -> Optional[TraceLogger]:
    thread_id = os.environ.get("RKT_TRACE")
    if not thread_id:
        return _LOGGER
    if _LOGGER is None:
        return init_tracer(thread_id)
    return _LOGGER


def get_logger() -> Optional[TraceLogger]:
    return _LOGGER


def reset_tracer_for_tests() -> None:
    global _LOGGER
    if _LOGGER is not None:
        _LOGGER.close()
    _LOGGER = None


@contextlib.contextmanager
def trace(phase: str, tool_name: str) -> Iterator[_TraceToken]:
    logger = get_logger()
    if logger is None:
        yield _NullToken()
        return

    token = _TraceToken(phase, tool_name)
    mem_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    t0 = time.perf_counter()
    try:
        yield token
    except Exception as exc:
        duration_ms = (time.perf_counter() - t0) * 1000
        mem_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        logger.log(
            phase,
            tool_name,
            "FAIL",
            duration_ms,
            input_summary=token._input,
            output_summary=f"exception={_truncate(exc, 160)}",
            memory_delta_kb=(mem_after - mem_before) // _MAXRSS_TO_KB,
        )
        logger._write(traceback.format_exc().rstrip())
        logger.record_phase_time(phase, duration_ms)
        raise
    duration_ms = (time.perf_counter() - t0) * 1000
    mem_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    status = "EMPTY" if token._empty else "OK"
    logger.log(
        phase,
        tool_name,
        status,
        duration_ms,
        input_summary=token._input,
        output_summary=token._output,
        memory_delta_kb=(mem_after - mem_before) // _MAXRSS_TO_KB,
    )
    logger.record_phase_time(phase, duration_ms)


def trace_rg(args: Sequence[str], timeout: int = 10) -> List[Dict[str, Any]]:
    logger = get_logger()
    cmd = [shutil.which("rg") or "rg", "--json"] + list(args)
    pattern = _extract_rg_pattern(args)
    file_patterns = _extract_file_patterns(args)
    t0 = time.perf_counter()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception:
        duration_ms = (time.perf_counter() - t0) * 1000
        if logger:
            logger.increment("ripgrep")
            logger.log_sub(
                f"rg pattern={pattern}",
                duration_ms,
                f"status=FAIL filesearched={file_patterns} error={traceback.format_exc().splitlines()[-1]}",
            )
        return []

    matches: List[Dict[str, Any]] = []
    files = set()
    for line in result.stdout.splitlines():
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("type") != "match":
            continue
        data = obj.get("data") or {}
        matches.append(data)
        path = (data.get("path") or {}).get("text")
        if path:
            files.add(path)

    duration_ms = (time.perf_counter() - t0) * 1000
    if logger:
        logger.increment("ripgrep")
        logger.log_sub(
            f"rg pattern={pattern}",
            duration_ms,
            (
                f"exit={result.returncode} matches={len(matches)} files={len(files)} "
                f"patterns={file_patterns or '-'} cmd={' '.join(cmd)}"
            ),
        )
    return matches


def trace_ast_grep(args: Sequence[str], timeout: int = 10) -> subprocess.CompletedProcess:
    logger = get_logger()
    cmd = [shutil.which("ast-grep") or "ast-grep"] + list(args)
    pattern = _extract_rg_pattern(args)
    t0 = time.perf_counter()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception:
        duration_ms = (time.perf_counter() - t0) * 1000
        if logger:
            logger.increment("ast_grep")
            logger.log_sub(
                f"ast-grep pattern={pattern}",
                duration_ms,
                f"status=FAIL error={traceback.format_exc().splitlines()[-1]}",
            )
        raise
    duration_ms = (time.perf_counter() - t0) * 1000
    matches = result.stdout.count("\n") if result.stdout else 0
    if logger:
        logger.increment("ast_grep")
        logger.log_sub(
            f"ast-grep pattern={pattern}",
            duration_ms,
            f"exit={result.returncode} matches={matches} cmd={' '.join(cmd)}",
        )
    return result


def trace_claude(client: Any, **kwargs: Any) -> Any:
    logger = get_logger()
    model = kwargs.get("model", "unknown")
    prompt = ""
    messages = kwargs.get("messages") or []
    if messages:
        content = messages[0].get("content", "") if isinstance(messages[0], dict) else ""
        prompt = content if isinstance(content, str) else str(content)
    t0 = time.perf_counter()
    try:
        response = client.messages.create(**kwargs)
    except Exception:
        duration_ms = (time.perf_counter() - t0) * 1000
        if logger:
            logger.increment("claude")
            logger.log("PHASE6", "claude_api", "FAIL", duration_ms, f"model={model}", traceback.format_exc().splitlines()[-1])
        raise
    duration_ms = (time.perf_counter() - t0) * 1000
    usage = getattr(response, "usage", None)
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    cost = (input_tokens * 3 / 1_000_000) + (output_tokens * 15 / 1_000_000)
    response_text = ""
    try:
        response_text = response.content[0].text
    except Exception:
        response_text = ""
    if logger:
        logger.increment("claude")
        logger.log(
            "PHASE6",
            "claude_api",
            "OK" if response_text else "EMPTY",
            duration_ms,
            input_summary=f"model={model}",
            output_summary=f"tokens={input_tokens}+{output_tokens} cost=${cost:.3f}",
        )
        logger.log_sub("prompt[:200]", 0, _truncate(prompt, 200))
        logger.log_sub("response[:200]", 0, _truncate(response_text, 200))
    return response


def trace_db(conn: Any, sql: str, params: Sequence[Any] = ()) -> List[Any]:
    logger = get_logger()
    table = _extract_table(sql)
    t0 = time.perf_counter()
    try:
        rows = conn.execute(sql, tuple(params)).fetchall()
    except Exception:
        duration_ms = (time.perf_counter() - t0) * 1000
        if logger:
            logger.increment("sqlite3")
            logger.log_sub(
                f"sqlite3 query={_truncate(sql, 80)}",
                duration_ms,
                f"status=FAIL table={table} error={traceback.format_exc().splitlines()[-1]}",
            )
        raise
    duration_ms = (time.perf_counter() - t0) * 1000
    if logger:
        logger.increment("sqlite3")
        logger.log_sub(
            f"sqlite3 query={_truncate(sql, 80)}",
            duration_ms,
            f"rows={len(rows)} table={table}",
        )
    return rows
