"""Typed results shared by every SEC call (M00_SEC_DATA rule 3).

A result is data (`Ok`), a checked negative (`Empty`, naming what was checked),
or a failure (`Failed`). A failure never becomes empty data, and empty data is
never coerced to zero (rule 6).
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
class Failed:
    reason: str
    url: str = ""
    status: int | None = None
    throttled: bool = False


type Result[T] = Ok[T] | Empty | Failed


def is_ok(result: Result[Any]) -> bool:
    return isinstance(result, Ok)
