"""Typed results shared by every SEC call (M00_SEC_DATA rule 3).

A result is data (`Ok`), a checked negative (`Empty`, naming what was checked),
a missing file (`NotFound`: no file at that URL, HTTP 404), or a failure
(`Failed`). Only a source parser that has tried every known path may turn
`NotFound` into `Empty`; the client never does. A failure never becomes empty
data, and empty data is never coerced to zero (rule 6).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Probe:
    """One lookup that was attempted, so a negative states what was checked."""

    path: str
    query: str
    result: str


@dataclass(frozen=True)
class Ok[T]:
    data: T
    source_ref: str = ""
    fetched_at: str = ""
    from_cache: bool = False
    stale: bool = False  # served from storage after a failed refresh (read path step 4)


@dataclass(frozen=True)
class Empty:
    paths_checked: tuple[Probe, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class NotFound:
    """No file at this URL (HTTP 404): a broken or wrong link, not proof of no data."""

    url: str
    status: int = 404
    from_cache: bool = False


@dataclass(frozen=True)
class Failed:
    reason: str
    url: str = ""
    status: int | None = None
    throttled: bool = False


type Result[T] = Ok[T] | Empty | NotFound | Failed


def is_ok(result: Result[Any]) -> bool:
    return isinstance(result, Ok)
