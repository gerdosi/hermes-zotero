"""Choose the best text for each item and split it into search passages."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from .frontmatter import is_true, split_front_matter
from .tables import MARKER, Table, prepare
from .textquality import damage
from .zdb import normalize_doi

MIN_BYTES = 200
STORED_LINK_MODES = (0, 1)

_URL_PREFIXES = ("https_doi.org_", "http_doi.org_", "https_dx.doi.org_", "http_dx.doi.org_")
_HEADING = re.compile(r"^#{1,6}\s+(.*)$", re.MULTILINE)


@dataclass(frozen=True)
class TextResult:
    source: str          # "markdown" | "ft-cache" | "metadata"
    text: str
    path: str | None
    flags: tuple[str, ...]
    signature: str


@dataclass(frozen=True)
class Passage:
    section: str
    start: int
    end: int
    text: str
    kind: str = "text"            # "text" | "table"
    table: int | None = None      # the N of '### Table N' for a table passage


def doi_slug(doi: str) -> str:
    """File-name slug of a DOI, as used by the Markdown corpus."""
    value = normalize_doi(doi)
    return re.sub(r"[^a-z0-9.-]+", "_", value).strip("_")


class MarkdownCorpus:
    """Index of the converted-Markdown folder (one scan, file names only)."""

    def __init__(self, root) -> None:
        self._keys: dict[str, Path] = {}
        self._slugs: dict[str, Path] = {}
        if not root:
            return
        folder = Path(os.path.expanduser(str(root)))
        if (folder / "library").is_dir():
            folder = folder / "library"
        if not folder.is_dir():
            return
        try:
            entries = list(os.scandir(folder))
        except OSError:
            return
        for entry in sorted(entries, key=lambda e: e.name):
            name = entry.name
            if not name.lower().endswith(".md"):
                continue
            try:
                if not entry.is_file() or entry.stat().st_size < MIN_BYTES:
                    continue
            except OSError:
                continue
            stem = name[:-3]
            if stem.startswith("K:"):
                self._keys.setdefault(stem[2:].upper(), Path(entry.path))
            elif stem.startswith("doi_"):
                slug = stem[4:]
                for prefix in _URL_PREFIXES:
                    if slug.lower().startswith(prefix):
                        slug = slug[len(prefix):]
                        break
                self._slugs.setdefault(slug.lower(), Path(entry.path))

    def __len__(self) -> int:
        return len(self._keys) + len(self._slugs)

    def find(self, item) -> Path | None:
        """Markdown file for an item: by DOI, item key, then attachment keys."""
        slug = doi_slug(item.doi) if item.doi else ""
        if slug and slug in self._slugs:
            return self._slugs[slug]
        for key in (item.key, *(a.key for a in item.attachments)):
            found = self._keys.get(str(key).upper())
            if found is not None:
                return found
        return None


def ft_cache_path(data_dir, attachment) -> Path:
    """Zotero's full-text cache file for an attachment."""
    return Path(data_dir) / "storage" / attachment.key / ".zotero-ft-cache"


def _stored(item) -> list:
    """Stored attachments, PDFs first, each group in attachment order."""
    stored = [a for a in item.attachments if a.link_mode in STORED_LINK_MODES]
    pdfs = [a for a in stored if a.content_type == "application/pdf"]
    return pdfs + [a for a in stored if a.content_type != "application/pdf"]


def _select(item, data_dir, corpus):
    """Pick the source using file stats only. Returns (source, path, attachment, stat, signature)."""
    if corpus is not None:
        md = corpus.find(item)
        if md is not None:
            try:
                st = md.stat()
            except OSError:
                st = None
            if st is not None and st.st_size >= MIN_BYTES:
                return ("markdown", md, None,
                        f"markdown:{md.name}:{st.st_size}:{st.st_mtime_ns}")
    parts = []
    stored = _stored(item)
    for att in stored:
        path = ft_cache_path(data_dir, att)
        try:
            st = path.stat()
            size = st.st_size
        except OSError:
            st, size = None, -1
        if st is not None and size >= MIN_BYTES:
            return ("ft-cache", path, att, f"ft-cache:{att.key}:{size}:{st.st_mtime_ns}")
        parts.append(f"{att.key}:{size}")
    return ("metadata", None, None, "metadata:" + "|".join(parts))


