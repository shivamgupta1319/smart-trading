"""Auto-select runs in the background: the request that starts it must return at once.

A run takes several minutes and the public address cuts a request off after 120 seconds,
so POST /auto-select only starts the run and GET /auto-select/status reports on it.

Run from apps/engine:  python -m pytest test/test_auto_select_job.py -q
"""
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import routers.auto_select as auto  # noqa: E402


def _wait_until(predicate, seconds=5.0):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def test_start_returns_at_once_and_status_follows_the_run(monkeypatch):
    release = threading.Event()

    def slow_run(req, progress):
        progress("Testing strategies", 3, 28)
        release.wait(5)
        return {"written": 2, "totalPicks": 2}

    monkeypatch.setattr(auto, "run_auto_select", slow_run)
    started = time.monotonic()
    job = auto.auto_select(auto.AutoSelectRequest())
    assert time.monotonic() - started < 1, "starting a run must not wait for it"
    assert job["status"] == "running"

    assert _wait_until(lambda: auto.auto_select_status().get("done") == 3)
    status = auto.auto_select_status()
    assert (status["status"], status["stage"], status["total"]) == ("running", "Testing strategies", 28)

    # A second start while one is running returns that run; it does not start another.
    assert auto.auto_select(auto.AutoSelectRequest())["startedAt"] == job["startedAt"]

    release.set()
    assert _wait_until(lambda: auto.auto_select_status()["status"] == "done")
    assert auto.auto_select_status()["result"] == {"written": 2, "totalPicks": 2}


def test_a_failed_run_says_why_and_frees_the_next_one(monkeypatch):
    def broken(req, progress):
        raise RuntimeError("database went away")

    monkeypatch.setattr(auto, "run_auto_select", broken)
    auto.auto_select(auto.AutoSelectRequest())
    assert _wait_until(lambda: auto.auto_select_status()["status"] == "failed")
    assert "database went away" in auto.auto_select_status()["error"]

    monkeypatch.setattr(auto, "run_auto_select", lambda req, progress: {"written": 0})
    job = auto.auto_select(auto.AutoSelectRequest(wait=True))   # the lock was released
    assert job["status"] == "done" and job["result"] == {"written": 0}
