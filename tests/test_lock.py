from __future__ import annotations

import json
import os
import time

import pytest

from engine.store import lock


def test_second_holder_is_refused_and_lock_released(tmp_path):
    path = tmp_path / "refresh.lock"
    with lock.run_lock(path, "run_refresh", heartbeat_s=0.05):
        assert json.loads(path.read_text())["holder"] == "run_refresh"
        assert not lock.acquire(path, "run_seasonal")  # same live PID holds it
        with pytest.raises(lock.LockBusy, match="run_refresh"), lock.run_lock(path, "run_seasonal"):
            pass
        assert "run_refresh" in (lock.held_by(path) or "")
    assert not path.exists()


def test_dead_process_lock_is_cleared(tmp_path, monkeypatch):
    path = tmp_path / "refresh.lock"
    path.write_text(json.dumps({"pid": 999_999, "holder": "run_themes"}))
    monkeypatch.setattr(lock, "pid_alive", lambda pid: False)
    assert lock.held_by(path) is None  # killed at the task limit: no cleanup ran
    assert lock.acquire(path, "run_refresh")


def test_old_heartbeat_is_stale_even_if_pid_reused(tmp_path, monkeypatch):
    path = tmp_path / "refresh.lock"
    path.write_text("4242")  # a lock written by the old code: PID only
    old = time.time() - 11 * 60
    os.utime(path, (old, old))
    monkeypatch.setattr(lock, "pid_alive", lambda pid: True)
    assert lock.held_by(path) is None
    assert lock.acquire(path, "run_refresh")


def test_fresh_lock_of_live_process_is_kept(tmp_path, monkeypatch):
    path = tmp_path / "refresh.lock"
    path.write_text(json.dumps({"pid": 4242, "holder": "run_financing", "started": "x"}))
    monkeypatch.setattr(lock, "pid_alive", lambda pid: True)
    assert "run_financing" in (lock.held_by(path) or "")
    assert not lock.acquire(path, "run_refresh")


def test_heartbeat_touches_the_file(tmp_path):
    path = tmp_path / "refresh.lock"
    with lock.run_lock(path, "x", heartbeat_s=0.05):
        old = time.time() - 600
        os.utime(path, (old, old))
        time.sleep(0.3)
        assert time.time() - path.stat().st_mtime < 5


def test_this_process_is_alive():
    assert lock.pid_alive(os.getpid())
