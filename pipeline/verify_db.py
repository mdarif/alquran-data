#!/usr/bin/env python3
"""
Verify a compiled AlMarfa360 Quran seed database.

Checks the invariants that matter for a Quran reader:
  * exactly 114 surahs and 6236 ayahs
  * every ayah has non-empty Arabic text
  * each translation resource covers all 6236 ayahs (warns on gaps)
  * navigation indices, when present, fall in sane ranges
  * prints the recorded source checksums

Usage:
    python pipeline/verify_db.py --db assets/quran.db
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

EXPECTED_SURAHS = 114
EXPECTED_AYAHS = 6236

# Upper bounds for sanity (None = skip range check)
RANGES = {
    "page_number": (1, 604),
    "juz_number": (1, 30),
    "hizb_number": (1, 60),
    "rub_el_hizb": (1, 240),
    "ruku_number": (1, 600),  # generous upper bound; counts vary by tradition
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="assets/quran.db")
    args = ap.parse_args()

    path = Path(args.db)
    if not path.exists():
        sys.exit(f"db not found: {path}")

    conn = sqlite3.connect(path)
    problems: list[str] = []
    warnings: list[str] = []

    n_surahs = conn.execute("SELECT COUNT(*) FROM surahs").fetchone()[0]
    n_ayahs = conn.execute("SELECT COUNT(*) FROM ayahs").fetchone()[0]
    print(f"surahs: {n_surahs}  ayahs: {n_ayahs}")

    if n_surahs != EXPECTED_SURAHS:
        problems.append(f"expected {EXPECTED_SURAHS} surahs, found {n_surahs}")
    if n_ayahs != EXPECTED_AYAHS:
        problems.append(f"expected {EXPECTED_AYAHS} ayahs, found {n_ayahs}")

    empty = conn.execute(
        "SELECT COUNT(*) FROM ayahs WHERE text_arabic_uthmani IS NULL OR TRIM(text_arabic_uthmani) = ''"
    ).fetchone()[0]
    if empty:
        problems.append(f"{empty} ayahs have empty Arabic text")

    # surah total_ayahs vs actual
    bad_counts = conn.execute(
        "SELECT s.id, s.total_ayahs, COUNT(a.id) c FROM surahs s "
        "JOIN ayahs a ON a.surah_id = s.id GROUP BY s.id HAVING s.total_ayahs != c"
    ).fetchall()
    for sid, declared, actual in bad_counts:
        warnings.append(f"surah {sid}: total_ayahs={declared} but {actual} ayahs present")

    # translation coverage
    for rid, name, lang in conn.execute("SELECT id, name, language_code FROM resources").fetchall():
        cnt = conn.execute("SELECT COUNT(*) FROM translations WHERE resource_id=?", (rid,)).fetchone()[0]
        status = "ok" if cnt == EXPECTED_AYAHS else f"GAP ({EXPECTED_AYAHS - cnt} missing)"
        print(f"translation [{lang}] {name}: {cnt} ayahs -> {status}")
        if cnt != EXPECTED_AYAHS:
            warnings.append(f"translation '{name}' covers {cnt}/{EXPECTED_AYAHS} ayahs")

    # navigation index ranges
    for col, (lo, hi) in RANGES.items():
        row = conn.execute(
            f"SELECT MIN({col}), MAX({col}), COUNT(*) FROM ayahs WHERE {col} IS NOT NULL"
        ).fetchone()
        mn, mx, present = row
        if present == 0:
            warnings.append(f"{col}: no values populated")
            continue
        if mn < lo or mx > hi:
            warnings.append(f"{col}: out-of-range values (min={mn}, max={mx}, allowed {lo}-{hi})")
        else:
            print(f"{col}: {present} populated, range {mn}-{mx}")

    # checksums
    row = conn.execute("SELECT value FROM db_meta WHERE key='source_checksums'").fetchone()
    if row:
        print("\nsource checksums:")
        for fname, digest in json.loads(row[0]).items():
            print(f"  {fname}: {digest[:16]}…")

    conn.close()

    print()
    for w in warnings:
        print(f"WARN: {w}")
    for p in problems:
        print(f"FAIL: {p}")

    if problems:
        sys.exit(1)
    print("OK" if not warnings else "OK (with warnings)")


if __name__ == "__main__":
    main()
