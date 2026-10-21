"""M08 parameters and owner overrides: `config/valuation.toml` (version `v1` in every row).

The built-in defaults equal the file (a test checks it). A broken file is rejected at load;
the refresh then uses the defaults with no overrides and says so (as M09's params).
Overrides (D-M08-1, rule 5): per company `headline` (a `val_*` row or `mnav`) and
`cyclical` (true / false), each with a one-line `reason`; the owner's entry wins.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

from engine.sec.identity import normalize_cik
from engine.valuation.measures import HEADLINE_KEYS

PATH = Path("config/valuation.toml")


class ParamsError(ValueError):
    pass


@dataclass(frozen=True)
class Override:
    ticker: str | None
    cik: str | None
    reason: str
    headline: str | None = None
    cyclical: bool | None = None

    def matches(self, cik: str, ticker: str | None) -> bool:
        if self.cik is not None:
            return self.cik == (normalize_cik(cik) or cik)
        return ticker is not None and self.ticker == ticker.upper()


@dataclass(frozen=True)
class Params:
    version: str = "v1"
    own_min_points: int = 20
    peer_min: int = 5
    close_tolerance_days: int = 5
    cyclical_years: int = 10
    cyclical_min_years: int = 5
    margin_range_pp: float = 30.0
    nep_swing_pp: float = 5.0
    nep_min_years: int = 3
    value_trap_pctile: float = 20.0
    # Part 2: estimates and PEG (D-M08-5, -6, -14…)
    peg_growth_cap_pct: float = 50.0
    flat_band_pct: float = 0.5
    min_abs_eps: float = 0.10
    min_count_dispersion: int = 3
    walk_down_days: int = 30
    snapshot_max_age_days: int = 28
    snapshot_every_days: int = 7
    no_coverage_retry_days: int = 28
    overrides: tuple[Override, ...] = field(default=())

    def override(self, cik: str, ticker: str | None) -> Override | None:
        return next((o for o in self.overrides if o.matches(cik, ticker)), None)


KEYS = {
    ("history", "own_min_points"): "own_min_points",
    ("history", "peer_min"): "peer_min",
    ("history", "close_tolerance_days"): "close_tolerance_days",
    ("cyclical", "years"): "cyclical_years",
    ("cyclical", "min_years"): "cyclical_min_years",
    ("cyclical", "margin_range_pp"): "margin_range_pp",
    ("nep", "swing_pp"): "nep_swing_pp",
    ("nep", "min_years"): "nep_min_years",
    ("value_trap", "pctile"): "value_trap_pctile",
    ("peg", "growth_cap_pct"): "peg_growth_cap_pct",
    ("estimates", "flat_band_pct"): "flat_band_pct",
    ("estimates", "min_abs_eps"): "min_abs_eps",
    ("estimates", "min_count_dispersion"): "min_count_dispersion",
    ("estimates", "walk_down_days"): "walk_down_days",
    ("estimates", "snapshot_max_age_days"): "snapshot_max_age_days",
    ("estimates", "snapshot_every_days"): "snapshot_every_days",
    ("estimates", "no_coverage_retry_days"): "no_coverage_retry_days",
}


def _override(i: int, r: object) -> Override:
    where = f"[[company]] {i}"
    if not isinstance(r, dict):
        raise ParamsError(f"{where}: not a table")
    unknown = set(r) - {"ticker", "cik", "headline", "cyclical", "reason"}
    if unknown:
        raise ParamsError(f"{where}: unknown field(s) {', '.join(sorted(unknown))}")
    cik, ticker = r.get("cik"), r.get("ticker")
    if cik is not None and (not isinstance(cik, str) or not re.fullmatch(r"\d{10}", cik)):
        raise ParamsError(f"{where}: cik must be 10 digits as text")
    if cik is None and not (isinstance(ticker, str) and ticker.strip()):
        raise ParamsError(f"{where}: needs a cik or a ticker")
    if not str(r.get("reason") or "").strip():
        raise ParamsError(f"{where}: missing reason (one line)")
    headline = r.get("headline")
    if headline is not None and headline not in HEADLINE_KEYS:
        raise ParamsError(f"{where}: headline must be one of {', '.join(HEADLINE_KEYS)}")
    cyc = r.get("cyclical")
    if cyc is not None and not isinstance(cyc, bool):
        raise ParamsError(f"{where}: cyclical must be true or false")
    if headline is None and cyc is None:
        raise ParamsError(f"{where}: sets neither headline nor cyclical")
    return Override(
        ticker.strip().upper() if ticker else None, cik, r["reason"].strip(), headline, cyc
    )


def parse(data: dict) -> Params:
    version = data.get("version")
    if not isinstance(version, str) or not version:
        raise ParamsError('version must be text (e.g. "v1")')
    kw: dict = {"version": version}
    types = {f.name: f.type for f in fields(Params)}
    for section, body in data.items():
        if section in ("version", "company"):
            continue
        if not isinstance(body, dict):
            raise ParamsError(f"unknown key {section!r}")
        for key, value in body.items():
            name = KEYS.get((section, key))
            if name is None:
                raise ParamsError(f"unknown key [{section}] {key}")
            if isinstance(value, bool) or not isinstance(value, int | float):
                raise ParamsError(f"[{section}] {key} must be a number")
            if types[name] == "int" and (not isinstance(value, int) or value < 1):
                raise ParamsError(f"[{section}] {key} must be a positive whole number")
            kw[name] = value if types[name] == "int" else float(value)
    rows = data.get("company", [])
    if not isinstance(rows, list):
        raise ParamsError("[[company]] entries expected")
    kw["overrides"] = tuple(_override(i, r) for i, r in enumerate(rows, 1))
    return Params(**kw)


def load(path: Path = PATH) -> Params:
    if not path.exists():
        return Params()
    with path.open("rb") as fh:
        try:
            data = tomllib.load(fh)
        except tomllib.TOMLDecodeError as e:
            raise ParamsError(f"{path}: not valid TOML: {e}") from e
    return parse(data)


def load_safe(path: Path = PATH) -> tuple[Params, str]:
    """(params, error): a broken file yields the defaults (no overrides) and its error."""
    try:
        return load(path), ""
    except ParamsError as e:
        return Params(), f"{path}: {e}; built-in v1 defaults used, no overrides"
