"""Filing documents: index, full text, storage (M00_SEC_DATA documents.py).

The per-filing index is `{accession}-index.htm` (checked live 2026-10-07:
`{accession}-index.json` does not exist; `index.json` is a folder listing
without document types). Its "Document Format Files" table lists each
document's sequence, description, file and type. Inline-XBRL documents link
through the viewer (`/ix?doc=...`); the prefix is removed to get the file.

Documents are stored whole (rule 7, D22): raw bytes stay in the HTTP cache
(long TTL; filings are immutable) and the extracted text goes to corpus.db
with the parser version, split into sections indexed in FTS5 (sections.py).
"""

from __future__ import annotations

import hashlib
import re
import sqlite3
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urljoin

from engine.sec.client import SecClient, iso
from engine.sec.identity import normalize_cik
from engine.sec.results import Empty, Failed, NotFound, Ok, Probe, Result
from engine.sec.sections import write_sections
from engine.sec.submissions import Filing

ARCHIVES = "https://www.sec.gov/Archives/edgar/data"
SEC_ROOT = "https://www.sec.gov"
INDEX_TTL_S = 3650 * 86400  # filings are immutable; amendments are new accessions
DOC_TTL_S = 3650 * 86400  # keeps raw bytes for re-parsing
PARSER_VERSION = "html-text-1"
# Exhibits fetched by default, by form. EX-99.1 = 8-K press release (R19).
DEFAULT_EXTRA_TYPES: dict[str, tuple[str, ...]] = {"8-K": ("EX-99.1",), "8-K/A": ("EX-99.1",)}


@dataclass(frozen=True)
class IndexDoc:
    seq: int | None
    description: str | None
    filename: str
    url: str
    doc_type: str | None
    size: int | None
    inline_xbrl: bool


@dataclass(frozen=True)
class StoredDoc:
    doc_id: int
    accession: str
    filename: str
    doc_type: str | None
    chars: int
    new: bool


@dataclass(frozen=True)
class FilingDocs:
    accession: str
    stored: tuple[StoredDoc, ...]
    failed: tuple[str, ...] = field(default_factory=tuple)  # "filename: reason"
    not_listed: tuple[str, ...] = field(default_factory=tuple)  # wanted types absent

    @property
    def complete(self) -> bool:
        return not self.failed


def filing_folder(cik: str, accession: str) -> str:
    return f"{ARCHIVES}/{int(cik)}/{accession.replace('-', '')}"


def strip_viewer(href: str) -> str:
    """'/ix?doc=/Archives/...' → '/Archives/...' (inline-XBRL viewer link)."""
    m = re.match(r"^/ix\?doc=(.+)$", href)
    return m.group(1) if m else href


# --- Index page --------------------------------------------------------------


