#!/usr/bin/env python3
"""Export the reviewed Ahsanul Kalam pilot JSON into a simple SQLite source.

The main build pipeline already knows how to ingest "simple" per-ayah SQLite
translation sources. This script is the narrow bridge from:

    dist/pilot/ahsanul-kalam/surah-001.json ... surah-114.json

to:

    sources/hi-ahsanul-kalam-simple.db

It does not publish anything by itself. The resulting DB is then listed in
config/sources.yaml and can be emitted as a downloadable edition by
pipeline/build_editions.py.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

EXPECTED_SURAHS = 114
EXPECTED_AYAHS = 6236


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="dist/pilot/ahsanul-kalam")
    ap.add_argument("--out", default="sources/hi-ahsanul-kalam-simple.db")
    args = ap.parse_args()

    src = Path(args.src)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    rows: list[tuple[int, int, str]] = []
    for surah in range(1, EXPECTED_SURAHS + 1):
        path = src / f"surah-{surah:03d}.json"
        if not path.exists():
            raise SystemExit(f"missing pilot surah JSON: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        ayahs = data.get("ayahs")
        if not isinstance(ayahs, dict):
            raise SystemExit(f"{path} has no ayahs object")
        for ayah_key, text in sorted(ayahs.items(), key=lambda i: int(i[0])):
            rows.append((surah, int(ayah_key), str(text).strip()))

    if len(rows) != EXPECTED_AYAHS:
        raise SystemExit(
            f"Ahsanul Kalam export has {len(rows)}/{EXPECTED_AYAHS} ayahs"
        )

    conn = sqlite3.connect(out)
    try:
        conn.executescript(
            """
            PRAGMA page_size = 1024;
            CREATE TABLE translations (
              surah INTEGER NOT NULL,
              ayah INTEGER NOT NULL,
              text TEXT NOT NULL,
              PRIMARY KEY (surah, ayah)
            );
            """
        )
        conn.executemany(
            "INSERT INTO translations(surah, ayah, text) VALUES (?, ?, ?)",
            rows,
        )
        conn.commit()
        conn.execute("VACUUM")
    finally:
        conn.close()

    print(f"wrote {out}: {len(rows)} ayahs")


if __name__ == "__main__":
    main()
