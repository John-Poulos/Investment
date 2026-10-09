"""Company IR documents the owner downloaded (lean fallback, D-M02-21 (1)).

When Alpha Vantage has no transcript 30 days after a release, an `m02_ir_download`
review item asks the owner to save the call transcript or prepared remarks (PDF)
from the company's IR site, honouring its terms (D-M02-6). "I downloaded it" finds
the newest PDF in the Downloads folder (setting `ENGINE_DOWNLOADS_DIR`), shows its
name, and on confirm stores it — the file itself is not moved.

Stored like a transcript: raw bytes once (doc_raw), text from pypdf, one section
'IR document', passages, a call_document row (source ir_download, grade A — the
company's own document). For a full transcript only the text before the Q&A
heading is parsed (prepared remarks; analysts never become guidance).
"""

from __future__ import annotations

import hashlib
import io
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from engine.calls.transcripts import ledger_label
from engine.guidance.calls import IR_SECTION, CallDoc, CallScan, scan_call
from engine.guidance.sources import IR_PREFIX
from engine.search.passages import fts_label, write_passages
from engine.sec.client import iso

EXTRACTOR_VERSION = "pypdf-1"
DOC_KINDS = {
    "transcript": "IR-TRANSCRIPT",
    "prepared_remarks": "IR-PREPARED-REMARKS",
    "cfo_commentary": "IR-CFO-COMMENTARY",
}
MAX_BYTES = 30 * 1024 * 1024


class InboxError(ValueError):
    """The file cannot be stored (not found, not a PDF, already stored, no text)."""


@dataclass(frozen=True)
class Found:
    path: Path
    name: str
    size: int
    modified: datetime


def newest_pdf(folder: Path) -> Found | None:
    try:
        pdfs = [p for p in folder.iterdir() if p.suffix.lower() == ".pdf" and p.is_file()]
    except OSError:
        return None
    if not pdfs:
        return None
    p = max(pdfs, key=lambda x: x.stat().st_mtime)
    st = p.stat()
    return Found(p, p.name, st.st_size, datetime.fromtimestamp(st.st_mtime))


def pdf_text(raw: bytes) -> str:
    """Text of every page, pages separated by a blank line; lines with collapsed spaces."""
    from pypdf import PdfReader

    pages = []
    for page in PdfReader(io.BytesIO(raw)).pages:
        lines = [" ".join(ln.split()) for ln in (page.extract_text() or "").splitlines()]
        pages.append("\n".join(ln for ln in lines if ln))
    return "\n\n".join(p for p in pages if p)


def _safe_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:120] or "document.pdf"


def ingest_pdf(
    engine: sqlite3.Connection,
    corpus: sqlite3.Connection,
    *,
    path: Path,
    cik: str,
    symbol: str,
    av_quarter: str,
    doc_kind: str,
    release_accession: str | None,
    release_filed: str | None,
    now: datetime,
    extract: Callable[[bytes], str] = pdf_text,
) -> tuple[str, CallScan]:
    """Store a downloaded PDF and scan it into the ledger → (accession, scan)."""
    if doc_kind not in DOC_KINDS:
        raise InboxError(f"unknown document kind {doc_kind!r}")
    try:
        raw = path.read_bytes()
    except OSError as e:
        raise InboxError(f"cannot read {path.name}: {e}") from e
    if not raw.startswith(b"%PDF"):
        raise InboxError(f"{path.name} is not a PDF")
    if len(raw) > MAX_BYTES:
        raise InboxError(f"{path.name} is larger than {MAX_BYTES // 2**20} MB")
    sha = hashlib.sha256(raw).hexdigest()
    url = f"file:sha256:{sha}"
    if corpus.execute("SELECT 1 FROM document WHERE url = ?", (url,)).fetchone():
        raise InboxError(f"{path.name} is already stored")
    try:
        text = extract(raw)
    except Exception as e:  # a broken or encrypted PDF is reported, never stored half
        raise InboxError(f"could not read text from {path.name}: {type(e).__name__}: {e}") from e
    if len(text.strip()) < 200:
        raise InboxError(f"{path.name} has almost no text (scanned images are not read)")
    symbol = symbol.upper()
    kind_tag = doc_kind.replace("_", "-")
    accession = f"{IR_PREFIX}{symbol}-{av_quarter}-{kind_tag}"
    filename = _safe_name(path.name)
    doc_type = DOC_KINDS[doc_kind]
    quarter = ledger_label(av_quarter)
    corpus.execute("BEGIN")
    try:
        doc_id = corpus.execute(
            "INSERT INTO document (accession, cik, filename, doc_type, url, content_type, text, "
            "sha256, fetched_at, parser_version, encoding, raw_size, description) "
            "VALUES (?, ?, ?, ?, ?, 'application/pdf', ?, ?, ?, ?, NULL, ?, ?)",
            (accession, cik, filename, doc_type, url, text, sha, iso(now), EXTRACTOR_VERSION,
             len(raw), f"{doc_kind.replace('_', ' ')}, fiscal {quarter} (owner download)"),
        ).lastrowid  # fmt: skip
        assert doc_id is not None
        sid = corpus.execute(
            "INSERT INTO section (doc_id, label, start_offset, end_offset, title, "
            "splitter_version) VALUES (?, ?, 0, ?, ?, ?)",
            (doc_id, IR_SECTION, len(text), path.name, EXTRACTOR_VERSION),
        ).lastrowid
        corpus.execute(
            "INSERT INTO section_fts (rowid, label, body) VALUES (?, ?, ?)",
            (sid, fts_label(IR_SECTION, path.name, doc_type, filename), text),
        )
        write_passages(corpus, doc_id)
        corpus.execute(
            "INSERT INTO doc_raw (doc_id, source, symbol, quarter, original_name, body, sha256, "
            "fetched_at) VALUES (?, 'ir_download', ?, ?, ?, ?, ?, ?)",
            (doc_id, symbol, av_quarter, path.name, raw, sha, iso(now)),
        )
        corpus.execute("COMMIT")
    except sqlite3.IntegrityError as e:
        corpus.execute("ROLLBACK")
        raise InboxError(f"a {doc_kind.replace('_', ' ')} for {symbol} {quarter} is "
                         "already stored") from e  # fmt: skip
    except Exception:
        corpus.execute("ROLLBACK")
        raise
    engine.execute(
        "INSERT INTO call_document (accession, filename, cik, symbol, quarter, source, doc_kind, "
        "release_accession, stated_on, added_at) VALUES (?, ?, ?, ?, ?, 'ir_download', ?, ?, ?, ?)",
        (accession, filename, cik, symbol, quarter, doc_kind, release_accession, release_filed,
         iso(now)),
    )  # fmt: skip
    cd = CallDoc(accession, filename, cik, symbol, quarter, "ir_download", doc_kind,
                 release_accession, release_filed)  # fmt: skip
    return accession, scan_call(engine, corpus, cd, now)
