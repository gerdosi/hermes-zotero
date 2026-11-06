"""The citation line of zotero_read. The only module that opens a network connection: loopback to Zotero."""
from __future__ import annotations

import html as html_lib
import json
import re
import urllib.parse
import urllib.request

ZOTERO_LOCAL_API = "http://127.0.0.1:23119/api"
STYLE = "apa"
TIMEOUT = 2.0
MAX_CHARS = 1000


def _sentence(piece: str) -> str:
    return piece if piece.endswith((".", "?", "!")) else piece + "."


def approximate_citation(creators, year, title, publication, doi) -> str:
    """An approximate author-year line built from index data."""
    names = [c.split(", ")[0] for c in creators if c]
    if not names:
        authors = ""
    elif len(names) == 1:
        authors = names[0]
    elif len(names) == 2:
        authors = f"{names[0]} & {names[1]}"
    else:
        authors = f"{names[0]} et al."
    when = f"({year})" if year else "(n.d.)"
    pieces = [_sentence(f"{authors} {when}" if authors else when)]
    for extra in ((title or "").strip(), (publication or "").strip()):
        if extra:
            pieces.append(_sentence(extra))
    if doi:
        pieces.append(f"https://doi.org/{doi}")
    return " ".join(pieces)


def html_to_text(value: str) -> str:
    """Plain text of a small HTML fragment."""
    text = html_lib.unescape(re.sub(r"<[^>]+>", "", value))
    return re.sub(r"\s+", " ", text).strip()


def item_url(base: str, library: str, key: str) -> str:
    """URL of one item in Zotero's local API, asking for the formatted reference."""
    query = urllib.parse.urlencode({"format": "json", "include": "bib", "style": STYLE})
    safe_key = urllib.parse.quote(key, safe="")
    if library == "user":
        return f"{base.rstrip('/')}/users/0/items/{safe_key}?{query}"
    return f"{base.rstrip('/')}/groups/{urllib.parse.quote(library, safe='')}/items/{safe_key}?{query}"


def fetch_zotero_citation(base: str, library: str, key: str, *, timeout: float = TIMEOUT) -> str | None:
    """Zotero's own APA reference for one item, or None for any problem (Zotero closed, API off, unknown item)."""
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # never through a proxy
        request = urllib.request.Request(item_url(base, library, key), headers={"Zotero-API-Version": "3"})
        with opener.open(request, timeout=timeout) as response:
            if response.status != 200:
                return None
            data = json.loads(response.read().decode("utf-8"))
        if isinstance(data, list) and len(data) == 1:
            data = data[0]
        if not isinstance(data, dict) or data.get("key") != key or not isinstance(data.get("bib"), str):
            return None
        return html_to_text(data["bib"])[:MAX_CHARS] or None
    except Exception:
        return None


def citation(base: str | None, library: str, key: str, *, creators, year, title, publication, doi) -> dict:
    """Zotero's formatted citation when its local API answers, otherwise an approximate line from the index."""
    if base:
        text = fetch_zotero_citation(base, library, key)
        if text:
            return {"text": text, "source": "zotero", "style": STYLE, "approximate": False}
    return {"text": approximate_citation(creators, year, title, publication, doi),
            "source": "index", "approximate": True}