class _IndexTableParser(HTMLParser):
    """Collects rows of the 'Document Format Files' table."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_table = False
        self.depth = 0
        self.rows: list[list[tuple[str, str | None]]] = []  # cells: (text, href)
        self._row: list[tuple[str, str | None]] | None = None
        self._cell: list[str] | None = None
        self._href: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = dict(attrs)
        if tag == "table":
            if self.in_table:
                self.depth += 1
            elif (
                "tablefile" in (a.get("class") or "").lower()
                and "document format" in (a.get("summary") or "").lower()
            ):
                self.in_table, self.depth = True, 0
        if not self.in_table:
            return
        if tag == "tr":
            self._row = []
        elif tag in ("td", "th") and self._row is not None:
            self._cell, self._href = [], None
        elif tag == "a" and self._cell is not None and self._href is None:
            self._href = a.get("href")

    def handle_endtag(self, tag: str) -> None:
        if not self.in_table:
            return
        if tag == "table":
            if self.depth:
                self.depth -= 1
            else:
                self.in_table = False
        elif tag in ("td", "th") and self._cell is not None and self._row is not None:
            self._row.append((" ".join("".join(self._cell).split()), self._href))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self.rows.append(self._row)
            self._row = None

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)


def parse_filing_index(html: str, base_url: str = SEC_ROOT) -> list[IndexDoc]:
    """Rows of the Document Format Files table. Raises ValueError if the table is absent."""
    parser = _IndexTableParser()
    parser.feed(html)
    parser.close()
    if not parser.rows:
        raise ValueError("no 'Document Format Files' table in filing index")

    header = [text.lower() for text, _ in parser.rows[0]]
    try:
        ci = {name: header.index(name) for name in ("seq", "description", "document", "type")}
    except ValueError as exc:
        raise ValueError(f"filing index columns changed: {header}") from exc
    size_i = header.index("size") if "size" in header else None

    docs = []
    for row in parser.rows[1:]:
        if len(row) < len(header):
            continue
        doc_text, href = row[ci["document"]]
        if not href:
            continue
        path = strip_viewer(href)
        filename = path.rsplit("/", 1)[-1] or doc_text.split()[0]
        seq_text = row[ci["seq"]][0]
        size_text = row[size_i][0] if size_i is not None else ""
        docs.append(
            IndexDoc(
                seq=int(seq_text) if seq_text.isdigit() else None,
                description=row[ci["description"]][0] or None,
                filename=filename,
                url=urljoin(base_url, path),
                doc_type=row[ci["type"]][0] or None,
                size=int(size_text) if size_text.isdigit() else None,
                inline_xbrl=href != path or "ixbrl" in doc_text.lower(),
            )
        )
    return docs


def fetch_filing_index(client: SecClient, cik: str, accession: str) -> Result[list[IndexDoc]]:
    """The filing's document list. Tries -index.htm, then -index.html; both missing → Empty."""
    norm = normalize_cik(cik)
    if norm is None:
        return Empty((Probe("CIK", str(cik), "not a CIK"),))
    folder = filing_folder(norm, accession)
    probes = []
    for name in (f"{accession}-index.htm", f"{accession}-index.html"):
        url = f"{folder}/{name}"
        res = client.get_text(url, ttl_s=INDEX_TTL_S)
        if isinstance(res, NotFound):
            probes.append(Probe("filing index", url, "HTTP 404: no file at this URL"))
            continue
        if not isinstance(res, Ok):
            return res
        try:
            docs = parse_filing_index(res.data)
        except ValueError as exc:
            return Failed(f"filing index unreadable: {exc}", url=url)
        return Ok(docs, source_ref=url, fetched_at=res.fetched_at, from_cache=res.from_cache)
    return Empty(tuple(probes))


# --- Document text -----------------------------------------------------------

_BLOCK = {
    "p", "div", "br", "tr", "li", "ul", "ol", "table", "section", "article", "header",
    "footer", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "blockquote", "hr", "title",
}  # fmt: skip
_SKIP = {"script", "style", "head", "ix:header"}  # ix:header = hidden iXBRL facts


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP:
            self.skip += 1
        elif not self.skip:
            if tag in _BLOCK:
                self.out.append("\n")
            elif tag in ("td", "th"):
                self.out.append("\t")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if not self.skip and tag in ("br", "hr"):
            self.out.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP:
            self.skip = max(0, self.skip - 1)
        elif not self.skip and tag in _BLOCK:
            self.out.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.out.append(data)


def html_to_text(html: str) -> str:
    """Readable text: tags dropped, entities decoded, blocks on their own lines,
    table cells tab-separated, nothing truncated."""
    parser = _TextExtractor()
    parser.feed(html)
    parser.close()
    text = "".join(parser.out).replace("\xa0", " ").replace("\r", "")
    lines = []
    for line in text.split("\n"):
        cells = [" ".join(cell.split()) for cell in line.split("\t")]
        joined = "\t".join(c for c in cells if c)
        lines.append(joined)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"


