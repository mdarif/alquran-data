#!/usr/bin/env python3
"""
Verify a compiled Al Quran seed database.

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
# Kashida (U+0640) carriers that seat the KFGQPC superscript marks. We carry ONLY
# the elongated-madd cases (a maddah follows) — those detach in Flutter without a
# carrier; plain dagger-alef stacks anchor fine on their own and a carrier there
# is just an ugly over-stretch (see build_db.py `--full-graft` for the legacy
# 1652). The golden v2 text alone has ~535; the surgical madd graft yields this.
# If a rebuild drops the grafting the count collapses and the madd breaks.
EXPECTED_TATWEELS = 1163

# Upper bounds for sanity (None = skip range check)
RANGES = {
    "page_number": (1, 604),
    "juz_number": (1, 30),
    "hizb_number": (1, 60),
    "rub_el_hizb": (1, 240),
    "ruku_number": (1, 600),  # generous upper bound; counts vary by tradition
}


# IndoPak text is authored for PDMS_Saleem; build_indopak_source.py normalises it
# for Noorehuda. These guards catch a re-source that forgets to normalise (PUA /
# format controls leak through) and pin the exact orthography the owner flagged on
# al-Fatiha. Letters are asserted by codepoint so the fixes can't silently regress.
PUA_LO, PUA_HI = 0xE000, 0xF8FF
INDOPAK_FORBIDDEN_CONTROLS = {0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0xFEFF, 0x0604}
# (surah, ayah, label, predicate(text) -> ok). Encodes the authentic IndoPak spelling.
INDOPAK_CANARIES = [
    (1, 2, "al-hamdu has the fatha on the alef (اَ)", lambda t: t.startswith("اَ")),
    (1, 4, "maalik uses the dagger-alef (مٰ)", lambda t: t.startswith("مٰ")),
    (1, 5, "iyyaka is bare alef+kasra, no spurious hamza", lambda t: t.startswith("اِ") and "إ" not in t),
    (1, 6, "ihdina has the kasra under the alef (اِ)", lambda t: t.startswith("اِ")),
]


def verify_indopak(conn: sqlite3.Connection, problems: list[str], warnings: list[str]) -> None:
    """Check the IndoPak column: normalised (no PUA/controls), correct spelling,
    and — when the font + shaping libs are available — 0 .notdef in Noorehuda."""
    rows = conn.execute(
        "SELECT surah_id, ayah_number, text_arabic_indopak FROM ayahs"
    ).fetchall()
    text = {(s, a): t for s, a, t in rows}

    leaked_pua = leaked_ctrl = 0
    for t in text.values():
        for ch in t:
            cp = ord(ch)
            if PUA_LO <= cp <= PUA_HI:
                leaked_pua += 1
            elif cp in INDOPAK_FORBIDDEN_CONTROLS:
                leaked_ctrl += 1
    if leaked_pua:
        problems.append(f"indopak: {leaked_pua} Private-Use-Area glyph(s) not normalised")
    if leaked_ctrl:
        problems.append(f"indopak: {leaked_ctrl} zero-width/format control(s) not stripped")

    for s, a, label, ok in INDOPAK_CANARIES:
        t = text.get((s, a), "")
        if not ok(t):
            problems.append(f"indopak {s}:{a} — {label} [got: {t[:12]!r}]")

    _verify_indopak_shaping(text, warnings)


def _verify_indopak_shaping(text: dict, warnings: list[str]) -> None:
    """Best-effort: shape every IndoPak ayah against Noorehuda and assert 0 .notdef.
    Skipped (with a note) when uharfbuzz / fontTools / the font aren't present, so
    verify_db.py keeps working stdlib-only in CI."""
    try:
        import uharfbuzz as hb  # type: ignore
    except ImportError:
        warnings.append("indopak: uharfbuzz not installed — skipped 0-.notdef shape check")
        return
    font_path = next(
        (p for p in (
            Path("../alquran-app/assets/fonts/Noorehuda.ttf"),
            Path("assets/fonts/Noorehuda.ttf"),
        ) if p.exists()),
        None,
    )
    if font_path is None:
        warnings.append("indopak: Noorehuda.ttf not found — skipped 0-.notdef shape check")
        return
    font = hb.Font(hb.Face(hb.Blob.from_file_path(str(font_path))))
    notdef_ayahs = 0
    for t in text.values():
        buf = hb.Buffer()
        buf.add_str(t)
        buf.guess_segment_properties()
        hb.shape(font, buf)
        if any(g.codepoint == 0 for g in buf.glyph_infos):
            notdef_ayahs += 1
    if notdef_ayahs:
        warnings.append(f"indopak: {notdef_ayahs} ayah(s) shape to .notdef in Noorehuda")
    else:
        print(f"indopak: 0 .notdef shaping all {len(text)} ayahs in Noorehuda ({font_path.name})")


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

    # IndoPak column (Phase 2): optional, but if present must be COMPLETE — a
    # partial fill would render blank ayahs in IndoPak mode.
    indopak_filled = conn.execute(
        "SELECT COUNT(*) FROM ayahs "
        "WHERE text_arabic_indopak IS NOT NULL AND TRIM(text_arabic_indopak) != ''"
    ).fetchone()[0]
    print(f"indopak ayahs: {indopak_filled}")
    if indopak_filled and indopak_filled != EXPECTED_AYAHS:
        problems.append(
            f"text_arabic_indopak partially filled ({indopak_filled}/{EXPECTED_AYAHS}) "
            "— must be complete or absent"
        )
    if indopak_filled == EXPECTED_AYAHS:
        verify_indopak(conn, problems, warnings)

    # Kashida carriers (elongated-madd fix): the count must match the canonical
    # edition, and the canary verse Al-Maidah 5:1 must open with the carried madd.
    n_tatweel = sum(
        t.count("ـ")
        for (t,) in conn.execute("SELECT text_arabic_uthmani FROM ayahs")
    )
    print(f"tatweel carriers: {n_tatweel}")
    if n_tatweel != EXPECTED_TATWEELS:
        problems.append(
            f"expected {EXPECTED_TATWEELS} tatweel carriers, found {n_tatweel} "
            "(kashida grafting missing? elongated madd will break)"
        )
    canary = conn.execute(
        "SELECT text_arabic_uthmani FROM ayahs WHERE surah_id=5 AND ayah_number=1"
    ).fetchone()[0]
    if not canary.startswith("يَـٰٓ"):  # يَـٰٓ
        problems.append("Al-Maidah 5:1 does not open with the carried madd (يَـٰٓ)")

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

    # sajda count (Quran has exactly 15 sajda ayahs)
    n_sajda = conn.execute("SELECT COUNT(*) FROM ayahs WHERE sajda = 1").fetchone()[0]
    if n_sajda != 15:
        warnings.append(f"expected 15 sajda ayahs, found {n_sajda}")
    else:
        print(f"sajda: {n_sajda} ayahs")

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
