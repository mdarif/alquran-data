#!/usr/bin/env python3
"""
Al Quran — preprocess raw QUL exports into builder-ready structural metadata.

The Arabic Uthmani TEXT is no longer derived here. We ship github.com/quran's
golden `quran.ar.uthmani.v2.db` (QPC Hafs, ayah-by-ayah) verbatim — see
config/sources.yaml. That text is co-designed with the KFGQPC font
(UthmanicHafs1B Ver13), so there is NO tatweel-grafting and NO mark-stripping:
the old `arabic-ayah.sqlite` derivation and its Tanzil-canonical diff are gone.

This script now produces only the structural navigation indices, which QUL still
ships in shapes build_db.py can't read directly:

  * juz / hizb / rub / ruku are start-marker tables (one row per division)
  * sajda is a list of ayahs
  * there is no page table — page numbers live in a separate Mushaf *layout*
    database (QPC V2, 604 pages) keyed by global word id

Output:
  sources/structure.sqlite   ayah_meta(surah, ayah, page_number, juz_number,
                             hizb_number, rub_el_hizb, ruku_number, sajda)

Page per ayah = the printed page on which the ayah's first word falls.
juz/hizb/rub/ruku per ayah = expanded from each division's start markers.

Re-run whenever the raw QUL metadata files change, then run build_db.py.
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def _verse_key(s: str) -> tuple[int, int]:
    a, b = str(s).split(":")
    return (int(a), int(b))


def _expand_markers(starts: list[tuple[int, int]],
                    ayah_order: list[tuple[int, int]]) -> dict[tuple[int, int], int]:
    """Each start marker opens division N; it applies until the next marker."""
    start_idx = {pos: i + 1 for i, pos in enumerate(starts)}
    out: dict[tuple[int, int], int] = {}
    current = 0
    for pos in ayah_order:
        if pos in start_idx:
            current = start_idx[pos]
        out[pos] = current
    return out


def _starts(db: Path, table: str, order_col: str,
            key_col: str = "first_verse_key") -> list[tuple[int, int]]:
    c = sqlite3.connect(db)
    try:
        rows = c.execute(f"SELECT {key_col} FROM {table} ORDER BY {order_col}").fetchall()
    finally:
        c.close()
    return [_verse_key(r[0]) for r in rows]


def build(words_db: Path, layout_db: Path, juz_db: Path, hizb_db: Path,
          rub_db: Path, ruku_db: Path, sajda_db: Path,
          out_structure: Path) -> None:
    # --- Ayah order + each ayah's first word id (for page mapping) ----------
    # The word-by-word DB is used only as the canonical (surah, ayah) ordering
    # and the first-word-id index; its TEXT is not read (text comes from the
    # golden quran.ar.uthmani.v2.db at build time).
    wc = sqlite3.connect(words_db)
    first_word: dict[tuple[int, int], int] = {}
    for wid, s, a in wc.execute("SELECT id, surah, ayah FROM words ORDER BY id"):
        first_word.setdefault((int(s), int(a)), int(wid))
    wc.close()
    ayah_order = sorted(first_word.keys())
    if len(ayah_order) != 6236:
        print(f"[prepare] WARNING: expected 6236 ayahs, got {len(ayah_order)}")

    # --- Page: word id -> page; ayah page = page of the ayah's first word ---
    lc = sqlite3.connect(layout_db)
    word_page: dict[int, int] = {}
    for page_no, fw, lw in lc.execute(
        "SELECT page_number, first_word_id, last_word_id FROM pages "
        "WHERE line_type='ayah' AND first_word_id != '' AND last_word_id != ''"
    ):
        for wid in range(int(fw), int(lw) + 1):
            word_page[wid] = int(page_no)
    lc.close()

    def ayah_page(pos: tuple[int, int]):
        return word_page.get(first_word.get(pos, -1))

    # --- Structural divisions from start markers ---------------------------
    juz = _expand_markers(_starts(juz_db, "juz", "juz_number"), ayah_order)
    hizb = _expand_markers(_starts(hizb_db, "hizbs", "hizb_number"), ayah_order)
    rub = _expand_markers(_starts(rub_db, "rub", "rub_number"), ayah_order)
    ruku = _expand_markers(_starts(ruku_db, "ruku", "ruku_number"), ayah_order)

    sc = sqlite3.connect(sajda_db)
    sajda_set = {_verse_key(r[0]) for r in sc.execute("SELECT verse_key FROM sajdah")}
    sc.close()

    # --- Emit structure.sqlite --------------------------------------------
    out_structure.unlink(missing_ok=True)
    pc = sqlite3.connect(out_structure)
    pc.execute(
        "CREATE TABLE ayah_meta(surah INT, ayah INT, page_number INT, "
        "juz_number INT, hizb_number INT, rub_el_hizb INT, ruku_number INT, sajda INT)"
    )
    pc.executemany(
        "INSERT INTO ayah_meta VALUES (?,?,?,?,?,?,?,?)",
        [(s, a, ayah_page((s, a)), juz[(s, a)], hizb[(s, a)], rub[(s, a)],
          ruku[(s, a)], 1 if (s, a) in sajda_set else 0) for (s, a) in ayah_order],
    )
    pc.commit()
    pc.close()

    # --- Report -----------------------------------------------------------
    pages = {ayah_page(p) for p in ayah_order} - {None}
    print(f"[prepare] ayahs: {len(ayah_order)}")
    print(f"[prepare] structure -> {out_structure}")
    if pages:
        print(f"[prepare] pages: {min(pages)}..{max(pages)} ({len(pages)} distinct)")
    else:
        print("[prepare] WARNING: no page numbers derived — check layout DB")
    print(f"[prepare] juz max {max(juz.values())} | hizb max {max(hizb.values())} | "
          f"rub max {max(rub.values())} | ruku max {max(ruku.values())} | "
          f"sajda {len(sajda_set)}")
    missing = [p for p in ayah_order if ayah_page(p) is None]
    if missing:
        print(f"[prepare] WARNING: {len(missing)} ayahs have no page "
              f"(e.g. {missing[:5]})")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Preprocess raw QUL metadata into structure.sqlite.")
    ap.add_argument("--sources", default="sources", help="folder holding raw QUL files")
    ap.add_argument("--words", default="qpc-hafs-word-by-word.db")
    ap.add_argument("--layout", default="qpc-v2-15-lines.db")
    ap.add_argument("--juz", default="quran-metadata-juz.sqlite")
    ap.add_argument("--hizb", default="quran-metadata-hizb.sqlite")
    ap.add_argument("--rub", default="quran-metadata-rub.sqlite")
    ap.add_argument("--ruku", default="quran-metadata-ruku.sqlite")
    ap.add_argument("--sajda", default="quran-metadata-sajda.sqlite")
    ap.add_argument("--out-structure", default="structure.sqlite")
    args = ap.parse_args()

    src = Path(args.sources)
    build(
        src / args.words, src / args.layout, src / args.juz, src / args.hizb,
        src / args.rub, src / args.ruku, src / args.sajda,
        src / args.out_structure,
    )


if __name__ == "__main__":
    main()
