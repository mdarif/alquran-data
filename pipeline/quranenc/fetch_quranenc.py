#!/usr/bin/env python3
"""Download a QuranEnc.com translation and reshape it into this repo's
per-ayah ``*-simple.db`` format, ready for a ``file:`` entry in
``config/sources.yaml``.

QuranEnc publishes a ready-made SQLite export per edition (see
``database_uncompressed_url`` from ``translations/list``, surfaced by
``survey_quranenc.py``) with a ``translations(sura, aya, translation,
footnotes)`` table — already exactly 6236 rows / 114 surahs, no pagination or
per-surah API calls needed. This script just downloads that file, validates
it, and rewrites it into the ``translation(sura, ayah, ayah_key, text)``
shape ``build_db.py`` already auto-detects (matching e.g.
``build_hindi_source.py``), so no changes are needed there.

Footnotes are dropped for now (QuranEnc embeds footnote markers inline in
``translation`` text as bracketed digits; the app has no footnote-rendering
UI yet — inspect a sample before shipping and strip/renumber if they leak
digits into the reading flow, matching the Indonesian-edition precedent in
TRANSLATIONS-ROADMAP.md).

Output (git-ignored): ``sources/<slug>-simple.db``

Usage:
    python3 pipeline/quranenc/fetch_quranenc.py english_hilali_khan en-hilali-khan-quranenc
"""
from __future__ import annotations

import sqlite3
import sys
import urllib.request
from pathlib import Path

LIST_URL = "https://quranenc.com/api/v1/translations/list"
USER_AGENT = "Mozilla/5.0 (compatible; alquran-data-pipeline/1.0)"
EXPECTED_SURAHS = 114
EXPECTED_AYAHS = 6236
SOURCES_DIR = Path(__file__).resolve().parent.parent.parent / "sources"


def resolve_download_url(key: str) -> tuple[str, dict]:
    """Look up `key` in the translations/list API; if absent (the API's list is
    a curated subset — some site editions, e.g. marathi_ansari, aren't in it),
    fall back to the site's standard download URL pattern directly."""
    import json

    req = urllib.request.Request(LIST_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        editions = json.loads(resp.read().decode("utf-8"))["translations"]
    for e in editions:
        if e["key"] == key:
            return e["database_uncompressed_url"], e

    url = f"https://quranenc.com/downloads/sqlite/{key}.sqlite"
    print(f"[quranenc] '{key}' not in {LIST_URL} — falling back to {url}")
    return url, {"title": key, "version": "unknown (not in API list)"}


def download(url: str, dest: Path) -> None:
    print(f"[quranenc] GET {url}")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as f:
        f.write(resp.read())


def reshape(raw_db: Path, slug: str) -> Path:
    src = sqlite3.connect(raw_db)
    rows = src.execute("SELECT sura, aya, translation FROM translations").fetchall()
    src.close()

    surahs = {s for s, _, _ in rows}
    if len(surahs) != EXPECTED_SURAHS or len(rows) != EXPECTED_AYAHS:
        sys.exit(
            f"[quranenc] FATAL: expected {EXPECTED_SURAHS} surahs / {EXPECTED_AYAHS} "
            f"ayahs, got {len(surahs)} / {len(rows)}"
        )
    empty = [f"{s}:{a}" for s, a, t in rows if not t or not t.strip()]
    if empty:
        sys.exit(f"[quranenc] FATAL: {len(empty)} empty verses, e.g. {empty[:5]}")

    out = SOURCES_DIR / f"{slug}-simple.db"
    if out.exists():
        out.unlink()
    con = sqlite3.connect(out)
    con.execute(
        "CREATE TABLE translation (sura INTEGER, ayah INTEGER, ayah_key TEXT, text TEXT)"
    )
    con.executemany(
        "INSERT INTO translation VALUES (?,?,?,?)",
        [(s, a, f"{s}:{a}", t) for s, a, t in rows],
    )
    con.commit()
    con.close()
    print(f"[quranenc] wrote {len(rows)} ayahs -> {out} ({out.stat().st_size / 1024:.0f} KB)")
    return out


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(f"Usage: {sys.argv[0]} <quranenc-key> <output-slug>")
    key, slug = sys.argv[1], sys.argv[2]

    url, meta = resolve_download_url(key)
    print(f"[quranenc] {meta['title']}  (v{meta['version']})")

    raw = SOURCES_DIR / f".{key}.raw.sqlite"
    SOURCES_DIR.mkdir(exist_ok=True)
    download(url, raw)
    try:
        reshape(raw, slug)
    finally:
        raw.unlink(missing_ok=True)

    print(
        f"[quranenc] Next: add a `sources.translations` entry in config/sources.yaml "
        f"(file: sources/{slug}-simple.db, source_url: https://quranenc.com/en/{key}/), "
        f"a TRANSLATIONS-ROADMAP.md candidate entry, and an ATTRIBUTION.md credit block "
        f"citing QuranEnc.com terms (v{meta['version']}, unmodified + attribution + "
        f"preserve version metadata) before rebuilding."
    )


if __name__ == "__main__":
    main()
