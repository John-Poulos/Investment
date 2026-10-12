"""Nightly SEC refresh entry point (D-SEC-15).

    uv run python scripts/run_refresh.py                 # run now (manual)
    uv run python scripts/run_refresh.py --scheduled     # the 02:00 task
    uv run python scripts/run_refresh.py --if-missed --ask
        # at logon: if the last 02:00 run was missed, ask before catching up (owner choice)

Writes logs/refresh_<YYYYMMDD-HHMMSS>.txt and stores the run in data/engine.db.
Only one SEC-calling process at a time (data/refresh.lock with a heartbeat; a lock whose
process is gone or whose heartbeat stopped is cleared, D-M02-51). The end-of-run box is
shown after the lock is released.
Exit code: 0 ok, 1 partial or failed, 2 another run is in progress, 3 declined/not missed.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime, time, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEDULED_AT = time(2, 0)  # local time of the nightly task


def prices_step(engine, report) -> str:
    """Daily prices after the SEC step (D-UI-2): core + promoted every run, tracked names in
    a 3-day rotation; at most 40 requests/hour so the app keeps 8 (D-M02-12). Never fails
    the run."""
    from engine.prices.store import refresh_prices, tracked_rotation
    from engine.prices.tiingo import (
        BATCH_HOURLY_BUDGET,
        BATCH_MIN_INTERVAL_S,
        MissingKey,
        TiingoClient,
        token_from_env,
    )

    try:
        client = TiingoClient(token_from_env(), engine, hourly_budget=BATCH_HOURLY_BUDGET,
                              min_interval_s=BATCH_MIN_INTERVAL_S)  # fmt: skip
    except MissingKey as e:
        return f"\nPrices (Tiingo): skipped — {e}\n"
    symbols: dict[str, str | None] = {}
    for ticker, label in report.watchlist.items():
        cik = label.rsplit("(", 1)[-1].rstrip(")") if label.endswith(")") else None
        symbols[ticker] = cik if cik and len(cik) == 10 else None
    tracked = {t: c for t, c in report.tracked.items() if t not in symbols}
    today, over = tracked_rotation(engine, tracked)
    symbols |= today
    try:
        res = refresh_prices(engine, client, symbols, datetime.now(UTC))
    except Exception as e:  # prices must not break the SEC run report
        return f"\nPrices (Tiingo): error — {type(e).__name__}: {e}\n"
    lines = res.lines()
    if tracked:
        lines.append(
            f"tracked rotation: {len(today)} of {len(tracked)} tracked names today"
            + (f"; over the soft cap (not priced): {', '.join(over)}" if over else "")
        )
    return "\n".join(lines) + "\n"


def companies_of(report) -> dict[str, str]:
    """symbol → cik for core, promoted and tracked names in this run."""
    out: dict[str, str] = {}
    for ticker, label in report.watchlist.items():
        cik = label.rsplit("(", 1)[-1].rstrip(")") if label.endswith(")") else None
        if cik and len(cik) == 10:
            out[ticker] = cik
    return out | {t: c for t, c in report.tracked.items() if t not in out}


def calls_step(engine, corpus, report) -> str:
    """Releases and calls into the guidance ledger; transcripts within 20 Alpha Vantage
    requests a day (D-M02-20). Never fails the run."""
    from engine.calls.alpha_vantage import AlphaVantageClient, MissingKey, key_from_env
    from engine.calls.step import run_calls_step

    client, reason = None, ""
    try:
        client = AlphaVantageClient(key_from_env(), engine)
    except MissingKey as e:
        reason = str(e)
    lines = run_calls_step(engine, corpus, client, companies_of(report), datetime.now(UTC),
                           no_client_reason=reason)  # fmt: skip
    return "\n" + "\n".join(lines) + "\n"


def money_step(client, engine, corpus, report) -> str:
    """Money flow after the calls step (M02 part 3): stated actuals, extension facts,
    allocation coverage, spender links and candidates. Never fails the run."""
    from engine.moneyflow.step import run_money_step

    lines = run_money_step(client, engine, corpus, companies_of(report), datetime.now(UTC))
    return "\n".join(lines) + "\n"


def supply_step(client, engine, corpus, report) -> str:
    """Supplier passages after money flow (M02 part 5): L1 local, L3 and L2 within per-run
    caps; Gemini never runs here. Never fails the run."""
    from engine.supply.step import run_supply_step

    lines = run_supply_step(client, engine, corpus, companies_of(report), datetime.now(UTC))
    return "\n".join(lines) + "\n"


def financing_step(client, engine, corpus, report) -> str:
    """Financing links after suppliers (M02 part 5b): 13F, 13D/13G, text passages within
    per-run caps, credit series alerts. Never fails the run."""
    from engine.financing.step import run_financing_step

    lines = run_financing_step(client, engine, corpus, companies_of(report), datetime.now(UTC))
    return "\n".join(lines) + "\n"


def news_step(engine, corpus, report) -> str:
    """News after financing (M02 part 7a): IR RSS, trade press, 8-K releases, Finnhub
    (Massive backup), first mentions, last week's news item. Never fails the run."""
    from engine.news.step import run_news_step
    from engine.news.vendors import key_from_env

    rep = run_news_step(engine, corpus, companies_of(report), datetime.now(UTC),
                        finnhub_key=key_from_env("FINNHUB_API_KEY"),
                        massive_key=key_from_env("MASSIVE_API_KEY"))  # fmt: skip
    return "\n" + "\n".join(rep.lines) + "\n"


