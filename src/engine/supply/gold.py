"""Precision set for link labels (D-M02-9, D-M02-35): owner labels blind, then Gemini.

Code picks ~30 passages, spread over the rungs (L1, L2, L3 in turn, newest first within a
rung), once. The owner labels each from the passage text only — no suggestion shown —
on the labelling page. Gemini (use case 5) labels the same passages; the comparison
gives precision for "supply", recall, and direction accuracy where both say supply and
the owner gave a direction. Link counts feed nothing until this has been measured.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from engine.sec.client import iso

SIZE = 30
ORDER = ("L2", "L2c", "L1", "L3")  # L2c = option (c) trial passages (D-M02-38)


def build(engine: sqlite3.Connection, size: int = SIZE) -> int:
    """Pick the set once (no-op when it exists) → passages in the set."""
    have = engine.execute("SELECT count(*) FROM link_gold").fetchone()[0]
    if have:
        return have

    def pool(name: str) -> list[int]:
        rung, trial = name[:2], name.endswith("c")
        return [
            r[0]
            for r in engine.execute(
                "SELECT min(link_id) FROM supply_link WHERE rung = ? AND "
                "(how LIKE '(c)%') = ? GROUP BY pair_key ORDER BY max(filed) DESC",
                (rung, trial),
            )
        ]

    pools = {name: pool(name) for name in ORDER}
    chosen: list[int] = []
    while len(chosen) < size and any(pools.values()):
        for rung in ORDER:
            if pools[rung] and len(chosen) < size:
                chosen.append(pools[rung].pop(0))
    engine.executemany(
        "INSERT INTO link_gold (link_id, position) VALUES (?, ?)",
        [(lid, i + 1) for i, lid in enumerate(chosen)],
    )
    return len(chosen)


@dataclass(frozen=True)
class Card:
    gold_id: int
    position: int
    total: int
    labelled: int
    a_name: str
    b_name: str
    quote: str
    source: str
    gold_type: str | None
    gold_direction: str | None


def card(engine: sqlite3.Connection, position: int | None = None) -> Card | None:
    """The card at `position`, else the first unlabelled one."""
    total = engine.execute("SELECT count(*) FROM link_gold").fetchone()[0]
    labelled = engine.execute(
        "SELECT count(*) FROM link_gold WHERE gold_type IS NOT NULL"
    ).fetchone()[0]
    where = "g.position = ?" if position else "g.gold_type IS NULL"
    r = engine.execute(
        "SELECT g.*, l.a_name, l.b_name, l.quote, l.form, l.filed FROM link_gold g "
        f"JOIN supply_link l ON l.link_id = g.link_id WHERE {where} ORDER BY g.position LIMIT 1",
        (position,) if position else (),
    ).fetchone()
    if r is None:
        return None
    source = f"{r['a_name']} {r['form'] or ''} {r['filed'] or ''}".strip()
    return Card(
        r["gold_id"],
        r["position"],
        total,
        labelled,
        r["a_name"],
        r["b_name"],
        r["quote"],
        source,
        r["gold_type"],
        r["gold_direction"],
    )


TYPES = ("supply", "partner", "competitor", "none", "unclear")
DIRECTIONS = ("a_to_b", "b_to_a", "unclear")


def label(
    engine: sqlite3.Connection,
    gold_id: int,
    gold_type: str,
    direction: str | None,
    by: str,
    now: datetime,
) -> None:
    if gold_type not in TYPES:
        raise ValueError("Choose a relationship.")
    if gold_type == "supply" and direction not in DIRECTIONS:
        raise ValueError("Choose who supplies whom (or 'unclear').")
    engine.execute(
        "UPDATE link_gold SET gold_type = ?, gold_direction = ?, labelled_by = ?, "
        "labelled_at = ? WHERE gold_id = ?",
        (gold_type, direction if gold_type == "supply" else None, by, iso(now), gold_id),
    )


def size(engine: sqlite3.Connection) -> int:
    return engine.execute("SELECT count(*) FROM link_gold").fetchone()[0]


def link_ids(engine: sqlite3.Connection) -> list[int]:
    return [r[0] for r in engine.execute("SELECT link_id FROM link_gold ORDER BY position")]


@dataclass(frozen=True)
class Accuracy:
    labelled: int
    compared: int  # labelled by the owner and by Gemini
    type_agree: int
    supply_said: int  # Gemini said supply
    supply_right: int  # ... and the owner said supply
    supply_gold: int  # owner said supply
    direction_n: int
    direction_right: int

    @property
    def precision(self) -> float | None:
        return self.supply_right / self.supply_said if self.supply_said else None

    @property
    def recall(self) -> float | None:
        return self.supply_right / self.supply_gold if self.supply_gold else None

    @property
    def direction_accuracy(self) -> float | None:
        return self.direction_right / self.direction_n if self.direction_n else None

    def line(self) -> str:
        def pct(x: float | None) -> str:
            return "n/a" if x is None else f"{x:.0%}"

        return (
            f"precision set: {self.labelled} labelled by the owner, {self.compared} also "
            f"by Gemini; type agreement {self.type_agree}/{self.compared}; supply "
            f"precision {pct(self.precision)} ({self.supply_right}/{self.supply_said}), "
            f"recall {pct(self.recall)} ({self.supply_right}/{self.supply_gold}); "
            f"direction {pct(self.direction_accuracy)} "
            f"({self.direction_right}/{self.direction_n})"
        )


def accuracy(engine: sqlite3.Connection) -> Accuracy:
    rows = engine.execute(
        "SELECT g.gold_type, g.gold_direction, l.llm_type, l.llm_direction FROM link_gold g "
        "JOIN supply_link l ON l.link_id = g.link_id WHERE g.gold_type IS NOT NULL"
    ).fetchall()
    comp = [r for r in rows if r["llm_type"] is not None]
    said = [r for r in comp if r["llm_type"] == "supply"]
    both = [r for r in said if r["gold_type"] == "supply"]
    dirs = [r for r in both if r["gold_direction"] in ("a_to_b", "b_to_a")]
    return Accuracy(
        labelled=len(rows),
        compared=len(comp),
        type_agree=sum(r["gold_type"] == r["llm_type"] for r in comp),
        supply_said=len(said),
        supply_right=len(both),
        supply_gold=sum(r["gold_type"] == "supply" for r in comp),
        direction_n=len(dirs),
        direction_right=sum(r["gold_direction"] == r["llm_direction"] for r in dirs),
    )


def trial_line(engine: sqlite3.Connection) -> str | None:
    """Option (c) trial (D-M02-38): how many of its passages the owner labelled supply."""
    rows = engine.execute(
        "SELECT g.gold_type FROM link_gold g JOIN supply_link l ON l.link_id = g.link_id "
        "WHERE l.how LIKE '(c)%' AND g.gold_type IS NOT NULL"
    ).fetchall()
    if not rows:
        return None
    supply = sum(r[0] == "supply" for r in rows)
    return (f"option (c) trial: {supply} of {len(rows)} labelled bare-name passages state a "
            "supplier/customer link")  # fmt: skip
