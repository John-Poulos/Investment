"""Where a guidance statement came from, and how it is labelled (D-M02-21).

Documents not filed with SEC carry synthetic accessions in corpus.db:
`AV-<SYMBOL>-<YYYYQn>` for an Alpha Vantage call transcript (fiscal label) and
`IR-<SYMBOL>-<YYYYQn>-<kind>` for a company IR file the owner downloaded.

Every call-derived item is labelled as an oral statement from a third-party
transcript, grade B, and becomes A only when a company document states the same
figure (D-M02-6). All guidance, release or call, is a forecast, not a commitment:
forward-looking statements under the safe harbor (Exchange Act §21E), no duty to
update (S98). Not legal advice.
"""

from __future__ import annotations

CALL_PREFIX = "AV-"
IR_PREFIX = "IR-"

CALL_LABEL = "call transcript (Alpha Vantage), oral statement, not in an SEC filing"
IR_LABEL = "company IR document (downloaded by the owner), not in an SEC filing"
FORECAST_NOTE = "forecast, not a commitment"


def origin_of(accession: str) -> str:
    """release | call | ir"""
    if accession.startswith(CALL_PREFIX):
        return "call"
    if accession.startswith(IR_PREFIX):
        return "ir"
    return "release"


def is_sec(accession: str) -> bool:
    return origin_of(accession) == "release"


def default_grade(origin: str) -> str:
    return "B" if origin == "call" else "A"


def source_label(accession: str, grade: str | None = None) -> str | None:
    """Label for a document or a ledger row; None for SEC documents."""
    origin = origin_of(accession)
    if origin == "call":
        g = grade or "B"
        tail = ", grade A (a company document states the same figure)" if g == "A" else ", grade B"
        return CALL_LABEL + tail
    if origin == "ir":
        return IR_LABEL + ", grade A"
    return None


def stated_prefix(kind: str | None, bound: str | None) -> str:
    """How the value was stated: 'approximately ', 'more than ', 'up to ' or ''."""
    if bound == "floor":
        return "more than "
    if bound == "ceiling":
        return "up to "
    return "approximately " if kind == "approx" else ""
