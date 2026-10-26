"""M06 parameters: `config/moat.toml` (version `v1` in every row's method).

The built-in defaults equal the file (a test checks it). A broken file is rejected at load;
the refresh then uses the defaults and says so (the M08 / M09 pattern). Values marked † in
the file are sourced starting values, never tuned on the watchlist alone (D32).
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

PATH = Path("config/moat.toml")


class ParamsError(ValueError):
    pass


@dataclass(frozen=True)
class Params:
    version: str = "v1"
    hurdle: float = 0.08
    band_pp: float = 0.02
    window_years: int = 10
    min_years: int = 7
    persistent_share: float = 0.80
    recent_years: int = 3
    rd_heavy_share: float = 0.10
    my_horizon_years: int = 5


KEYS = {
    ("quant", "hurdle"): "hurdle",
    ("quant", "band_pp"): "band_pp",
    ("quant", "window_years"): "window_years",
    ("quant", "min_years"): "min_years",
    ("quant", "persistent_share"): "persistent_share",
    ("quant", "recent_years"): "recent_years",
    ("quant", "rd_heavy_share"): "rd_heavy_share",
    ("gate", "my_horizon_years"): "my_horizon_years",
}


def parse(data: dict) -> Params:
    version = data.get("version")
    if not isinstance(version, str) or not version:
        raise ParamsError('version must be text (e.g. "v1")')
    kw: dict = {"version": version}
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
            if types[name] == "int":
                if not isinstance(value, int) or value < 1:
                    raise ParamsError(f"[{section}] {key} must be a positive whole number")
                kw[name] = value
            else:
                if not 0 <= float(value) <= 1:
                    raise ParamsError(f"[{section}] {key} must be a share between 0 and 1")
                kw[name] = float(value)
    p = Params(**kw)
    if p.min_years > p.window_years:
        raise ParamsError("[quant] min_years cannot exceed window_years")
    if p.recent_years > p.window_years:
        raise ParamsError("[quant] recent_years cannot exceed window_years")
    return p


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
    """(params, error): a broken file yields the built-in defaults and its error."""
    try:
        return load(path), ""
    except ParamsError as e:
        return Params(), f"{path}: {e}; built-in v1 defaults used"
