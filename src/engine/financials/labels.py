"""The owner's M04 label file (D-M04-51, D-M04-73): read-only for the app.

`config/m04_labels.toml` is created by Part 3 as a template; the owner fills it during
Parts 3–7; Part 8b scores against it. The app never writes it. This reader only counts and
validates (unknown labels are reported, never fixed).
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

LABELS = Path("config/m04_labels.toml")  # relative to the repo, as models.MODELS
CVD_LABELS = (
    "CYCLICAL_TROUGH",
    "CYCLE_PLUS_DAMAGE",
    "STUMBLE",
    "STRUCTURAL_DECLINE",
    "NO_SLOWDOWN",
    "AMBIGUOUS",
)
FLAG_LABELS = ("flag", "clean", "unsure")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@dataclass(frozen=True)
class LabelFile:
    path: str
    episodes: int
    episodes_labelled: int
    controls: int
    red_flags: int
    red_flags_labelled: int
    problems: tuple[str, ...]
    error: str = ""

    def line(self) -> str:
        if self.error:
            return f"Label file {self.path}: {self.error}"
        out = (
            f"Label file {self.path}: {self.episodes} CvD episodes ({self.controls} "
            f"controls), {self.episodes_labelled} labelled; {self.red_flags} red-flag rows, "
            f"{self.red_flags_labelled} labelled (the app never edits it)"
        )
        if self.problems:
            out += "; check: " + "; ".join(self.problems[:5])
        return out


def read(path: Path = LABELS) -> LabelFile:
    if not path.exists():
        return LabelFile(str(path), 0, 0, 0, 0, 0, (), "missing")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        return LabelFile(str(path), 0, 0, 0, 0, 0, (), f"not valid TOML: {e}")
    eps = data.get("episode", [])
    flags = data.get("red_flag", [])
    problems = []
    for kind, rows, allowed in (("episode", eps, CVD_LABELS), ("red_flag", flags, FLAG_LABELS)):
        for r in rows:
            lab = str(r.get("label") or "").strip()
            if lab and lab not in allowed:
                problems.append(f"{kind} {r.get('key')}: unknown label {lab!r}")
            d = str(r.get("label_date") or "").strip()
            if lab and not DATE.match(d):
                problems.append(f"{kind} {r.get('key')}: label_date missing or not YYYY-MM-DD")
            if not re.fullmatch(r"\d{10}", str(r.get("cik") or "")):
                problems.append(f"{kind} {r.get('key')}: cik must be 10 digits")
    return LabelFile(
        str(path),
        len(eps),
        sum(1 for r in eps if str(r.get("label") or "").strip()),
        sum(1 for r in eps if r.get("set") == "control"),
        len(flags),
        sum(1 for r in flags if str(r.get("label") or "").strip()),
        tuple(problems),
    )