def decode(raw: bytes) -> tuple[str, str]:
    for encoding in ("utf-8", "cp1252"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1"), "latin-1"


def extract_text(raw: bytes, filename: str) -> tuple[str, str]:
    """(text, encoding). HTML is converted; .txt and .xml are kept as-is."""
    text, encoding = decode(raw)
    if filename.lower().endswith((".htm", ".html")):
        return html_to_text(text), encoding
    return text, encoding


# --- Storage -----------------------------------------------------------------


def store_document(
    corpus: sqlite3.Connection,
    cik: str,
    accession: str,
    doc: IndexDoc,
    raw: bytes,
    now: datetime,
) -> StoredDoc:
    """Insert the document and its sections (FTS5) in one transaction."""
    text, encoding = extract_text(raw, doc.filename)
    corpus.execute("BEGIN")
    try:
        cur = corpus.execute(
            "INSERT INTO document (accession, cik, filename, doc_type, url, content_type, text, "
            "sha256, fetched_at, parser_version, encoding, raw_size, description) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                accession,
                cik,
                doc.filename,
                doc.doc_type,
                doc.url,
                None,
                text,
                hashlib.sha256(raw).hexdigest(),
                iso(now),
                PARSER_VERSION,
                encoding,
                len(raw),
                doc.description,
            ),
        )
        doc_id = cur.lastrowid
        assert doc_id is not None
        write_sections(corpus, doc_id, text, doc.doc_type, doc.filename, now)
        corpus.execute("COMMIT")
    except Exception:
        corpus.execute("ROLLBACK")
        raise
    return StoredDoc(doc_id, accession, doc.filename, doc.doc_type, len(text), True)


def _stored(corpus: sqlite3.Connection, url: str) -> StoredDoc | None:
    row = corpus.execute(
        "SELECT doc_id, accession, filename, doc_type, length(text) AS chars "
        "FROM document WHERE url = ?",
        (url,),
    ).fetchone()
    if row is None:
        return None
    return StoredDoc(
        row["doc_id"], row["accession"], row["filename"], row["doc_type"], row["chars"], False
    )


def ingest_filing(
    client: SecClient,
    corpus: sqlite3.Connection,
    filing: Filing,
    now: datetime,
    *,
    types: Iterable[str] | None = None,
) -> Result[FilingDocs]:
    """Store the documents of `filing` whose type is wanted.

    Default: the primary document (type = the filing's form), plus EX-99.1 for 8-Ks.
    Documents already stored are not fetched again.
    """
    wanted = (
        set(types)
        if types is not None
        else {filing.form, *DEFAULT_EXTRA_TYPES.get(filing.form, ())}
    )
    index = fetch_filing_index(client, filing.cik, filing.accession)
    if not isinstance(index, Ok):
        return index

    chosen = [d for d in index.data if d.doc_type in wanted]
    listed = {d.doc_type for d in index.data}
    not_listed = tuple(sorted(t for t in wanted if t not in listed))

    stored, failed = [], []
    for doc in chosen:
        existing = _stored(corpus, doc.url)
        if existing is not None:
            stored.append(existing)
            continue
        res = client.get_bytes(doc.url, ttl_s=DOC_TTL_S)
        if isinstance(res, NotFound):
            failed.append(f"{doc.filename}: no file at {doc.url} (HTTP 404)")
            continue
        if not isinstance(res, Ok):
            failed.append(f"{doc.filename}: {res.reason if isinstance(res, Failed) else res}")
            continue
        stored.append(store_document(corpus, filing.cik, filing.accession, doc, res.data, now))

    return Ok(
        FilingDocs(filing.accession, tuple(stored), tuple(failed), not_listed),
        source_ref=index.source_ref,
        fetched_at=iso(now),
    )


def document_text(corpus: sqlite3.Connection, doc_id: int) -> str | None:
    row = corpus.execute("SELECT text FROM document WHERE doc_id = ?", (doc_id,)).fetchone()
    return row["text"] if row else None
