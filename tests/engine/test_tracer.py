import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.expanduser("~/rocket-support/engine"))


def test_trace_context_writes_realtime_log():
    import tracer

    log_dir = tempfile.mkdtemp()
    log_path = os.path.join(log_dir, "trace.log")
    old_trace_log = os.environ.get("RKT_TRACE_LOG")
    try:
        os.environ["RKT_TRACE_LOG"] = log_path
        logger = tracer.init_tracer("TEST")
        with tracer.trace("PHASEX", "fake_tool") as token:
            time.sleep(0.001)
            token.set_output("items=3")

        with open(logger.log_path, encoding="utf-8") as fh:
            content = fh.read()

        assert "START rkt-trace thread=TEST" in content
        assert "PHASEX fake_tool" in content
        assert "OK" in content
        assert "items=3" in content
    finally:
        if old_trace_log is None:
            os.environ.pop("RKT_TRACE_LOG", None)
        else:
            os.environ["RKT_TRACE_LOG"] = old_trace_log
        tracer.reset_tracer_for_tests()


def test_trace_rg_logs_match_counts():
    import tracer

    workdir = tempfile.mkdtemp()
    sample_path = os.path.join(workdir, "sample.txt")
    with open(sample_path, "w", encoding="utf-8") as fh:
        fh.write("alpha\nbeta\nalpha\n")

    log_path = os.path.join(workdir, "trace.log")
    old_trace_log = os.environ.get("RKT_TRACE_LOG")
    try:
        os.environ["RKT_TRACE_LOG"] = log_path
        tracer.init_tracer("RGTEST")
        matches = tracer.trace_rg(["-n", "alpha", workdir])

        with open(log_path, encoding="utf-8") as fh:
            content = fh.read()

        assert len(matches) == 2
        assert "rg pattern=alpha" in content
        assert "matches=2" in content
        assert "files=1" in content
    finally:
        if old_trace_log is None:
            os.environ.pop("RKT_TRACE_LOG", None)
        else:
            os.environ["RKT_TRACE_LOG"] = old_trace_log
        tracer.reset_tracer_for_tests()
