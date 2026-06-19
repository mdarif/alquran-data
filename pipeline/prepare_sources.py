#!/usr/bin/env python3
"""
AlMarfa360 Quran — preprocess raw QUL exports into builder-ready inputs.

QUL ships the MVP data in shapes that don't map 1:1 onto build_db.py:

  * Arabic is a *word-by-word* `words` table (KFGQPC Hafs), not ayah-level text.
  * Structural navigation is split across several files: juz / hizb / rub / ruku
    are start-marker tables (one row per division), sajda is a list of ayahs,
    and there is no page table at all — page numbers live in a separate Mushaf
    *layout* database (QPC V2, 604 pages) keyed by global word id.

This script reads those raw files (leaving them untouched) and emits the two
derived per-ayah inputs that build_db.py auto-detects cleanly:

  sources/arabic-ayah.sqlite   ayahs(surah, ayah, text)
  sources/structure.sqlite     ayah_meta(surah, ayah, page_number, juz_number,
                               hizb_number, rub_el_hizb, ruku_number, sajda)

Page per ayah = the printed page on which the ayah's first word falls.
juz/hizb/rub/ruku per ayah = expanded from each division's start markers.

Re-run whenever the raw QUL files change, then run build_db.py.
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
          out_arabic: Path, out_structure: Path) -> None:
    # --- Arabic: aggregate words -> ayah text (ordered by word position) ---
    wc = sqlite3.connect(words_db)
    word_rows = wc.execute("SELECT surah, ayah, word, text FROM words").fetchall()
    first_word: dict[tuple[int, int], int] = {}
    for wid, s, a in wc.execute("SELECT id, surah, ayah FROM words ORDER BY id"):
        first_word.setdefault((int(s), int(a)), int(wid))
    wc.close()

    buckets: dict[tuple[int, int], list[tuple[int, str]]] = {}
    for s, a, w, t in word_rows:
        if t is None:
            continue
        buckets.setdefault((int(s), int(a)), []).append((int(w), str(t)))
    arabic: dict[tuple[int, int], str] = {}
    for key, ws in buckets.items():
        ws.sort(key=lambda x: x[0])
        arabic[key] = " ".join(t for _, t in ws).strip()
    ayah_order = sorted(arabic.keys())

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

    # --- Emit arabic-ayah.sqlite ------------------------------------------
    out_arabic.unlink(missing_ok=True)
    ac = sqlite3.connect(out_arabic)
    ac.execute("CREATE TABLE ayahs(surah INT, ayah INT, text TEXT)")
    ac.executemany("INSERT INTO ayahs VALUES (?,?,?)",
                   [(s, a, arabic[(s, a)]) for (s, a) in ayah_order])
    ac.commit()
    ac.close()

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
    print(f"[prepare] arabic -> {out_arabic}")
    print(f"[prepare] structure -> {out_structure}")
    print(f"[prepare] pages: {min(pages)}..{max(pages)} ({len(pages)} distinct)")
    print(f"[prepare] juz max {max(juz.values())} | hizb max {max(hizb.values())} | "
          f"rub max {max(rub.values())} | ruku max {max(ruku.values())} | "
          f"sajda {len(sajda_set)}")
    missing = [p for p in ayah_order if ayah_page(p) is None]
    if missing:
        print(f"[prepare] WARNING: {len(missing)} ayahs have no page "
              f"(e.g. {missing[:5]})")


def main() -> None:
    ap = argparse.ArgumentParser(description="Preprocess raw QUL files into builder inputs.")
    ap.add_argument("--sources", default="sources", help="folder holding raw QUL files")
    ap.add_argument("--words", default="qpc-hafs-word-by-word.db")
    ap.add_argument("--layout", default="qpc-v2-15-lines.db")
    ap.add_argument("--juz", default="quran-metadata-juz.sqlite")
    ap.add_argument("--hizb", default="quran-metadata-hizb.sqlite")
    ap.add_argument("--rub", default="quran-metadata-rub.sqlite")
    ap.add_argument("--ruku", default="quran-metadata-ruku.sqlite")
    ap.add_argument("--sajda", default="quran-metadata-sajda.sqlite")
    ap.add_argument("--out-arabic", default="arabic-ayah.sqlite")
    ap.add_argument("--out-structure", default="structure.sqlite")
    args = ap.parse_args()

    src = Path(args.sources)
    build(
        src / args.words, src / args.layout, src / args.juz, src / args.hizb,
        src / args.rub, src / args.ruku, src / args.sajda,
        src / args.out_arabic, src / args.out_structure,
    )


if __name__ == "__main__":
    main()
