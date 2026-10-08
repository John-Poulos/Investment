from __future__ import annotations

import importlib.util
import os
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("run_refresh", ROOT / "scripts" / "run_refresh.py")
assert spec and spec.loader
run_refresh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_refresh)


def test_last_scheduled_slot():
    assert run_refresh.last_scheduled_slot(datetime(2026, 10, 7, 8, 30)) == datetime(
        2026, 10, 7, 2, 0
    )  # morning logon: today's 02:00 slot
    assert run_refresh.last_scheduled_slot(datetime(2026, 10, 7, 1, 15)) == datetime(
        2026, 10, 6, 2, 0
    )  # before 02:00: yesterday's slot


def test_lock_blocks_second_run_and_expires(tmp_path):
    lock = tmp_path / "refresh.lock"
    assert run_refresh.acquire_lock(lock)
    assert not run_refresh.acquire_lock(lock)  # a run is in progress
    old = time.time() - 7 * 3600
    os.utime(lock, (old, old))
    assert run_refresh.acquire_lock(lock)  # stale lock (> 6 h) is replaced