def official_step(engine, report) -> str:
    """Official feeds after news (M02 part 7b): Federal Register, Congress.gov, USAspending,
    arXiv, each within its own slice of a ~3-minute budget. Never fails the run."""
    from engine.news.vendors import key_from_env
    from engine.official.step import run_official_step

    rep = run_official_step(engine, companies_of(report), datetime.now(UTC),
                            congress_key=key_from_env("CONGRESS_API_KEY"))  # fmt: skip
    return "\n" + "\n".join(rep.lines) + "\n"


def seasonal_step(engine, corpus, report, background: bool):
    """D-M02-51: a due seasonal pass is mined here, locally (no SEC), and a background run
    then asks Yes/No after releasing the lock. Manual runs and a pass declined today get
    the reminder line only. Returns (report text, Prepared or None). Never fails the run."""
    from engine.themes import season_pass, seasonal

    today = datetime.now(UTC).date()
    line = seasonal.reminder(engine, today)
    if not line:
        return "", None
    s = seasonal.due(engine, today)
    declined = engine.execute("SELECT detail FROM refresh_state WHERE name = 'seasonal_declined'"
                              ).fetchone()  # fmt: skip
    if not background or s is None or (declined and declined[0] == f"{s.key}:{today}"):
        return f"\n{line}\n", None
    try:
        prep = season_pass.prepare(engine, corpus, s, core_promoted(report), datetime.now(UTC))
    except Exception as e:  # mining must not break the refresh report
        return f"\n{line}\nseasonal mining failed: {type(e).__name__}: {e}\n", None
    return (
        f"\n{line}\nSeasonal pass {s.key}: {prep.candidates} candidate phrases mined; "
        f"testing needs about {prep.requests:,} SEC requests (~{prep.minutes} min)\n"
    ), prep


def core_promoted(report) -> dict[str, str]:
    """cik → ticker of the core and promoted names (the companies mined, D-M02-52 (1))."""
    out: dict[str, str] = {}
    for ticker, label in report.watchlist.items():
        cik = label.rsplit("(", 1)[-1].rstrip(")") if label.endswith(")") else None
        if cik and len(cik) == 10:
            out.setdefault(cik, ticker)
    return out


def ask_and_run_season(engine, folder, prep, summary: str | None) -> None:
    """After the lock is released: one Yes/No box (the waiting summary inside it). Yes runs
    the pass now under the lock; No is remembered for today and the reminder stays."""
    from engine.store.lock import LockBusy, run_lock

    text = prep.question() + (f"\n\n{summary}" if summary else "")
    if not ask_yes_no("Investment engine — seasonal pass", text):
        engine.execute(
            "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES "
            "('seasonal_declined', 'owner', ?, ?) ON CONFLICT (name) DO UPDATE SET "
            "fetched_at = excluded.fetched_at, detail = excluded.detail",
            (datetime.now(UTC).isoformat(timespec="seconds"),
             f"{prep.season.key}:{datetime.now(UTC).date()}"),
        )  # fmt: skip
        return
    try:
        with run_lock(folder / "refresh.lock", "run_refresh (seasonal pass)"):
            last = run_season(engine, folder, prep)
    except LockBusy as e:
        last = f"The seasonal pass did not start: {e}."
    show_info("Investment engine — seasonal pass", last)


