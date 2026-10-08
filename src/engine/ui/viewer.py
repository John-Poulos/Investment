"""Who is viewing (M00_UI rules U1, U2).

Every request resolves its viewer here and nowhere else. While the app is bound
to this PC, the viewer is always the owner. Sharing later replaces this function
with a login; pages and services do not change. Write actions depend on
`require_owner`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request


@dataclass(frozen=True)
class Viewer:
    id: str
    role: str  # owner | viewer

    @property
    def is_owner(self) -> bool:
        return self.role == "owner"


OWNER = Viewer("owner", "owner")


def current_viewer(request: Request) -> Viewer:
    return OWNER


def require_owner(viewer: Annotated[Viewer, Depends(current_viewer)]) -> Viewer:
    """Owner-only actions resolve the viewer through `current_viewer`, so a future
    login (or a test override) applies here too."""
    if not viewer.is_owner:
        raise HTTPException(status_code=403, detail="Only the owner can do this.")
    return viewer
