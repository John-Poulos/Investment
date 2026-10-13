"""Credit-rating sentences in stored 8-Ks and earnings releases (M04 Part 3; S3.7, DS17).

Text only (agency data is not free). A sentence needs a credit context (a rating-scale
token — AAA…CC with +/−, Aaa…Ca with 1/2/3, a quoted single-letter grade — "investment
grade" / "speculative grade", an agency, or a credit-rating or outlook phrase; live check 1:
"upgraded quantum hardware" is not a rating). It counts when it states a rating action in
the past or present tense: downgraded / lowered / cut, upgraded / raised, outlook revised
to negative or positive, placed on watch or review for downgrade, affirmed. No agency name
is needed; ratings in the sentence (BBB+, Baa1 …) give from → to. The old engine's
severity words are kept ("credit rating", "downgrade", "negative outlook"); its bare
"covenant" and "waiver of" are dropped (S3.7). Hypothetical sentences ("a downgrade could
increase our borrowing costs") are skipped. Downgrades, negative outlooks and negative
watches open an `m04_rating` review (group 3); the first scan of a company is a baseline
(D-M04-71). Information row; rating actions carry no weight (Signals out: "never").
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime

from engine.financials import queue
from engine.financials.text import clean, sentences
from engine.sec.client import iso
from engine.sec.identity import normalize_cik

QUERY = (
    '"credit rating" OR "credit ratings" OR downgrade OR downgraded OR downgrades OR '
    '"rating outlook" OR "negative outlook" OR "positive outlook" OR creditwatch OR '
    '"credit watch" OR upgraded OR "corporate rating" OR "issuer rating"'
)
DOC_TYPES = ("8-K", "8-K/A", "EX-99.1", "EX-99.2", "EX-99")
RATING = re.compile(
    r"(?<![A-Za-z])(AAA|AA[+-]?|A[+-]|BBB[+-]?|BB[+-]?|B[+-]|CCC[+-]?|CC|Aaa|"
    r"Aa[123]|A[123]|Baa[123]|Ba[123]|B[123]|Caa[123]|Ca)(?![A-Za-z0-9])"
)
# Single-letter grades count only in quotes ('C', “D”).
QUOTED_GRADE = re.compile(r"[\"“‘'](?:A|B|C|D|SD|RD)[\"”’']")
# A credit context is required in the sentence (live check 1: "Delivered upgraded quantum
# hardware … technology operating aboard the ISS" matched "rating" inside "operating").
CONTEXT = re.compile(
    r"\b(?:investment|speculative)[- ]grade\b|\b(?:credit|issuer|corporate|debt|"
    r"long-term|short-term|senior unsecured|notes?) ratings?\b|\boutlooks?\b|"
    r"creditwatch|credit watch|Moody[’']?s|\bS&P\b|Standard & Poor|\bFitch\b",
    re.I,
)


def credit_context(s: str) -> bool:
    """A rating-scale token, a quoted grade, an agency, or a credit-rating or outlook
    phrase in the sentence."""
    return bool(CONTEXT.search(s) or RATING.search(s) or QUOTED_GRADE.search(s))


ACTIONS = (
    (
        "watch_negative",
        re.compile(
            r"(?:placed|put)[^.]{0,80}(?:on|under) (?:credit ?watch|"
            r"watch|review)[^.]{0,40}(?:negative|downgrade|possible "
            r"downgrade)",
            re.I,
        ),
    ),
    (
        "negative_outlook",
        re.compile(
            r"(?:revised|changed|lowered)[^.]{0,60}outlook[^.]{0,40}"
            r"(?:to|at) (?:\"|“)?negative|negative outlook",
            re.I,
        ),
    ),
    (
        "downgrade",
        re.compile(
            r"\bdowngraded\b|\b(?:lowered|cut|reduced)\b[^.]{0,80}"
            r"\bratings?\b|\bratings?\b[^.]{0,80}\b(?:lowered|cut)\b",
            re.I,
        ),
    ),
    (
        "positive_outlook",
        re.compile(
            r"(?:revised|changed|raised)[^.]{0,60}outlook[^.]{0,40}"
            r"(?:to|at) (?:\"|“)?positive|positive outlook",
            re.I,
        ),
    ),
    ("upgrade", re.compile(r"\bupgraded\b|\braised\b[^.]{0,80}\bratings?\b", re.I)),
    (
        "affirmed",
        re.compile(
            r"\baffirmed\b[^.]{0,80}\bratings?\b|\bratings?\b[^.]{0,80}"
            r"\baffirmed\b",
            re.I,
        ),
    ),
)
HYPOTHETICAL = re.compile(r"\b(?:if|may|could|would|might|should|any|potential|future)\b", re.I)
AGENCY = re.compile(r"Moody's|Moody’s|S&P(?: Global)?|Standard & Poor's|Fitch", re.I)
REVIEW_ACTIONS = ("downgrade", "negative_outlook", "watch_negative")
BASELINE_STATE = "m04_ratings_baseline:{cik}"


@dataclass(frozen=True)
class RatingSentence:
    cik: str
    accession: str
    filed: str | None
    doc_id: int
    passage_id: int | None
    start: int
    end: int
    action: str
    from_rating: str | None
    to_rating: str | None
    agency: str | None
    quote: str

    @property
    def review(self) -> bool:
        return self.action in REVIEW_ACTIONS

    @property
    def key(self) -> str:
        return f"{self.accession}:{self.doc_id}:{self.start}"


def classify_sentence(s: str) -> tuple[str, str | None, str | None, str | None] | None:
    """(action, from, to, agency) or None when the sentence states no rating action."""
    if not credit_context(s) or HYPOTHETICAL.search(s):
        return None
    action = next((name for name, rx in ACTIONS if rx.search(s)), None)
    ratings = [m.group(1) for m in RATING.finditer(s)]
    if action is None:
        if ratings and re.search(r"credit rating|rated", s, re.I):
            action = "mention"
        else:
            return None
    frm = to = None
    for m in RATING.finditer(s):
        before = s[max(0, m.start() - 12) : m.start()].lower()
        if re.search(r"\bfrom\W*$", before) and frm is None:
            frm = m.group(1)
        elif re.search(r"\bto\W*$", before) and to is None:
            to = m.group(1)
    if len(ratings) >= 2 and frm is None and to is None:
        frm, to = ratings[0], ratings[1]
    elif len(ratings) >= 1 and to is None and frm is None:
        to = ratings[0]
    elif to is None and frm is not None:
        to = next((r for r in ratings if r != frm), None)
    elif frm is None and to is not None and len(ratings) >= 2:
        frm = next((r for r in ratings if r != to), None)
    ag = AGENCY.search(s)
    return action, frm, to, ag.group(0) if ag else None


def scan(
    engine: sqlite3.Connection, corpus: sqlite3.Connection | None, cik: str
) -> list[RatingSentence]:
    """Rating sentences in the company's stored 8-Ks and releases."""
    if corpus is None:
        return []
    from engine.search.query import search

    norm = normalize_cik(cik) or cik
    out: dict[tuple[int, int], RatingSentence] = {}
    hits = search(corpus, QUERY, ciks=[norm], limit=500)
    for h in hits:
        if not ((h.doc_type or "").startswith(DOC_TYPES)):
            continue
        text = corpus.execute("SELECT text FROM document WHERE doc_id = ?", (h.doc_id,)).fetchone()[
            0
        ]
        f = engine.execute(
            "SELECT filed FROM filing WHERE accession = ?", (h.accession,)
        ).fetchone()
        for a, b in sentences(text, h.start, h.end):
            s = text[a:b]
            got = classify_sentence(s)
            if got is None:
                continue
            action, frm, to, agency = got
            out[(h.doc_id, a)] = RatingSentence(
                norm,
                h.accession,
                f["filed"] if f else None,
                h.doc_id,
                h.passage_id,
                a,
                b,
                action,
                frm,
                to,
                agency,
                clean(s),
            )
    return sorted(out.values(), key=lambda r: (r.filed or "", r.start), reverse=True)


