"""`config/news.toml`: IR feeds, trade press, grade lists (D-M02-13)."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

NEWS = Path("config/news.toml")


@dataclass(frozen=True)
class Feed:
    channel: str  # ir_rss or trade
    key: str  # ticker (IR) or outlet key (trade)
    name: str
    url: str

    @property
    def state_key(self) -> str:
        return f"{self.channel}:{self.key}:{self.url}"


@dataclass(frozen=True)
class NewsConfig:
    ir: dict[str, tuple[str, ...]] = field(default_factory=dict)  # ticker → feed URLs
    company_domains: dict[str, str] = field(default_factory=dict)  # domain → ticker
    trade: tuple[Feed, ...] = ()
    outlets: frozenset[str] = frozenset()  # grade-B domains
    sources: frozenset[str] = frozenset()  # grade-B vendor source names (lowercase)
    finnhub_first_days: int = 30
    finnhub_overlap_days: int = 2
    massive_max_per_run: int = 10

    def ir_feeds(self, tickers: set[str] | None = None) -> list[Feed]:
        return [
            Feed("ir_rss", t, t, u)
            for t, urls in self.ir.items()
            if tickers is None or t in tickers
            for u in urls
        ]


def domain(url: str | None) -> str:
    """Host without 'www.'; '' when the URL has none."""
    host = (urlsplit(url or "").hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


def matches_domain(host: str, domains: frozenset[str] | set[str] | dict[str, str]) -> str | None:
    """The listed domain that `host` is or is a subdomain of."""
    parts = host.split(".")
    for i in range(len(parts) - 1):
        d = ".".join(parts[i:])
        if d in domains:
            return d
    return None


def load(path: Path = NEWS) -> NewsConfig:
    if not path.exists():
        return NewsConfig()
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    ir: dict[str, tuple[str, ...]] = {}
    company_domains: dict[str, str] = {}
    for ticker, v in (data.get("ir") or {}).items():
        t = ticker.upper()
        if v.get("feeds"):
            ir[t] = tuple(v["feeds"])
        for d in v.get("domains") or ():
            company_domains[d.lower()] = t
    trade = tuple(
        Feed("trade", k, v.get("name") or k, v["url"])
        for k, v in (data.get("trade") or {}).items()
        if v.get("url")
    )
    grades = data.get("grades") or {}
    outlets = {d.lower() for d in grades.get("outlets") or ()} | {domain(f.url) for f in trade}
    fh = data.get("finnhub") or {}
    ms = data.get("massive") or {}
    return NewsConfig(
        ir=ir,
        company_domains=company_domains,
        trade=trade,
        outlets=frozenset(outlets),
        sources=frozenset(s.lower() for s in grades.get("sources") or ()),
        finnhub_first_days=int(fh.get("first_days", 30)),
        finnhub_overlap_days=int(fh.get("overlap_days", 2)),
        massive_max_per_run=int(ms.get("max_per_run", 10)),
    )
