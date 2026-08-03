#!/usr/bin/env python3
"""Export the Al Marfa Roman Urdu text into a simple SQLite source.

The main build pipeline already knows how to ingest "simple" per-ayah SQLite
translation sources. This script is the narrow bridge from:

    ../alquran-roman-urdu/data/roman-urdu/surah-001.json ... surah-114.json

to:

    sources/ur-roman-almarfa-simple.db

It does not publish anything by itself. The resulting DB is then listed in
config/sources.yaml (slug `ur-roman-almarfa`, type `transliteration`) and
emitted as a downloadable edition by pipeline/build_editions.py.

Every source verse currently carries `"status": "beta-unverified"` — nothing
in ../alquran-roman-urdu has been human-reviewed or approved yet (see that
repo's AGENTS.md non-negotiable #2: "nothing ships unreviewed"). This script
does not block ingestion on that status — the third-party
ur-roman-junagarhi-experimental edition it replaces was ingested and shipped
in the same unreviewed state, labelled "(Experimental)" so consumers never
mistake it for approved text. `ur-roman-almarfa`'s `name`/`license` fields in
config/sources.yaml carry the same kind of explicit label; review-gating is
this project's own AGENTS.md concern, not something to duplicate here as a
second source of truth. Re-running this export after a review pass simply
picks up whatever text is on disk, unconditionally.
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
    ap.add_argument("--src", default="../alquran-roman-urdu/data/roman-urdu")
    ap.add_argument("--out", default="sources/ur-roman-almarfa-simple.db")
    args = ap.parse_args()

    src = Path(args.src)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    rows: list[tuple[int, int, str]] = []
    unverified = 0
    for surah in range(1, EXPECTED_SURAHS + 1):
        path = src / f"surah-{surah:03d}.json"
        if not path.exists():
            raise SystemExit(f"missing surah JSON: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        ayahs = data.get("ayahs")
        if not isinstance(ayahs, dict):
            raise SystemExit(f"{path} has no ayahs object")
        if data.get("status") != "approved":
            unverified += len(ayahs)
        for ayah_key, text in sorted(ayahs.items(), key=lambda i: int(i[0])):
            text = str(text).strip()
            if not text:
                raise SystemExit(f"{path} ayah {ayah_key} is blank")
            if any(ch.isdigit() for ch in text):
                raise SystemExit(
                    f"{path} ayah {ayah_key} contains a digit — the fused-"
                    "footnote-marker defect that disqualified the third-party "
                    f"edition this one replaces: {text!r}"
                )
            rows.append((surah, int(ayah_key), text))

    if len(rows) != EXPECTED_AYAHS:
        raise SystemExit(
            f"Roman Urdu export has {len(rows)}/{EXPECTED_AYAHS} ayahs"
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

    print(f"wrote {out}: {len(rows)} ayahs ({unverified} not status=approved)")


if __name__ == "__main__":
    main()
