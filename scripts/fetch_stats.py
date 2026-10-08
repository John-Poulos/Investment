"""Summarise SEC request rates from data/engine.db fetch_log (diagnosing throttles).

    uv run python scripts/fetch_stats.py

Writes logs/fetch_stats_<YYYYMMDD-HHMMSS>.txt: requests per run window, peak
requests per 1 s / 10 s / 60 s, by host, and the minute before each throttle.
Reads only request URLs, outcomes and times (no credentials, no document text).
"""

from __future__ import annotations

import sqlite3
import sys
from collections import Counter, deque
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent


def peak(times: list[datetime], seconds: int) -> tuple[int, datetime | None]:
    best, at, window = 0, None, deque()
    for t in times:
        window.append(t)
        while (t - window[0]).total_seconds() >= seconds:
            window.popleft()
        if len(window) > best:
            best, at = len(window), window[0]
    return best, at


def main() -> int:
    db = ROOT / "data" / "engine.db"
    if not db.exists():
        print(f"not found: {db}")
        return 1
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    rows = conn.execute(
        "SELECT at, url, outcome, status FROM fetch_log WHERE from_cache = 0 ORDER BY log_id"
    ).fetchall()
    runs = conn.execute(
        "SELECT run_id, trigger, started_at, finished_at, status, error FROM refresh_run "
        "ORDER BY run_id"
    ).fetchall()
    out = [f"fetch_log: {len(rows)} network requests (cache hits excluded)", ""]
    out.append("refresh runs:")
    for r in runs:
        out.append(f"  run {r[0]} {r[1]:<17} {r[2]} → {r[3]}  {r[4]}  {(r[5] or '')[:90]}")
    out.append("")

    times = [datetime.fromisoformat(r[0]) for r in rows]
    for label, secs in (("1 s", 1), ("10 s", 10), ("60 s", 60)):
        n, at = peak(times, secs)
        out.append(f"peak requests in {label:>4}: {n:>5}  (window starting {at})")
    if times:
        span = (times[-1] - times[0]).total_seconds() or 1
        out.append(f"overall: {len(times)} requests over {span / 60:.1f} min "
                   f"= {len(times) / span:.2f}/s")  # fmt: skip
    out.append("")
    out.append("by host and outcome:")
    for (host, outcome), n in sorted(Counter(
        (urlparse(r[1]).netloc, r[2]) for r in rows
    ).items()):  # fmt: skip
        out.append(f"  {host:<20} {outcome:<10} {n:>6}")

    throttles = [i for i, r in enumerate(rows) if r[2] == "throttled"]
    out.append("")
    out.append(f"throttled responses: {len(throttles)}")
    if throttles:
        first = throttles[0]
        t0 = times[first]
        before = [t for t in times[:first] if (t0 - t).total_seconds() <= 60]
        out.append(f"first throttle at {t0} on {rows[first][1][:110]} (HTTP {rows[first][3]})")
        out.append(f"requests in the 60 s before it: {len(before)}")
        per_min = Counter(t.strftime("%H:%M") for t in times[:first])
        out.append("requests per minute before the first throttle (last 15 minutes):")
        for minute, n in sorted(per_min.items())[-15:]:
            out.append(f"  {minute}  {n:>4}  ({n / 60:.2f}/s)")

    text = "\n".join(out) + "\n"
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    path = logs / f"fetch_stats_{datetime.now():%Y%m%d-%H%M%S}.txt"
    path.write_text(text, encoding="utf-8")
    print(text)
    print(f"Written to: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
