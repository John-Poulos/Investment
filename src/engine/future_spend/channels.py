"""Spend channel (D-M05-1): `config/m05_channels.toml`, owner-edited; the engine never writes it.

Channels: `fabless`, `outsourced` (R9: commitments lead, the capex signals are info),
`fab_owner`, `hyperscaler`, `long_cycle`, `manufacturer` (every gauge, capex signals carry
weight) and `n/a` (MSTR, ETV: every M05 row "missing: not applicable (channel n/a)"). A
company not listed reads "channel unset": every gauge shown, `commitment_cover` info only
(Part 2). M04's model-tag loader ignores this file (D-M04-8 takes only its six tags).

Keyed like M04's file: `cik` (10 digits, wins when present; tickers can be recycled,
D-M04-74) and/or `ticker`. An unknown channel or a malformed entry rejects the whole file;
the refresh and the app then read every company as "channel unset" and show the error.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from engine.sec.identity import normalize_cik

CHANNELS_FILE = Path("config/m05_channels.toml")
CHANNELS = ("fabless", "outsourced", "fab_owner", "hyperscaler", "long_cycle", "manufacturer",
            "n/a")  # fmt: skip
COMMITMENTS_LEAD = frozenset({"fabless", "outsourced"})  # R9: capex signals are info
NOT_APPLICABLE = "n/a"
UNSET = "unset"


class ChannelFileError(ValueError):
    """The channel file breaks a rule (unknown channel, bad CIK, no key)."""


@dataclass(frozen=True)
class Channel:
    channel: str  # one of CHANNELS, or "unset"
    ticker: str | None = None
    cik: str | None = None
    note: str = ""

    @property
    def commitments_lead(self) -> bool:
        return self.channel in COMMITMENTS_LEAD

    @property
    def not_applicable(self) -> bool:
        return self.channel == NOT_APPLICABLE

    def text(self) -> str:
        if self.channel == UNSET:
            return "channel unset (every gauge shown; config/m05_channels.toml)"
        return f"channel {self.channel}" + (f" ({self.note})" if self.note else "")


@dataclass(frozen=True)
class ChannelFile:
    path: str
    entries: tuple[Channel, ...]
    error: str = ""

    def for_company(self, cik: str | None, ticker: str | None = None) -> Channel:
        norm = normalize_cik(cik) if cik else None
        for e in self.entries:
            if e.cik is not None and e.cik == norm:
                return e
        for e in self.entries:
            if e.cik is None and ticker is not None and e.ticker == ticker.upper():
                return e
        return Channel(UNSET, ticker, norm)


def parse(data: dict, path: str = str(CHANNELS_FILE)) -> ChannelFile:
    rows = data.get("company", [])
    if not isinstance(rows, list):
        raise ChannelFileError("[[company]] entries expected")
    out = []
    for i, r in enumerate(rows, 1):
        if not isinstance(r, dict):
            raise ChannelFileError(f"entry {i}: not a table")
        where = f"entry {i} ({r.get('ticker') or r.get('cik')})"
        unknown = set(r) - {"ticker", "cik", "channel", "note"}
        if unknown:
            raise ChannelFileError(f"{where}: unknown field(s) {', '.join(sorted(unknown))}")
        ch = r.get("channel")
        if ch not in CHANNELS:
            raise ChannelFileError(f"{where}: unknown channel {ch!r} (allowed: "
                                   f"{', '.join(CHANNELS)})")  # fmt: skip
        cik = r.get("cik")
        if cik is not None and (not isinstance(cik, str) or not re.fullmatch(r"\d{10}", cik)):
            raise ChannelFileError(f"{where}: cik must be 10 digits as text")
        ticker = r.get("ticker")
        if cik is None and not ticker:
            raise ChannelFileError(f"{where}: needs a cik or a ticker")
        out.append(Channel(ch, str(ticker).upper() if ticker else None, cik,
                           str(r.get("note") or "").strip()))  # fmt: skip
    return ChannelFile(path, tuple(out))


def load(path: Path = CHANNELS_FILE) -> ChannelFile:
    """A missing file means every company is unset; a broken one raises."""
    if not path.exists():
        return ChannelFile(str(path), ())
    with path.open("rb") as fh:
        try:
            data = tomllib.load(fh)
        except tomllib.TOMLDecodeError as e:
            raise ChannelFileError(f"{path}: not valid TOML: {e}") from e
    return parse(data, str(path))


def load_safe(path: Path = CHANNELS_FILE) -> ChannelFile:
    """For the refresh and the app: a broken file reads every company as unset, with the error."""
    try:
        return load(path)
    except ChannelFileError as e:
        return ChannelFile(str(path), (), str(e))