def text_signature(item, data_dir, corpus=None) -> str:
    """Signature of the chosen text; stats files only, never reads them."""
    return _select(item, data_dir, corpus)[3]


def _read(path: Path) -> str:
    with open(path, "r", encoding="utf-8", errors="replace", newline="") as fh:
        return fh.read()


def _damage_flag(text: str) -> tuple[str, ...]:
    """('text_damaged',) when the prose (structured tables left aside) shows conversion damage."""
    marker = MARKER.search(text)
    return ("text_damaged",) if damage(text[:marker.start()] if marker else text) else ()


def choose_text(item, data_dir, corpus=None) -> TextResult:
    """Best available text: Markdown, then Zotero's cache, then title and abstract."""
    source, path, att, signature = _select(item, data_dir, corpus)
    if source == "markdown":
        values, body = split_front_matter(_read(path))
        flags = ("ocr",) if is_true(values.get("ocr")) else ()
        return TextResult("markdown", body, str(path), flags + _damage_flag(body), signature)
    if source == "ft-cache":
        flags: tuple[str, ...] = ()
        if (att.indexed_pages is not None and att.total_pages is not None
                and att.indexed_pages < att.total_pages):
            flags = ("truncated",)
        text = _read(path)
        return TextResult("ft-cache", text, str(path), flags + _damage_flag(text), signature)
    text = "\n\n".join(p for p in (item.title, item.abstract) if p)
    flags = ("body_not_read",)
    if any(a.content_type == "application/pdf" for a in _stored(item)):
        flags += ("scanned_or_empty",)
    return TextResult("metadata", text, None, flags, signature)


def _window(text: str, s: int, e: int, window: int, overlap: int) -> list[tuple[int, int]]:
    """Cut [s, e) into overlapping pieces of at most `window` characters."""
    spans: list[tuple[int, int]] = []
    pos = s
    zone = int(window * 0.7)
    while pos < e:
        end = min(pos + window, e)
        cut = end
        if end < e:
            lo = pos + zone
            i = text.rfind("\n\n", lo, end)
            if i >= 0:
                cut = i + 2
            else:
                i = text.rfind("\n", lo, end)
                if i >= 0:
                    cut = i + 1
        spans.append((pos, cut))
        if cut >= e:
            break
        pos = max(cut - overlap, pos + 1)
    return spans


def split_passages(text: str, source: str, *, window: int = 2000, overlap: int = 200) -> list[Passage]:
    """Split text into passages of at most `window` characters."""
    if not text or not text.strip():
        return []
    if source == "metadata":
        return [Passage("metadata", 0, len(text), text)]
    sections: list[tuple[str, int, int]] = []
    if source == "markdown":
        heads = list(_HEADING.finditer(text))
        if heads:
            if heads[0].start() > 0:
                sections.append(("", 0, heads[0].start()))
            for n, m in enumerate(heads):
                end = heads[n + 1].start() if n + 1 < len(heads) else len(text)
                sections.append((m.group(1).strip(), m.start(), end))
        else:
            sections.append(("", 0, len(text)))
    else:
        sections.append(("", 0, len(text)))
    passages: list[Passage] = []
    for name, s, e in sections:
        for a, b in _window(text, s, e, window, overlap):
            piece = text[a:b]
            if piece.strip():
                passages.append(Passage(name, a, b, piece))
    return passages


def build_passages(text: str, source: str, *, window: int = 2000,
                   overlap: int = 200) -> tuple[str, list[Passage], tuple[Table, ...]]:
    """The text as it is indexed, its passages and its structured tables.

    Positions (Passage.start/end, Table.start/end) refer to the returned text, in which each
    structured table stands as pipe rows; for a paper without such tables it is `text` itself.
    """
    prep = prepare(text, source, window)
    passages = split_passages(prep.text[:prep.body_end], source, window=window, overlap=overlap)
    for seg in prep.segments:
        name = f"Table {seg.number}"
        if seg.kind == "table":
            passages.append(Passage(name, seg.start, seg.end, prep.text[seg.start:seg.end], "table", seg.number))
        else:
            for a, b in _window(prep.text, seg.start, seg.end, window, overlap):
                if prep.text[a:b].strip():
                    passages.append(Passage(name, a, b, prep.text[a:b]))
    return prep.text, passages, prep.tables
