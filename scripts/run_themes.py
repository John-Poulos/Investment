"""Theme breadth from EDGAR full-text search (M02 part 1: D-M02-1, -14, -16).

    uv run python scripts/run_themes.py --dry-run          # seeds + plan, no SEC calls
    uv run python scripts/run_themes.py                    # 10-K family, 2019 → today
    uv run python scripts/run_themes.py --families 10-K,10-Q --first-year 2021
    uv run python scripts/run_themes.py --themes quantum,hbm_packaging

Steps: sync config/themes.toml into the database; fetch EDGAR's quarterly form
indexes for the years needed (denominator: distinct filers per form family); then,
for each theme phrase and window, count filings and distinct filers via EFTS (up to
10 pages per window; beyond that a lower bound "≥"). Windows: full calendar years,
then year-to-date and the same span a year earlier. SEC pacing as everywhere (5/s).
Closed windows are cached 30 days, so re-runs are cheap.

Writes logs/themes_<YYYYMMDD-HHMMSS>.txt (send it back). Does not start while the
nightly refresh holds data/refresh.lock, and holds that lock itself while running.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from engine.sec.client import SecClient, iso, user_agent_from_env  # noqa: E402
from engine.store.db import data_dir, open_db  # noqa: E402
from engine.store.http import SqliteCache, SqliteFetchLog  # noqa: E402
from engine.themes.breadth import (  # noqa: E402
    MAX_PAGES,
    THEME_ROW,
    breadth_rows,
    breadth_windows,
    compute_theme,
)
from engine.themes.seeds import active_phrases, active_themes, sync_seeds  # noqa: E402
from engine.themes.universe import (  # noqa: E402
    FAMILIES,
    data_through,
    ensure_quarters,
    quarters_between,
)


def fmt_share(v: float | None, lower: bool) -> str:
    return "—" if v is None else f"{'≥' if lower else ''}{100 * v:.2f}%"


def report_theme(engine, theme, family: str) -> list[str]:
    rows = breadth_rows(engine, theme["theme_id"], family)
    out = [f"\n{theme['name']} ({theme['key']}) — {family}"]
    out.append(f"  {'window':<23} {'companies':>10} {'filers':>7} {'share':>8} {'vs yr ago':>10}")
    for r in (r for r in rows if r.phrase == THEME_ROW):
        ge = "≥" if r.lower_bound else ""
        comp = "—" if r.companies is None else f"{ge}{r.companies:,}"
        fil = "—" if r.filers is None else f"{r.filers:,}"
        chg = "—" if r.change_pts is None else f"{r.change_pts:+.2f} pts"
        out.append(f"  {r.start}..{r.end} {comp:>10} {fil:>7} "
                   f"{fmt_share(r.share, r.lower_bound):>8} {chg:>10}"
                   f"{'  ' + r.error if r.error else ''}")  # fmt: skip
    out.append("  per phrase (companies per window, oldest → newest):")
    phrases: dict[str, list[str]] = {}
    for r in (r for r in rows if r.phrase != THEME_ROW):
        cell = "fail" if r.companies is None else f"{'≥' if r.lower_bound else ''}{r.companies}"
        phrases.setdefault(r.phrase, []).append(cell)
    for p, cells in phrases.items():
        out.append(f"    {p:<32} {' '.join(f'{c:>6}' for c in cells)}")
    for r in rows:
        if r.phrase != THEME_ROW and r.error:
            out.append(f"    note {r.phrase} {r.start}..{r.end}: {r.error}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--families", default="10-K", help=f"comma list of {', '.join(FAMILIES)}")
    ap.add_argument("--first-year", type=int, default=2019)
    ap.add_argument("--themes", help="comma list of theme keys (default: all active)")
    ap.add_argument("--max-pages", type=int, default=MAX_PAGES)
    ap.add_argument("--dry-run", action="store_true", help="sync seeds and show the plan only")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # "≥", "×" on Windows consoles
    families = [f.strip() for f in args.families.split(",") if f.strip()]
    if bad := [f for f in families if f not in FAMILIES]:
        print(f"unknown families: {bad}; choose from {list(FAMILIES)}")
        return 1

    folder = data_dir()
    lock = folder / "refresh.lock"
    if lock.exists():
        print("data/refresh.lock exists: the refresh is running; try again later.")
        return 2
    engine = open_db("engine", folder)
    now = datetime.now(UTC)
    lines = [f"Theme breadth run {now:%Y-%m-%d %H:%M} UTC  families={families} "
             f"first_year={args.first_year} max_pages={args.max_pages}"]  # fmt: skip

    seeds = sync_seeds(engine, ROOT / "config" / "themes.toml", now)
    lines.append(
        f"seeds: +{len(seeds.themes_added)} themes, +{len(seeds.phrases_added)} "
        f"phrases, +{len(seeds.companies_added)} company links; archived "
        f"{seeds.themes_archived + seeds.phrases_archived + seeds.companies_archived}"
    )
    for p in seeds.rejected:
        lines.append(f"  seed problem: {p}")
    themes = active_themes(engine)
    if args.themes:
        wanted = {k.strip() for k in args.themes.split(",")}
        themes = [t for t in themes if t["key"] in wanted]
    n_phrases = sum(len(active_phrases(engine, t["theme_id"])) for t in themes)
    today = now.date()
    n_windows = len(breadth_windows(args.first_year, today))
    lines.append(f"plan: {len(themes)} themes, {n_phrases} phrases × {n_windows} windows × "
                 f"{len(families)} families = {n_phrases * n_windows * len(families)} EFTS "
                 f"queries minimum (+ paging up to {args.max_pages} pages each); "
                 f"{len(quarters_between(date(args.first_year, 1, 1), today))} quarterly "
                 "form indexes")  # fmt: skip
    if args.dry_run:
        print("\n".join(lines))
        return 0

    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)
    try:
        corpus = open_db("corpus", folder)
        client = SecClient(user_agent_from_env(), cache=SqliteCache(corpus),
                           log=SqliteFetchLog(engine))  # fmt: skip
        wanted_q = quarters_between(date(args.first_year, 1, 1), today)
        quarters = ensure_quarters(client, engine, wanted_q, now)
        fetched = [q for q in quarters if q.status == "fetched"]
        failed = [q for q in quarters if q.status == "failed"]
        lines.append(f"form index: {len(fetched)} quarters fetched, "
                     f"{len(quarters) - len(fetched) - len(failed)} already stored, "
                     f"{len(failed)} failed")  # fmt: skip
        for q in failed:
            lines.append(f"  {q.year} Q{q.quarter} failed: {q.detail}")
        through = data_through(engine)
        end = date.fromisoformat(through) if through else today
        lines.append(f"index data through {end}; year-to-date windows end there")
        windows = breadth_windows(args.first_year, end)
        print("\n".join(lines), flush=True)
        for t in themes:
            phrases = active_phrases(engine, t["theme_id"])
            for fam in families:
                compute_theme(client, engine, t["theme_id"], t["key"], phrases, fam, windows,
                              now, args.max_pages, progress=print)  # fmt: skip
                lines += report_theme(engine, t, fam)
        sent = engine.execute(
            "SELECT count(*) FROM fetch_log WHERE at >= ? AND from_cache = 0", (iso(now),)
        ).fetchone()[0]
        lines.append(f"\nSEC requests sent this run: {sent:,}")
        corpus.close()
    finally:
        lock.unlink(missing_ok=True)

    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    out = logs / f"themes_{datetime.now():%Y%m%d-%H%M%S}.txt"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[-200:]))
    print(f"\nwrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
