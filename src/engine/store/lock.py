"""One SEC-calling process at a time: `data/refresh.lock` (D-M02-51).

Two processes pacing at 5/s each reach SEC's 10/s limit (S121), so the refresh and
every owner script that calls SEC take the same lock. The file holds the holder's PID,
name and start time; a background thread touches it every minute (heartbeat). A
scheduled task killed at its time limit or at shutdown skips cleanup (S120), so a lock
is stale — and cleared — when its process is gone or its heartbeat is older than
`STALE_AFTER`. Scripts that only read local data use `held_by()` to wait politely.
"""

from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

LOCK_NAME = "refresh.lock"
HEARTBEAT_S = 60
STALE_AFTER = timedelta(minutes=10)


class LockBusy(Exception):
    """Another live process holds the lock; the message names it."""


def pid_alive(pid: int) -> bool:
    """Whether a process with this PID exists (Windows: OpenProcess + exit code)."""
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return kernel32.GetLastError() == 5  # access denied: it exists
        try:
            code = ctypes.c_ulong()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == 259  # STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_lock(path: Path) -> dict | None:
    """Holder details, or None when there is no lock. Old locks hold only a PID."""
    try:
        raw = path.read_text(encoding="utf-8").strip()
        mtime = path.stat().st_mtime
    except FileNotFoundError:
        return None
    except OSError:
        return {"pid": 0, "holder": "unknown", "beat": datetime.now()}
    try:
        info = json.loads(raw) if raw.startswith("{") else {"pid": int(raw or 0)}
    except ValueError, TypeError:
        info = {"pid": 0}
    info.setdefault("holder", "unknown")
    info["beat"] = datetime.fromtimestamp(mtime)
    return info


def stale_reason(info: dict, now: datetime | None = None) -> str | None:
    now = now or datetime.now()
    pid = int(info.get("pid") or 0)
    if pid and pid != os.getpid() and not pid_alive(pid):
        return f"process {pid} is gone"
    if now - info["beat"] > STALE_AFTER:
        return f"no heartbeat since {info['beat']:%Y-%m-%d %H:%M}"
    return None


def held_by(path: Path) -> str | None:
    """Who holds a live lock ("run_seasonal, PID 123, since …"), clearing a stale one."""
    info = read_lock(path)
    if info is None:
        return None
    if stale_reason(info):
        path.unlink(missing_ok=True)
        return None
    return f"{info['holder']} (PID {info.get('pid')}, since {info.get('started', '?')})"


def acquire(path: Path, holder: str) -> bool:
    """Create the lock; False when a live process holds it. A stale lock is replaced."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if held_by(path) is not None:
        return False
    try:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return False
    body = {"pid": os.getpid(), "holder": holder, "started": f"{datetime.now():%Y-%m-%d %H:%M}"}
    os.write(fd, json.dumps(body).encode())
    os.close(fd)
    return True


def release(path: Path) -> None:
    info = read_lock(path)
    if info is not None and int(info.get("pid") or 0) in (0, os.getpid()):
        path.unlink(missing_ok=True)


def run_script(root: Path, holder: str, main: Callable[[], int]) -> int:
    """Run an owner script's main under the lock; exit code 2 when another holds it."""
    try:
        with run_lock(root / "data" / LOCK_NAME, holder):
            return main()
    except LockBusy as e:
        print(f"{e}; try again later.")
        return 2


@contextmanager
def run_lock(path: Path, holder: str, heartbeat_s: float = HEARTBEAT_S) -> Iterator[None]:
    """Hold the lock for the block, touching it every `heartbeat_s` seconds."""
    if not acquire(path, holder):
        raise LockBusy(f"{path.name} is held by {held_by(path) or 'another process'}")
    stop = threading.Event()

    def beat() -> None:
        while not stop.wait(heartbeat_s):
            try:
                os.utime(path)
            except OSError:
                return

    t = threading.Thread(target=beat, name="lock-heartbeat", daemon=True)
    t.start()
    try:
        yield
    finally:
        stop.set()
        t.join(timeout=2)
        release(path)
