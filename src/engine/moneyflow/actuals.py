"""Actual capex on each company's own definition (D-M02-29, D-M02-32).

Recipe from the guidance clause:
- "including principal payments on finance leases" → PP&E payments + finance-lease
  principal (Meta);
- "including finance leases" → PP&E payments + new finance-lease right-of-use assets,
  always approximate (Microsoft: assets obtained, not principal paid);
- no clause → PP&E payments, fallback productive assets (broader: includes software and
  intangibles; labelled);
- `config/capex_definitions.toml` overrides a company's recipe (Amazon's cash capex).
The first plus term is required; any other missing term makes the value approximate,
"excludes …".

Shown actual (D-M02-32): a recipe that agrees with a stated actual within 1% is
"reconciled"; when the recipe is approximate, partial or off by more than 1%, the
stated figure is shown with the recipe and the gap beside it (a gap on an exact recipe
also raises an `m02_capex_gap` review item); with no statement the recipe stands with
its label; with no recipe value the stated figure stands alone. Missing stays missing.
"""

from __future__ import annotations

import re
import sqlite3
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from engine.moneyflow.periods import (
    Span,
    calendar_fiscal,
    fiscal_year_end,
    span_of,
    tag_points,
    value_for,
)
from engine.moneyflow.stated import StatedRow, stated_for
from engine.sec.xbrl_facts import Point

DEFINITIONS = Path("config/capex_definitions.toml")
TOLERANCE = 0.01  # reconciled within 1%
PPE = "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment"
PRODUCTIVE = "us-gaap:PaymentsToAcquireProductiveAssets"
LEASE_PRINCIPAL = "us-gaap:FinanceLeasePrincipalPayments"
LEASE_ROU = "us-gaap:RightOfUseAssetObtainedInExchangeForFinanceLeaseLiability"
_PRINCIPAL = re.compile(
    r"principal (?:payments? )?(?:on|of|for|under) finance leases?"
    r"|finance[- ]lease principal",
    re.IGNORECASE,
)
_FIN_LEASE = re.compile(r"\bfinance leases?\b", re.IGNORECASE)
_NAMES = {
    PPE: "payments for property and equipment",
    PRODUCTIVE: "payments for productive assets",
    LEASE_PRINCIPAL: "finance-lease principal payments",
    LEASE_ROU: "new finance-lease assets",
}


@dataclass(frozen=True)
class Recipe:
    key: str
    label: str
    plus: tuple[str, ...]
    minus: tuple[str, ...] = ()
    approximate: bool = False
    fallback: str | None = None  # replaces plus[0] when it has no value (labelled broader)
    source: str = "clause"  # clause | override | default


@dataclass(frozen=True)
class RecipeValue:
    value: float
    approximate: bool
    note: str  # "", "approximate: excludes …", "fallback: … (broader)"
    how: str  # tags and periods used
    recipe: Recipe


def name_of(term: str) -> str:
    return _NAMES.get(term, term)


def load_overrides(path: Path = DEFINITIONS) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {}
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    return {k.upper(): v for k, v in data.items() if isinstance(v, dict)}


def recipe_for(clause: str | None, override: dict[str, Any] | None = None) -> Recipe:
    if override:
        return Recipe(
            "override",
            override.get("definition") or "company definition (config/capex_definitions.toml)",
            tuple(override.get("plus") or (PPE,)),
            tuple(override.get("minus") or ()),
            bool(override.get("approximate", False)),
            None,
            "override",
        )
    if clause and _PRINCIPAL.search(clause):
        return Recipe(
            "ppe+lease_principal", "PP&E payments + finance-lease principal", (PPE, LEASE_PRINCIPAL)
        )
    if clause and _FIN_LEASE.search(clause):
        return Recipe(
            "ppe+lease_assets",
            "PP&E payments + new finance-lease assets",
            (PPE, LEASE_ROU),
            approximate=True,
        )
    if clause:
        return Recipe(
            "ppe",
            f'PP&E payments (clause not mapped: "{clause}")',
            (PPE,),
            approximate=True,
            fallback=PRODUCTIVE,
        )
    return Recipe("ppe", "PP&E payments", (PPE,), fallback=PRODUCTIVE, source="default")