def run_season(engine, folder, prep) -> str:
    from engine.sec.client import SecClient, user_agent_from_env
    from engine.store.db import open_db
    from engine.store.http import SqliteCache, SqliteFetchLog
    from engine.themes import season_pass, seasonal

    corpus = open_db("corpus", folder, check_same_thread=False)
    try:
        client = SecClient(user_agent_from_env(), cache=SqliteCache(corpus),
                           log=SqliteFetchLog(engine))  # fmt: skip
        comps = season_pass.core_and_promoted(engine, ROOT / "config" / "watchlist.toml")
        lines = season_pass.run_pass(client, engine, corpus, prep.season, comps,
                                     datetime.now(UTC), seasonal.Budget())  # fmt: skip
    finally:
        corpus.close()
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    out = logs / f"seasonal_{datetime.now():%Y%m%d-%H%M%S}.txt"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    done = next((x.strip() for x in lines if x.strip().startswith(("season ", "STOPPED", "Not "))),
                "finished")  # fmt: skip
    return (
        f"Seasonal pass {prep.season.key}: {done}\n\nNew proposals wait on the Themes page "
        f"and in the review queue.\nLog: {out}"
    )


def last_scheduled_slot(now_local: datetime) -> datetime:
    slot = now_local.replace(hour=SCHEDULED_AT.hour, minute=SCHEDULED_AT.minute, second=0,
                             microsecond=0)  # fmt: skip
    return slot if now_local >= slot else slot - timedelta(days=1)


def ask_yes_no(title: str, text: str) -> bool:
    """Windows Yes/No box (stdlib ctypes). Elsewhere, or if it cannot be shown: no."""
    if os.name != "nt":
        return False
    try:
        import ctypes

        mb_yesno, mb_icon_question, mb_topmost, idyes = 0x04, 0x20, 0x40000, 6
        flags = mb_yesno | mb_icon_question | mb_topmost
        return ctypes.windll.user32.MessageBoxW(None, text, title, flags) == idyes
    except Exception:
        return False


def show_info(title: str, text: str) -> None:
    """Windows OK box (stdlib ctypes); silently skipped elsewhere or on failure."""
    if os.name != "nt":
        return
    try:
        import ctypes

        flags = 0x0 | 0x40 | 0x40000  # MB_OK | MB_ICONINFORMATION | MB_TOPMOST
        ctypes.windll.user32.MessageBoxW(None, text, title, flags)
    except Exception:
        return


