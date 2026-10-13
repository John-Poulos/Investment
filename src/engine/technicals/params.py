"""Frozen M09 parameters: `config/technicals.toml` (version `v1` in every row's `method`).

The built-in defaults equal the file (a test checks it), so a missing file computes the same
rows; a file with an unknown key or a non-numeric value is rejected at load (the refresh then
falls back to the defaults and says so).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

PATH = Path("config/technicals.toml")


class ParamsError(ValueError):
    pass


@dataclass(frozen=True)
class Params:
    version: str = "v1"
    # band
    band_window: int = 20
    pullback_returns: int = 20
    zone_1: float = 1.0
    zone_2: float = 2.0
    # trend
    ma_weeks: int = 40
    slope_weeks: int = 4
    flip_closes: int = 2
    slope_tolerance: float = 0.0025
    trend_min_bars: int = 45
    # momentum
    skip_weeks: int = 4
    lookback_weeks: int = 52
    # reversal
    rev_weeks: int = 4
    rev_sigma_weeks: int = 26
    extended_z: float = 2.0

    @property
    def mom_min_bars(self) -> int:
        return self.lookback_weeks + 1

    @property
    def rev_min_bars(self) -> int:
        return self.rev_weeks + self.rev_sigma_weeks + 1


# toml section.key → field
KEYS = {
    ("band", "window_weeks"): "band_window",
    ("band", "pullback_returns"): "pullback_returns",
    ("band", "zone_1"): "zone_1",
    ("band", "zone_2"): "zone_2",
    ("trend", "ma_weeks"): "ma_weeks",
    ("trend", "slope_weeks"): "slope_weeks",
    ("trend", "flip_closes"): "flip_closes",
    ("trend", "slope_tolerance"): "slope_tolerance",
    ("trend", "min_bars"): "trend_min_bars",
    ("momentum", "skip_weeks"): "skip_weeks",
    ("momentum", "lookback_weeks"): "lookback_weeks",
    ("reversal", "window_weeks"): "rev_weeks",
    ("reversal", "sigma_weeks"): "rev_sigma_weeks",
    ("reversal", "extended_z"): "extended_z",
}


def parse(data: dict) -> Params:
    kw: dict = {}
    version = data.get("version")
    if not isinstance(version, str) or not version:
        raise ParamsError('version must be text (e.g. "v1")')
    kw["version"] = version
    types = {f.name: f.type for f in fields(Params)}
    for section, body in data.items():
        if section == "version":
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
    """(params, error): a broken file yields the defaults and its error text."""
    try:
        return load(path), ""
    except ParamsError as e:
        return Params(), f"{path}: {e}; built-in v1 defaults used"
