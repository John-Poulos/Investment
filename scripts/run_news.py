"""News (M02 part 7a): IR RSS, trade press, 8-K releases, Finnhub/Massive, weekly item.

    uv run python scripts/run_news.py --preview     # live check: everything + this week so far
    uv run python scripts/run_news.py --feeds-only  # RSS feeds and 8-K releases, no vendors
    uv run python scripts/run_news.py --rematch     # re-run matching after theme/alias edits

No SEC requests (8-K releases come from the stored corpus). Finnhub ~1 request per
watchlist/tracked symbol (60/min free tier), Massive only where Finnhub failed (≤ 10,
5/min), each RSS feed once (conditional GET). Writes logs/news_<time>.txt.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from engine.calls.transcripts import symbol_cik  # noqa: E402
from engine.news import match  # noqa: E402
from engine.news.step import run_news_step  # noqa: E402
from engine.news.vendors import key_from_env  # noqa: E402
from engine.refresh import load_config  # noqa: E402
from engine.store.db import open_db  # noqa: E402
from engine.themes import tiers  # noqa: E402


def companies(engine) -> dict[str, str]:
    out: dict[str, str] = {}
    for t in load_config(ROOT / "config" / "watchlist.toml").tickers:
        if cik := symbol_cik(engine, t):
            out[t] = cik
    for m in tiers.members(engine):
        out.setdefault(m.ticker, m.cik)
    return out


def summary(engine) -> list[str]:
    lines = ["", "Stored news by channel and grade:"]
    for r in engine.execute(
        "SELECT channel, grade, count(*) n FROM news_source GROUP BY channel, grade "
        "ORDER BY channel, grade"
    ):
        lines.append(f"  {r['channel']} {r['grade']}: {r['n']}")
    origins = Counter()
    for r in engine.execute("SELECT origin, grade FROM news_source WHERE channel IN "
                            "('finnhub', 'massive')"):  # fmt: skip
        origins[(r["origin"] or "?", r["grade"])] += 1
    if origins:
        lines.append("Finnhub/Massive origins (top 15; edit [grades] in config/news.toml):")
        lines += [f"  {o} → {g}: {n}" for (o, g), n in origins.most_common(15)]
    lines.append("Items per theme (all stored):")
    for r in engine.execute(
        "SELECT th.name, count(*) n, count(DISTINCT c.cik) cos FROM news_theme t "
        "JOIN theme th USING (theme_id) LEFT JOIN news_company c USING (item_id) "
        "GROUP BY th.theme_id ORDER BY n DESC"
    ):
        lines.append(f"  {r['name']}: {r['n']} item(s), {r['cos']} compan(ies) named")
    multi = engine.execute("SELECT count(*) FROM (SELECT item_id FROM news_source "
                           "GROUP BY item_id HAVING count(*) > 1)").fetchone()[0]  # fmt: skip
    lines.append(f"Items with more than one source (deduped): {multi}")
    lines.append("Sample deduped items (up to 5):")
    for r in engine.execute(
        "SELECT i.title, group_concat(s.channel || ':' || s.feed, ', ') src FROM news_item i "
        "JOIN news_source s USING (item_id) GROUP BY i.item_id HAVING count(*) > 1 "
        "ORDER BY i.item_id DESC LIMIT 5"
    ):
        lines.append(f"  {r['title'][:110]} ← {r['src']}")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--preview", action="store_true",
                        help="also build this week's news item so far (key …:preview)")  # fmt: skip
    parser.add_argument("--feeds-only", action="store_true", help="skip Finnhub/Massive")
    parser.add_argument("--rematch", action="store_true", help="re-run matching only")
    args = parser.parse_args()
    os.chdir(ROOT)
    engine = open_db("engine")
    if args.rematch:
        print(f"re-matched {match.rematch_all(engine)} item(s)")
        return 0
    corpus = open_db("corpus")
    now = datetime.now(UTC)
    rep = run_news_step(engine, corpus, companies(engine), now,
                        finnhub_key=key_from_env("FINNHUB_API_KEY"),
                        massive_key=key_from_env("MASSIVE_API_KEY"),
                        vendor_news=not args.feeds_only, preview=args.preview)  # fmt: skip
    text = "\n".join(rep.lines + summary(engine)) + "\n"
    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    out = logs / f"news_{datetime.now():%Y%m%d-%H%M%S}.txt"
    out.write_text(text, encoding="utf-8")
    print(text)
    print(f"Report written to: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
