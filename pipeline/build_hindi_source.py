#!/usr/bin/env python3
"""Build the Hindi translation source DB from the AlQuran Cloud API.

The bundled Hindi translation is *Suhel Farooq Khan & Saifur Rahman Nadwi*
(Tanzil edition ``hi.hindi``). QUL does not carry it, so — unlike the other
translations — it isn't a QUL SQLite download. AlQuran Cloud mirrors the Tanzil
text verbatim and serves the whole Quran as JSON, which we reshape into the same
``translation(sura, ayah, ayah_key, text)`` schema the other ``*-simple.db``
sources use, so ``build_db.py`` ingests it with no special-casing.

Output (git-ignored): ``sources/hi-suhel-farooq-nadwi-simple.db``

Usage:
    python pipeline/build_hindi_source.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
import urllib.request
from pathlib import Path

EDITION = "hi.hindi"  # Tanzil edition id, as exposed by AlQuran Cloud
API_URL = f"https://api.alquran.cloud/v1/quran/{EDITION}"
OUT = Path(__file__).resolve().parent.parent / "sources" / "hi-suhel-farooq-nadwi-simple.db"

EXPECTED_AYAHS = 6236
EXPECTED_SURAHS = 114


def fetch() -> dict:
    print(f"[hindi] GET {API_URL}")
    with urllib.request.urlopen(API_URL, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def build(payload: dict) -> None:
    data = payload["data"]
    edition = data["edition"]
    print(f"[hindi] edition: {edition['englishName']} / {edition['name']}")

    rows: list[tuple[int, int, str, str]] = []
    for surah in data["surahs"]:
        s = surah["number"]
        for ayah in surah["ayahs"]:
            a = ayah["numberInSurah"]
            rows.append((s, a, f"{s}:{a}", ayah["text"]))

    surah_count = len(data["surahs"])
    if surah_count != EXPECTED_SURAHS or len(rows) != EXPECTED_AYAHS:
        sys.exit(
            f"[hindi] FATAL: expected {EXPECTED_SURAHS} surahs / {EXPECTED_AYAHS} "
            f"ayahs, got {surah_count} / {len(rows)}"
        )

    if OUT.exists():
        OUT.unlink()
    con = sqlite3.connect(OUT)
    con.execute(
        "CREATE TABLE translation (sura INTEGER, ayah INTEGER, ayah_key TEXT, text TEXT)"
    )
    con.executemany("INSERT INTO translation VALUES (?,?,?,?)", rows)
    con.commit()
    con.close()
    print(f"[hindi] wrote {len(rows)} ayahs -> {OUT} ({OUT.stat().st_size/1024:.0f} KB)")


if __name__ == "__main__":
    build(fetch())