def waiting_summary(engine) -> str | None:
    """What waits for the owner after a run (D-M02-12): review items, downloads, overflow."""
    from engine.themes.proposals import overflow

    rows = dict(engine.execute(
        "SELECT kind = 'm02_ir_download', count(*) FROM review_queue WHERE resolved_at IS NULL "
        "GROUP BY kind = 'm02_ir_download'").fetchall())  # fmt: skip
    downloads, reviews, waiting = rows.get(1, 0), rows.get(0, 0), len(overflow(engine))
    if not (downloads or reviews or waiting):
        return None
    parts = []
    if downloads:
        parts.append(f"{downloads} call document(s) to download")
    if reviews:
        parts.append(f"{reviews} review item(s) open")
    if waiting:
        parts.append(f"{waiting} M02 proposal(s) waiting for next week's queue")
    lines = "\n".join(parts)
    return f"The refresh finished.\n\n{lines}\n\nOpen the app: Review queue."


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scheduled", action="store_true", help="run as the nightly task")
    parser.add_argument("--if-missed", action="store_true",
                        help="only run if the last scheduled run was missed")  # fmt: skip
    parser.add_argument("--ask", action="store_true", help="ask before running (with --if-missed)")
    parser.add_argument("--config", default=str(ROOT / "config" / "watchlist.toml"))
    parser.add_argument("--skip-prices", action="store_true",
                        help="SEC step only (quick checks during development)")  # fmt: skip
    args = parser.parse_args()

    os.chdir(ROOT)  # data/ and logs/ are relative to the repo
    sys.path.insert(0, str(ROOT / "src"))
    from engine.refresh import last_success
    from engine.store.db import data_dir, open_db

    folder = data_dir()
    engine = open_db("engine", folder)
    if args.if_missed:
        slot = last_scheduled_slot(datetime.now())
        last = last_success(engine)
        last_local = (
            datetime.fromisoformat(last).astimezone().replace(tzinfo=None) if last else None
        )
        if last_local is not None and last_local >= slot - timedelta(minutes=5):
            return 3  # not missed: the scheduled run happened
        when = last_local.strftime("%Y-%m-%d %H:%M") if last_local else "never"
        slot_key = slot.isoformat(timespec="minutes")
        declined = engine.execute(
            "SELECT detail FROM refresh_state WHERE name = 'missed_declined'"
        ).fetchone()
        if args.ask and declined and declined[0] == slot_key:
            return 3  # owner said no for this slot; ask again after the next scheduled night
        if args.ask and not ask_yes_no(
            "Investment engine",
            f"The nightly SEC refresh scheduled for {slot:%Y-%m-%d %H:%M} did not run "
            f"(last successful run: {when}).\n\nRun the catch-up now? It reads SEC's daily "
            "index for the missed days and updates the watchlist companies.",
        ):
            engine.execute(
                "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) "
                "VALUES ('missed_declined', 'owner', ?, ?) ON CONFLICT (name) DO UPDATE SET "
                "fetched_at = excluded.fetched_at, detail = excluded.detail",
                (datetime.now(UTC).isoformat(timespec="seconds"), slot_key),
            )
            return 3

    from engine.store.lock import LockBusy, run_lock

    try:
        with run_lock(folder / "refresh.lock", "run_refresh"):
            code, summary, prep = _run(args, engine, folder)
    except LockBusy as e:
        print(f"Not starting a second run: {e}.")
        return 2
    # after the lock is released: a waiting box must not hold it (D-M02-51)
    if prep is not None and prep.candidates:
        ask_and_run_season(engine, folder, prep, summary)
    elif summary:
        show_info("Investment engine", summary)
    return code


def _run(args, engine, folder):
    from engine.refresh import format_report, load_config, run_refresh
    from engine.sec.client import SecClient, user_agent_from_env
    from engine.store.db import open_db
    from engine.store.http import SqliteCache, SqliteFetchLog

    corpus = open_db("corpus", folder, check_same_thread=False)
    client = SecClient(user_agent_from_env(), cache=SqliteCache(corpus),
                       log=SqliteFetchLog(engine))  # fmt: skip
    trigger = "missed-run prompt" if args.if_missed else (
        "scheduled" if args.scheduled else "manual")  # fmt: skip
    report = run_refresh(client, engine, corpus, load_config(Path(args.config)),
                         datetime.now(UTC), trigger=trigger)  # fmt: skip
    calls = calls_step(engine, corpus, report)
    calls += money_step(client, engine, corpus, report)
    calls += supply_step(client, engine, corpus, report)
    calls += financing_step(client, engine, corpus, report)
    calls += news_step(engine, corpus, report)
    calls += official_step(engine, report)
    background = args.scheduled or args.if_missed
    season_text, prep = seasonal_step(engine, corpus, report, background)
    calls += season_text
    skipped = "\nPrices (Tiingo): skipped (--skip-prices)\n"
    prices = skipped if args.skip_prices else prices_step(engine, report)
    text = format_report(report) + calls + prices
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    out = logs / f"refresh_{datetime.now():%Y%m%d-%H%M%S}.txt"
    out.write_text(text, encoding="utf-8")
    print(text)
    print(f"Report written to: {out}")
    corpus.close()
    # background runs tell the owner what waits — shown by main() after the lock is released
    summary = waiting_summary(engine) if background else None
    return (0 if report.status == "ok" else 1), summary, prep


if __name__ == "__main__":
    sys.exit(main())