class Book:
    """Per-company cache of tag points (one build per tag)."""

    def __init__(self, engine: sqlite3.Connection, cik: str) -> None:
        self.engine, self.cik = engine, cik
        self.fye = fiscal_year_end(engine, cik)
        self._points: dict[str, tuple[Point, ...]] = {}

    def points(self, term: str) -> tuple[Point, ...]:
        if term not in self._points:
            tax, _, tag = term.partition(":")
            built = tag_points(self.engine, self.cik, tax, tag)
            self._points[term] = built.points if built else ()
        return self._points[term]


def compute(book: Book, recipe: Recipe, span: Span) -> RecipeValue | None:
    first = recipe.plus[0]
    found = value_for(book.points(first), span)
    notes = []
    if found is None and recipe.fallback:
        found = value_for(book.points(recipe.fallback), span)
        if found is not None:
            notes.append(
                f"fallback: {name_of(recipe.fallback)} (broader: includes software and intangibles)"
            )
    if found is None:
        return None
    total, how, missing = found.value, [f"{name_of(first)} {found.how}"], []
    for sign, terms in ((1, recipe.plus[1:]), (-1, recipe.minus)):
        for t in terms:
            f = value_for(book.points(t), span)
            if f is None:
                missing.append(name_of(t))
                continue
            total += sign * f.value
            how.append(f"{'+' if sign > 0 else '−'} {name_of(t)}")
    if missing:
        notes.append("approximate: excludes " + ", ".join(missing))
    approximate = recipe.approximate or bool(missing) or bool(notes and "fallback" in notes[0])
    return RecipeValue(total, approximate, "; ".join(notes), "; ".join(how), recipe)


@dataclass(frozen=True)
class Actual:
    period: str
    shown: float | None
    source: str  # recipe | stated | none
    status: str  # reconciled | gap | approximate | no statement | stated only | missing
    recipe: RecipeValue | None
    stated: StatedRow | None
    gap: float | None  # (recipe − stated) ÷ stated
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def label(self) -> str:
        if self.status == "reconciled":
            return f"reconciled ({abs(self.gap or 0):.1%})"
        if self.status in ("gap", "approximate") and self.gap is not None:
            return f"stated shown; recipe ≈, gap {self.gap:+.1%}"
        return self.status


def _stated_key(label: str, fye: str | None) -> str:
    """CY2026 on a calendar-year company is stated as FY2026."""
    if label.startswith("CY") and calendar_fiscal(fye):
        return "FY" + label[2:]
    return label


def actual_for(
    book: Book,
    label: str,
    clause: str | None,
    override: dict[str, Any] | None = None,
    stated: dict[str, StatedRow] | None = None,
) -> Actual:
    span = span_of(label, book.fye)
    stated = stated if stated is not None else stated_for(book.engine, book.cik)
    st = stated.get(_stated_key(label, book.fye))
    rv = compute(book, recipe_for(clause, override), span) if span else None
    if rv is None and st is None:
        return Actual(label, None, "none", "missing", None, None, None)
    if rv is None:
        return Actual(label, st.value, "stated", "stated only", None, st, None)
    if st is None:
        status = "approximate" if rv.approximate else "no statement"
        return Actual(label, rv.value, "recipe", status, rv, None, None)
    gap = (rv.value - st.value) / st.value
    if abs(gap) <= TOLERANCE and not rv.approximate:
        return Actual(label, rv.value, "recipe", "reconciled", rv, st, gap)
    status = "approximate" if rv.approximate else "gap"
    return Actual(label, st.value, "stated", status, rv, st, gap)


def overrides_by_cik(engine: sqlite3.Connection, path: Path = DEFINITIONS) -> dict[str, dict]:
    """Override sections keyed by CIK (tickers resolved through the stored ticker table)."""
    out = {}
    for ticker, section in load_overrides(path).items():
        row = engine.execute(
            "SELECT cik FROM ticker WHERE ticker = ? AND valid_to IS NULL", (ticker,)
        ).fetchone()
        if row:
            out[row[0]] = section | {"ticker": ticker}
    return out


def latest_clause(engine: sqlite3.Connection, cik: str) -> str | None:
    """The clause of the company's latest capex guidance row, if any."""
    row = engine.execute(
        "SELECT clause FROM guidance WHERE cik = ? AND metric = 'capex' AND clause IS NOT NULL "
        "ORDER BY stated_on DESC LIMIT 1",
        (cik,),
    ).fetchone()
    return row[0] if row else None
