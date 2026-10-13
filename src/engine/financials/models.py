"""Owner model tags (D-M04-8; M04 Part 1c): `config/company_models.toml`.

Six fixed tags, each with a one-line reason and a source; an unknown tag (or a missing
reason or source) is rejected at load; the app never writes the file. A tag overrides the
SEC industry code (SIC) and applies before the life-cycle stage. `before = "YYYY-MM-DD"`
keys a tag on period end (INFQ's shell years before the 2026-02-13 closing are
`spac_shell`; later periods carry no tag).

Routing per tag (docs/M04_FINANCIALS.md "Model tags", R1 brief): earnings quality,
dilution, survival-gate scope and health scores/CvD. Untagged financials (Fama-French 12
group 11, SIC 6000–6999) read "not applicable"; for SIC 6798 the engine may suggest `reit`
(a note only: the owner edits the file).
"""

from __future__ import annotations

import re
import sqlite3
import tomllib
from dataclasses import dataclass
from pathlib import Path

from engine.sec.identity import normalize_cik

MODELS = Path("config/company_models.toml")
TAGS = ("issuance_funded", "asset_treasury", "reit", "fund", "financial", "spac_shell")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# tag → (earnings quality, dilution, survival gate, health scores and CvD)
ROUTING: dict[str | None, tuple[str, str, str, str]] = {
    None: ("normal", "normal (D-M04-25)", "full", "normal"),
    "issuance_funded": (
        "normal",
        "review while the gate passes outside the warn band; "
        "else financing_pressure warns (D-M04-13)",
        "full (D-M04-13)",
        "normal; equity point per D-M04-65",
    ),  # fmt: skip
    "asset_treasury": (
        "NI, accruals, M-score not meaningful",
        "review (D-M04-25)",
        "liquidity-only",
        "Z not meaningful",
    ),  # fmt: skip
    "reit": ("excluded", "review", "liquidity-only", "excluded"),
    "fund": ("excluded", "excluded", "not applicable (D-M04-35)", "excluded"),
    "financial": ("excluded", "excluded", "not applicable (D-M04-35)", "excluded"),
    "spac_shell": (
        "excluded",
        "not meaningful",
        "trust only; text excluded (D-M04-34)",
        "excluded",
    ),  # fmt: skip
}
EXCLUDED = frozenset({"fund", "financial"})  # no stage, no peers, no flags


class ModelFileError(ValueError):
    """The tag file breaks a rule (unknown tag, missing reason or source, bad date)."""


@dataclass(frozen=True)
class ModelTag:
    tag: str
    ticker: str | None
    cik: str | None
    reason: str
    source: str
    before: str | None = None  # applies to periods ending before this date

    def applies(self, period_end: str | None) -> bool:
        if self.before is None:
            return True
        if period_end is None:  # "today": a dated tag has ended once its date has passed
            return False
        return period_end < self.before

    @property
    def scope(self) -> str:
        return f"periods ending before {self.before}" if self.before else "all periods"


@dataclass(frozen=True)
class ModelFile:
    path: str
    entries: tuple[ModelTag, ...]
    error: str = ""  # a rejected file: the error, and no tags apply

    def for_company(
        self, cik: str | None, ticker: str | None = None, period_end: str | None = None
    ) -> ModelTag | None:
        """The tag that applies to a company (and period end, when given)."""
        norm = normalize_cik(cik) if cik else None
        for e in self.entries:
            hit = (e.cik is not None and e.cik == norm) or (
                e.cik is None and ticker is not None and e.ticker == ticker.upper()
            )
            if hit and e.applies(period_end):
                return e
        return None

    def any_for(self, cik: str | None, ticker: str | None = None) -> ModelTag | None:
        """The company's entry whatever its period scope (for display)."""
        norm = normalize_cik(cik) if cik else None
        return next(
            (e for e in self.entries if (e.cik is not None and e.cik == norm)
             or (e.cik is None and ticker is not None and e.ticker == ticker.upper())),
            None,
        )  # fmt: skip


def parse(data: dict, path: str = str(MODELS)) -> ModelFile:
    """Validate the parsed TOML; raises ModelFileError on the first broken entry."""
    rows = data.get("company", [])
    if not isinstance(rows, list):
        raise ModelFileError("[[company]] entries expected")
    out = []
    for i, r in enumerate(rows, 1):
        where = f"entry {i}" + (f" ({r.get('ticker') or r.get('cik')})" if isinstance(r, dict)
                                else "")  # fmt: skip
        if not isinstance(r, dict):
            raise ModelFileError(f"{where}: not a table")
        unknown = set(r) - {"ticker", "cik", "tag", "reason", "source", "before"}
        if unknown:
            raise ModelFileError(f"{where}: unknown field(s) {', '.join(sorted(unknown))}")
        tag = r.get("tag")
        if tag not in TAGS:
            raise ModelFileError(f"{where}: unknown tag {tag!r} (allowed: {', '.join(TAGS)})")
        cik = r.get("cik")
        if cik is not None and (not isinstance(cik, str) or not re.fullmatch(r"\d{10}", cik)):
            raise ModelFileError(f"{where}: cik must be 10 digits as text")
        ticker = r.get("ticker")
        if cik is None and not ticker:
            raise ModelFileError(f"{where}: needs a cik or a ticker")
        for field in ("reason", "source"):
            if not str(r.get(field) or "").strip():
                raise ModelFileError(f"{where}: missing {field} (one line each, D-M04-8)")
        before = r.get("before")
        if before is not None:
            before = str(before)
            if not DATE.match(before):
                raise ModelFileError(f"{where}: before must be YYYY-MM-DD")
        out.append(ModelTag(tag, ticker.upper() if ticker else None, cik, r["reason"].strip(),
                            r["source"].strip(), before))  # fmt: skip
    return ModelFile(path, tuple(out))


def load(path: Path = MODELS) -> ModelFile:
    """Read the tag file. A missing file means no tags; a broken one raises."""
    if not path.exists():
        return ModelFile(str(path), ())
    with path.open("rb") as fh:
        try:
            data = tomllib.load(fh)
        except tomllib.TOMLDecodeError as e:
            raise ModelFileError(f"{path}: not valid TOML: {e}") from e
    return parse(data, str(path))


def load_safe(path: Path = MODELS) -> ModelFile:
    """For the refresh and the UI: a broken file applies no tags and carries the error."""
    try:
        return load(path)
    except ModelFileError as e:
        return ModelFile(str(path), (), str(e))


def is_ff12_financial(sic: str | None) -> bool:
    """Fama-French 12 group 11 (Money): SIC 6000–6999."""
    return bool(sic) and sic.isdigit() and 6000 <= int(sic) <= 6999


def route(
    engine: sqlite3.Connection,
    models: ModelFile,
    cik: str,
    ticker: str | None = None,
    period_end: str | None = None,
) -> tuple[str | None, str]:
    """(tag or None, how): tag first, then SIC (D-M04-8). An untagged FF12 group-11 company
    routes as `financial` ("not applicable")."""
    t = models.for_company(cik, ticker, period_end)
    if t is not None:
        return t.tag, f"model tag {t.tag} ({t.scope}): {t.reason}"
    row = engine.execute("SELECT sic FROM entity WHERE cik = ?", (normalize_cik(cik) or cik,))
    sic = (row.fetchone() or [None])[0]
    if is_ff12_financial(sic):
        how = f"untagged SIC {sic} (Fama-French 12 group 11): not applicable"
        if sic == "6798":
            how += "; a REIT? the owner may tag it reit"
        return "financial", how
    return None, f"no tag; SIC {sic or 'unknown'}"
