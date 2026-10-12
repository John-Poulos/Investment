"""Run the live SEC tests and save all output (stdout + stderr) to logs/.

Works the same from PowerShell, cmd or Git Bash:
    uv run python scripts/run_live.py [label] [extra pytest args...]

Writes logs/live_<label>_<YYYYMMDD-HHMMSS>.txt and prints its path.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _main() -> int:
    label = sys.argv[1] if len(sys.argv) > 1 else "sec"
    extra = sys.argv[2:]
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    log = logs / f"live_{label}_{datetime.now():%Y%m%d-%H%M%S}.txt"

    cmd = [sys.executable, "-m", "pytest", "-m", "live", "-v", "-s", *extra]
    # Redirected output on Windows defaults to cp1252, which cannot print characters
    # such as the ☒ on 10-K cover pages and garbles dashes; force UTF-8 like the log file.
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    with log.open("w", encoding="utf-8") as out:
        out.write(f"command: {' '.join(cmd)}\ncwd: {ROOT}\nstarted: {datetime.now()}\n\n")
        out.flush()
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            env=env,
            stdout=out,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
        )
        out.write(f"\nexit code: {proc.returncode}\n")

    print(f"Live test log written to: {log}")
    print(f"pytest exit code: {proc.returncode} (0 = all passed)")
    return proc.returncode


def main() -> int:
    sys.path.insert(0, str(ROOT / "src"))
    from engine.store.lock import run_script

    return run_script(ROOT, "run_live", _main)  # live tests call SEC (D-M02-51)


if __name__ == "__main__":
    sys.exit(main())
