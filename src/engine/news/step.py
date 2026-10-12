"""The news step of a refresh run (M02 part 7a, D-M02-13, D-M02-58).

1. Company IR RSS feeds of watchlist/tracked companies (grade A).
2. The 11 trade-press feeds (grade B).
3. 8-K press releases already stored by the SEC step (local, grade A).
4. Finnhub company news per watchlist/tracked symbol since the last success; Massive as
   backup for symbols where Finnhub failed (≤ 10 a run, 5/min).
5. First mentions of accepted themes in the companies' own documents (local).
6. Last week's `m02_news` review item, once the week is over.
Never fails the run: errors are reported in its lines. Each batch is one short write
transaction (the app writes too, D-M02-12).
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta

from engine.news import config as news_config
from engine.news import digest, discover, first_mentions, rss, sec8k, store, vendors
from engine.news.fetch import Fetcher
from engine.news.match import CompanyMatcher, ThemeMatcher
from engine.sec.client import iso
from engine.sec.results import Failed


@dataclass
class NewsReport:
    lines: list[str] = field(default_factory=list)
    counts: Counter = field(default_factory=Counter)
    failures: list[str] = field(default_factory=list)


def _add(rep: NewsReport, label: str, c: store.StoreCounts) -> None:
    rep.counts[f"{label} seen"] += c.seen
    rep.counts[f"{label} new"] += c.new
    rep.counts["merged"] += c.merged


def _state_get(engine: sqlite3.Connection, name: str) -> str | None:
    r = engine.execute("SELECT fetched_at FROM refresh_state WHERE name = ?", (name,)).fetchone()
    return r[0] if r else None


def _state_set(engine: sqlite3.Connection, name: str, ref: str, now: datetime, detail: str) -> None:
    engine.execute(
        "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (name) DO UPDATE SET source_ref = excluded.source_ref, "
        "fetched_at = excluded.fetched_at, detail = excluded.detail",
        (name, ref, iso(now), detail),
    )


def run_news_step(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    companies: dict[str, str],
    now: datetime,
    *,
    fetcher: Fetcher | None = None,
    finnhub_key: str | None = None,
    massive_key: str | None = None,
    cfg: news_config.NewsConfig | None = None,
    feeds: bool = True,
    vendor_news: bool = True,
    preview: bool = False,
) -> NewsReport:
    """companies: ticker → cik for core, promoted and tracked names."""
    rep = NewsReport(lines=["News (M02 part 7a):"])
    try:
        _run(engine, corpus, companies, now, rep, fetcher, finnhub_key, massive_key,
             cfg or news_config.load(), feeds, vendor_news, preview)  # fmt: skip
    except Exception as e:  # the news step must not break the run report
        if engine.in_transaction:
            engine.execute("ROLLBACK")
        rep.lines.append(f"error — {type(e).__name__}: {e}")
    return rep


def _run(engine, corpus, companies, now, rep, fetcher, finnhub_key, massive_key, cfg,
         feeds, vendor_news, preview) -> None:  # fmt: skip
    fetcher = fetcher or Fetcher(engine, secrets=tuple(k for k in (finnhub_key, massive_key) if k))
    themes, cos = ThemeMatcher(engine), CompanyMatcher(engine)
    ciks = set(companies.values())
    extra, extra_domains = discover.confirmed(engine, companies, cfg)
    if extra_domains:  # confirmed feeds' domains grade vendor items A, like config domains
        cfg = replace(cfg, company_domains=extra_domains | cfg.company_domains)

    def put(label: str, items) -> None:
        _add(rep, label, store.store_all(engine, items, cfg, now, themes, cos))

    if feeds:
        ir = cfg.ir_feeds(set(companies)) + extra
        trade = list(cfg.trade)
        for f in ir + trade:
            res = rss.fetch(
                engine, fetcher, f, now, cik=companies.get(f.key) if f.channel == "ir_rss" else None
            )
            rep.counts[f"{f.channel} {res.status}"] += 1
            if res.status == "failed":
                rep.failures.append(f"{f.channel} {f.key} ({f.url}): {res.detail}")
            put(f.channel, res.items)
        rep.lines.append(
            f"feeds: IR {len(ir)} (ok {rep.counts['ir_rss ok']}, not modified "
            f"{rep.counts['ir_rss not modified']}, failed {rep.counts['ir_rss failed']}), "
            f"trade press {len(trade)} (ok {rep.counts['trade ok']}, not modified "
            f"{rep.counts['trade not modified']}, failed {rep.counts['trade failed']})"
        )
    put("sec_8k", sec8k.releases(engine, corpus, ciks, now))

    if vendor_news:
        _vendors(engine, companies, now, rep, fetcher, finnhub_key, massive_key, cfg, put)
    if feeds:
        rep.lines += discover.run(engine, fetcher, finnhub_key, companies, cfg, now)

    c = rep.counts
    rep.lines.append(
        "items: " + ", ".join(
            f"{ch} {c[ch + ' new']} new of {c[ch + ' seen']}"
            for ch in ("ir_rss", "trade", "sec_8k", "finnhub", "massive") if c[ch + " seen"]
        ) + f"; merged as duplicates {c['merged']}"
    )  # fmt: skip
    themed = engine.execute(
        "SELECT count(DISTINCT item_id) FROM news_theme t JOIN news_item i USING (item_id) "
        "WHERE i.first_seen_at = ?", (iso(now),)
    ).fetchone()[0]  # fmt: skip
    rep.lines.append(f"new items with an accepted theme phrase: {themed}")

    firsts = first_mentions.scan(engine, corpus, ciks, now)
    rep.lines.append(f"first mentions of an accepted theme: {len(firsts)}")
    for m in firsts:
        rep.lines.append(f"  {_ticker(companies, m.cik)} — {m.phrase} ({m.source}, {m.dated})")

    tiers = digest.tier_ciks(engine, {v: k for k, v in companies.items()})
    week = digest.last_week_start(now)
    res = digest.propose_week(engine, week, tiers, now)
    rep.lines.append(f"weekly news item {week.date()}: {res}")
    if preview:
        res = digest.propose_week(engine, week + timedelta(days=7), tiers, now, preview=True)
        rep.lines.append(f"preview of this week so far: {res}")
    for f in rep.failures:
        rep.lines.append(f"  failed: {f}")


def _ticker(companies: dict[str, str], cik: str) -> str:
    return next((t for t, c in companies.items() if c == cik), cik)


def _vendors(engine, companies, now, rep, fetcher, finnhub_key, massive_key, cfg, put) -> None:
    today = now.date()
    backup: list[str] = []
    if not finnhub_key:
        rep.lines.append("Finnhub: skipped — FINNHUB_API_KEY is not set in .env")
        backup = sorted(companies)
    else:
        ok = empty = 0
        for symbol in sorted(companies):
            name = f"news:finnhub:{symbol}"
            last = _state_get(engine, name)
            start = (date.fromisoformat(last[:10]) - timedelta(days=cfg.finnhub_overlap_days)
                     if last else today - timedelta(days=cfg.finnhub_first_days))  # fmt: skip
            got = vendors.finnhub_news(
                fetcher, finnhub_key, symbol, start, today, companies[symbol]
            )
            if isinstance(got, Failed):
                rep.failures.append(f"finnhub {symbol}: {got.reason}")
                backup.append(symbol)
                if got.throttled:
                    rep.lines.append(f"Finnhub: stopped at {symbol} (throttled); the rest next run")
                    break
                continue
            put("finnhub", got)
            _state_set(engine, name, vendors.FINNHUB_URL, now, f"{len(got)} items from {start}")
            ok += 1
            empty += not got
        rep.lines.append(f"Finnhub: {ok} symbol(s) ok ({empty} with no news in the window), "
                         f"{len(backup)} failed")  # fmt: skip
    if not backup:
        return
    if not massive_key:
        rep.lines.append("Massive (backup): skipped — MASSIVE_API_KEY is not set in .env")
        return
    done = 0
    for symbol in backup[: cfg.massive_max_per_run]:
        name = f"news:massive:{symbol}"
        last = _state_get(engine, name)
        start = (date.fromisoformat(last[:10]) - timedelta(days=cfg.finnhub_overlap_days)
                 if last else today - timedelta(days=cfg.finnhub_first_days))  # fmt: skip
        got = vendors.massive_news(fetcher, massive_key, symbol, start, companies[symbol])
        if isinstance(got, Failed):
            rep.failures.append(f"massive {symbol}: {got.reason}")
            if got.throttled:
                break
            continue
        put("massive", got)
        _state_set(engine, name, vendors.MASSIVE_URL, now, f"{len(got)} items from {start}")
        done += 1
    tried = min(len(backup), cfg.massive_max_per_run)
    left = len(backup) - tried
    rep.lines.append(f"Massive (backup): {done} of {tried} symbol(s) ok"
                     + (f"; {left} left for the next run" if left else ""))  # fmt: skip