def store(
    engine: sqlite3.Connection,
    cik: str,
    ticker: str | None,
    found: list[RatingSentence],
    now: datetime,
    *,
    queue_items: bool = True,
) -> dict[str, int]:
    """Insert new sentences, queue reviews (first scan = baseline). Caller owns the
    transaction."""
    at = iso(now)
    norm = normalize_cik(cik) or cik
    first = (
        engine.execute(
            "SELECT 1 FROM refresh_state WHERE name = ?", (BASELINE_STATE.format(cik=norm),)
        ).fetchone()
        is None
    )
    counts = {
        "sentences": len(found),
        "new": 0,
        "queued": 0,
        "overflow": 0,
        "baseline": 0,
        "suppressed": 0,
    }
    # a sentence the current rules no longer read as a rating action is dropped (an
    # answered item keeps its row)
    keep = {(r.doc_id, r.start) for r in found}
    counts["dropped"] = 0
    for old in engine.execute(
        "SELECT accession, doc_id, start_offset, item_id FROM rating_action WHERE cik = ?", (norm,)
    ).fetchall():
        if (old["doc_id"], old["start_offset"]) in keep:
            continue
        key = f"{old['accession']}:{old['doc_id']}:{old['start_offset']}"
        withdrawn = queue.withdraw(
            engine, "m04_rating", key, now, "recomputed: not a credit-rating sentence"
        )
        answered = old["item_id"] is not None and not withdrawn
        if not answered:
            engine.execute(
                "DELETE FROM rating_action WHERE doc_id = ? AND start_offset = ?",
                (old["doc_id"], old["start_offset"]),
            )
            counts["dropped"] += 1
    for r in found:
        counts["new"] += (
            engine.execute(
                "SELECT 1 FROM rating_action WHERE doc_id = ? AND start_offset = ?",
                (r.doc_id, r.start),
            ).fetchone()
            is None
        )
        engine.execute(
            "INSERT INTO rating_action (cik, accession, filed, doc_id, passage_id, start_offset, "
            "end_offset, action, from_rating, to_rating, agency, quote, review, first_seen_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT (doc_id, start_offset) "
            "DO UPDATE SET end_offset = excluded.end_offset, action = excluded.action, "
            "from_rating = excluded.from_rating, to_rating = excluded.to_rating, "
            "agency = excluded.agency, quote = excluded.quote, review = excluded.review",
            (
                norm,
                r.accession,
                r.filed,
                r.doc_id,
                r.passage_id,
                r.start,
                r.end,
                r.action,
                r.from_rating,
                r.to_rating,
                r.agency,
                r.quote,
                int(r.review),
                at,
            ),
        )
        if not r.review:
            queue.withdraw(
                engine, "m04_rating", r.key, now, f"recomputed: {r.action}, no review needed"
            )
        if not (r.review and queue_items):
            continue
        what = r.action.replace("_", " ") + (
            f" {r.from_rating or '?'} → {r.to_rating}" if r.to_rating else ""
        )
        status = queue.propose(
            engine,
            "m04_rating",
            r.key,
            f"{ticker or norm}: credit rating {what} ({r.filed or 'date unknown'})",
            {
                "ticker": ticker,
                "accession": r.accession,
                "filed": r.filed,
                "action": r.action,
                "from": r.from_rating,
                "to": r.to_rating,
                "agency": r.agency,
                "quote": r.quote,
                "offsets": [r.start, r.end],
            },
            now,
            cik=norm,
            baseline=first,
            filed=r.filed,
        )
        counts[status] = counts.get(status, 0) + 1
        item = engine.execute(
            "SELECT item_id FROM m04_proposal WHERE prop_key = ?", (f"m04_rating:{r.key}",)
        ).fetchone()
        if item and item["item_id"]:
            engine.execute(
                "UPDATE rating_action SET item_id = ? WHERE doc_id = ? AND start_offset = ?",
                (item["item_id"], r.doc_id, r.start),
            )
    if first:
        engine.execute(
            "INSERT INTO refresh_state (name, source_ref, fetched_at, detail) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (name) DO NOTHING",
            (
                BASELINE_STATE.format(cik=norm),
                "ratings.scan",
                at,
                json.dumps({"sentences": len(found)}),
            ),
        )
    return counts


def stored(engine: sqlite3.Connection, cik: str) -> list[sqlite3.Row]:
    return engine.execute(
        "SELECT * FROM rating_action WHERE cik = ? ORDER BY filed DESC, start_offset",
        (normalize_cik(cik) or cik,),
    ).fetchall()
