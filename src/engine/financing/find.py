"""Sentences naming a financing or equity link (D-M02-41 kinds K1–K4, K6).

A = the filer of the document, B = a known company the sentence names (aliases).
Direction: a_to_b = A's money or equity goes to B; b_to_a = B's goes to A; None = not
stated. Examples (review guide):
- K1 equity purchase: "issue and sell 215 million shares of our common stock to NVIDIA"
  (Intel 10-K) → NVIDIA → Intel; "we invested $2.0 billion in Marvell preferred stock" →
  A → Marvell.
- K2 equity granted to a customer: "issued a warrant to Amazon to purchase up to …" →
  A grants equity to Amazon.
- K3 revenue backstop: "NVIDIA agreed to purchase any unsold capacity" (CoreWeave 10-K) →
  NVIDIA backstops CoreWeave.
- K4 customer financing, loans, guarantees: "we provided financing to …", "guarantee of
  … obligations".
- K6 joint venture / equity-method investee: "our equity method investment in SpaceX".
Sentences about competition are skipped; a name followed by a product word ("NVIDIA
NVLink") is a product, not the company (part 5 rules).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

from engine.supply.aliases import Company, Matcher
from engine.supply.find import _COMPETE, _product, _sentences_in

_SECURITY = (
    r"(?:shares|common stock|ordinary shares|preferred stock|preferred shares|warrants?|"
    r"convertible (?:senior )?(?:notes?|preferred)|American Depositary|equity interest|"
    r"equity stake|equity investment|ownership interest)"
)
K1 = re.compile(
    rf"\b(?:invest\w*|purchas\w*|acqui\w*|bought|subscri\w*|issu\w+|s[eo]l[dl]\w*|sale)\b"
    rf"(?:[^.;]|\.(?=\d)){{0,160}}\b{_SECURITY}\b|\b{_SECURITY}\b(?:[^.;]|\.(?=\d)){{0,120}}\b(?:to|by|from)\b",
    re.IGNORECASE,
)
# Live check 1 (D-M02-47): every warrant naming a commercial counterparty in the run was a
# warrant granted to that company (Amazon, Microsoft, Oracle) — one kind per pair, not K1/K2.
K2 = re.compile(r"\bwarrants?\b", re.IGNORECASE)
K3 = re.compile(
    r"\b(?:unsold|unused|excess|residual) (?:\w+ ){0,2}capacity\b|\bbackstop\w*\b|"
    r"\bcapacity (?:purchase|commitment)s?\b|\bminimum (?:revenue|purchase|utilization) "
    r"(?:commitment|guarantee)s?\b",
    re.IGNORECASE,
)
K4 = re.compile(
    r"\b(?:customer|vendor) financing\b|\bfinancing (?:to|for|provided to|arrangements? "
    r"with)\b|\bfinancing receivables?\b|\bloans? (?:to|receivable from)\b|"
    r"\bguarantee\w* (?:of|for)\b(?:[^.;]|\.(?=\d)){0,80}\b(?:debt|obligations|leases?|borrowings|"
    r"payments)\b|\bguarantor\b",
    re.IGNORECASE,
)
K6 = re.compile(
    r"\bjoint ventures?\b|\bequity[- ]method (?:investees?|investments?)\b", re.IGNORECASE
)
KINDS: tuple[tuple[str, re.Pattern], ...] = (
    ("K2", K2),
    ("K3", K3),
    ("K4", K4),
    ("K1", K1),
    ("K6", K6),
)
KIND_LABELS = {
    "K1": "equity purchase",
    "K2": "equity granted to a customer",
    "K3": "revenue backstop",
    "K4": "customer financing / guarantee",
    "K6": "joint venture / equity-method",
}

_MONEY = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)\s*(billion|million|thousand|[BMK]\b)?", re.I)
_SCALE = {"billion": 1e9, "b": 1e9, "million": 1e6, "m": 1e6, "thousand": 1e3, "k": 1e3}
_INSTRUMENT = (
    ("preferred stock", r"preferred (?:stock|shares)"),
    ("warrants", r"warrants?"),
    ("convertible notes", r"convertible (?:senior )?notes?"),
    ("common stock", r"common stock|ordinary shares|shares of (?:our |its )?(?:Class \w )?common"),
    ("ADSs", r"American Depositary"),
    ("capacity", r"capacity"),
    ("loan", r"\bloans?\b"),
    ("guarantee", r"guarant\w+"),
    ("joint venture", r"joint venture"),
    ("equity-method stake", r"equity[- ]method"),
)


@dataclass(frozen=True)
class FinFound:
    kind: str
    b: Company
    b_name: str
    direction: str | None
    amount: Decimal | None
    instrument: str | None
    start: int
    end: int
    how: str


_PER_UNIT = re.compile(r"\s*(?:per|a|each)\s+(?:\w+\s+)?(?:share|unit|warrant)", re.I)
_PAR = re.compile(
    r"(?:par value|exercise price|price per (?:share|unit|warrant))(?:\s+of)?\s*$", re.I
)
_WARRANT_SHARES = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*(million\s+)?(?:\w+\s+){0,3}shares", re.I)


def amount_of(sent: str) -> Decimal | None:
    """The largest dollar figure that is not a per-share price, par value or exercise price
    (live check 1: "$0.002 per share" par value was read as Marvell's $2.0B)."""
    best = None
    for m in _MONEY.finditer(sent):
        if _PER_UNIT.match(sent, m.end()) or _PAR.search(sent[max(0, m.start() - 30) : m.start()]):
            continue
        value = Decimal(m.group(1).replace(",", ""))
        value *= Decimal(str(_SCALE.get((m.group(2) or "").lower(), 1)))
        best = value if best is None else max(best, value)
    return best


def warrant_shares(sent: str) -> str | None:
    """'warrants (2,696,678 shares)' from "… to acquire up to 2,696,678 shares …"."""
    m = _WARRANT_SHARES.search(sent)
    if not m:
        return None
    n = float(m.group(1).replace(",", "")) * (1e6 if m.group(2) else 1)
    return f"warrants ({n:,.0f} shares)"


def instrument_of(sent: str) -> str | None:
    for label, rx in _INSTRUMENT:
        if re.search(rx, sent, re.IGNORECASE):
            return label
    return None


def _esc(name: str) -> str:
    return re.escape(name)


def direction_of(kind: str, sent: str, b_name: str) -> str | None:
    """Who finances whom, from wording around B's name; None when it does not say."""
    n = _esc(b_name)
    i = r"(?:[^.;]|\.(?=\d)){0,120}"
    # B acts: "NVIDIA agreed to invest / purchase / acquire …", "investment from NVIDIA"
    b_acts = re.search(
        rf"\b{n}\b(?:'s)?(?:[^.;]|\.(?=\d)){{0,40}}?\b(?:agreed to |will |has agreed to |would )?"
        r"(?:invest|purchas|acquir|bought|subscrib|provid\w* financing|lend|loan|guarant|"
        r"backstop)\w*",
        sent,
        re.IGNORECASE,
    ) or re.search(
        rf"\b(?:investment|financing|loan|funding|capital) (?:from|by|provided by)\b{i}\b{n}\b",
        sent,
        re.IGNORECASE,
    )
    # A acts towards B: "sell … to NVIDIA", "warrant to Amazon", "investment in Marvell"
    to_b = re.search(rf"\b(?:to|for|with)\s+{n}\b", sent, re.IGNORECASE)
    sale_to_b = to_b and re.search(r"\b(?:issu|s[eo]l[dl]|sale|grant|transfer)\w*", sent, re.I)
    in_b = (
        re.search(
            rf"\b(?:investments? in|invested in|stake in|interest in|shares of|stock of|"
            rf"preferred stock of|loans? to|financing to|guarantee\w* (?:of|for))\b{i}\b{n}\b",
            sent,
            re.IGNORECASE,
        )
        or re.search(rf"\b(?:invest|purchas|acquir|bought)\w*[^;]{{0,60}}\bin\s+{n}\b", sent, re.I)
        or re.search(
            rf"\b{n}\b(?:'s)? (?:\w+ )?(?:shares|common stock|preferred stock|stock)\b", sent, re.I
        )
    )  # "SpaceX shares", "SpaceX common stock": A holds B (live check 1)
    if kind == "K1":
        if sale_to_b or b_acts:
            return "b_to_a"  # B buys A's shares: B's money goes to A
        if in_b:
            return "a_to_b"
    elif kind == "K2":
        # B's own warrants: "warrants to purchase shares of Rivian", "warrants in Rivian"
        if re.search(rf"\bwarrants? (?:to purchase (?:shares of |common stock of )?|in |of ){n}\b",
                     sent, re.I):  # fmt: skip
            return "b_to_a"
        # otherwise the filer granted it to B ("issued … to Amazon", "exercised by Amazon",
        # "warrants held by Amazon", "the AWS Warrant") — live check 1 (D-M02-47)
        return "a_to_b"
    elif kind == "K3":
        if b_acts:
            return "b_to_a"  # B backstops A's revenue
        if re.search(rf"\b(?:from|of)\s+{n}\b", sent, re.I):
            return "a_to_b"  # A buys B's capacity
    elif kind == "K4":
        if b_acts:
            return "b_to_a"
        if in_b or (to_b and re.search(r"\b(?:financ|loan|lend|guarant)\w*", sent, re.I)):
            return "a_to_b"
    elif kind == "K6":
        if in_b:
            return "a_to_b"
    return None


def find(text: str, matcher: Matcher, self_keys: set[str]) -> list[FinFound]:
    out = []
    for s, e in _sentences_in(text):
        sent = text[s:e]
        if _COMPETE.search(sent):
            continue
        kind = next(((k, m) for k, rx in KINDS if (m := rx.search(sent))), None)
        if kind is None:
            continue
        seen = set()
        for m in matcher.find(text, s, e):
            c = m.company
            if c.key in self_keys or c.key in seen or _product(text, m):
                continue
            seen.add(c.key)
            k, w = kind
            out.append(
                FinFound(
                    k,
                    c,
                    m.name,
                    direction_of(k, sent, m.name),
                    # a warrant's dollar figures are prices or payment thresholds ("up to
                    # $60 billion in payments"), not money paid: shares only (live check 1)
                    None if k == "K2" else amount_of(sent),
                    (warrant_shares(sent) or "warrants") if k == "K2" else instrument_of(sent),
                    s,
                    e,
                    f"{KIND_LABELS[k]}: {w.group(0).lower()[:60]}",
                )
            )
    return out
