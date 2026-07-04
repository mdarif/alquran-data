#!/usr/bin/env python3
"""Build the IndoPak Arabic source DB for the Noorehuda script option.

Source: the **authentic Quran.com IndoPak** text (the `text_indopak` field, QPC /
PDMS IndoPak lineage), one row per ayah keyed "surah:ayah". It is fetched from the
Quran.com content API and cached at ``sources/quran-indopak-quran-com.json`` (the
live API now requires auth — 403 — so the snapshot is the build artifact). This is
the text with the *correct IndoPak orthography* the owner flagged: bare alef +
kasra for "iyyaka" (no spurious hamza), dagger-alef for "maalik", the zer under the
alef in "ihdina" — none of which the earlier standard-Unicode `quran-simple-enhanced`
text had right.

Why it needs normalising: the Quran.com text is authored for the **PDMS_Saleem**
font and carries Private-Use-Area glyphs (1383 of them) for a handful of marks. We:
  * MAP the PUA marks that have a standard-Unicode equivalent
    (E003 -> U+0656 subscript alef, E004 -> U+0657 inverted damma) and the two
    letters Noorehuda spells the standard way (U+06AA swash-kaf -> U+0643 kaf,
    U+06D2 yeh-barree -> U+064A yeh);
  * STRIP the 7 IndoPak-specific waqf symbols that have NO Unicode form
    (E01A/E01B/E01C/E01E/E01F/E021/E022 — the ز ص ق قف وقفة ع-ruku family, ~1378
    occurrences). The *standard-Unicode* waqf marks (U+0615 ﺹ, U+06D6, U+06D9 ﻻ,
    U+06DA ﺝ …) are KEPT and render natively in Noorehuda;
  * STRIP zero-width / directional / format controls (200B, 200C/D, 200E/F, FEFF,
    0604) and fold en/em spaces (2002/2003) to a normal space.

After this, the text shapes with **0 .notdef** against Noorehuda across all 6236
ayahs and the (surah,ayah) key set is identical to the Uthmani text — both verified
headlessly with HarfBuzz + fontTools (see the canaries in verify_db.py). Unlike the
AlQuran-Cloud source, Quran.com serves each ayah WITHOUT a bundled basmala
(2:1 = "الٓمّٓ"), so there is no basmala-strip step.

Output: ``sources/arabic-indopak-quran-com.db`` (table ``arabic_text`` with
``sura, ayah, text``) — the shape ``build_db.py``'s ``read_ayah_text`` expects.

Usage:
  python3 pipeline/build_indopak_source.py
"""
import json
import sqlite3
from pathlib import Path

SRC = Path("sources/quran-indopak-quran-com.json")
OUT = Path("sources/arabic-indopak-quran-com.db")
EXPECTED = 6236

# --- codepoint normalisation: Quran.com PDMS-authored IndoPak -> Noorehuda ----
# PUA marks with a standard-Unicode equivalent.
PUA_VOWEL_MAP = {0xE003: 0x0656, 0xE004: 0x0657}  # subscript alef, inverted damma
# Letters Noorehuda spells the standard way.
LETTER_MAP = {0x06AA: 0x0643, 0x06D2: 0x064A}     # swash-kaf -> kaf, yeh-barree -> yeh
# Typographic spaces -> normal space.
SPACE_MAP = {0x2002: 0x0020, 0x2003: 0x0020}      # en / em space
# IndoPak-specific waqf symbols (PUA) with NO Unicode form -> dropped (v1).
# The standard-Unicode waqf marks (0615, 06D6, 06D9, 06DA, …) are kept.
WAQF_STRIP = {0xE01A, 0xE01B, 0xE01C, 0xE01E, 0xE01F, 0xE021, 0xE022}
# Zero-width / directional / format controls that must not live in stored text.
FORMAT_STRIP = {0x200B, 0x200C, 0x200D, 0x200E, 0x200F, 0xFEFF, 0x0604}

# --- un-stackable waqf signs (Noorehuda mkmk gap) ---------------------------
# Noorehuda positions a madd-class above-mark fine, but a *small-high waqf sign*
# stacked ON TOP of one collapses to the glyph origin (it has no mark-to-mark
# anchor), colliding with the letter. Seen on the muqattaʿāt 2:1 (الٓمّٓۚ) and
# 80:24 (…هٖۤۙ). We drop only the offending waqf SIGN in that exact stack —
# letters + ḥarakāt/madd are untouched. Standalone/2nd-mark waqf signs (the
# common case, ~1400 verses) are kept. verify_db asserts no collapse remains.
MADD_MARKS = {0x0653, 0x06E4}                 # maddah above / small-high madda
STACKING_WAQF = set(range(0x06D6, 0x06DD))    # small-high waqf 06D6..06DC (incl 06D9/06DA)


def _drop_stacking_waqf(s: str) -> str:
    """Remove a small-high waqf sign that would stack on a madd-class mark."""
    out: list[str] = []
    had_madd = False  # a madd-class above-mark seen on the current base cluster
    for ch in s:
        cp = ord(ch)
        if ch == " ":
            had_madd = False
            out.append(ch)
        elif 0x0600 <= cp <= 0x06FF and not (0x0621 <= cp <= 0x064A) and cp not in (0x0640, 0x0670, 0x0671):
            # a combining mark (not a base letter / tatweel / dagger-alef / wasla)
            if cp in MADD_MARKS:
                had_madd = True
                out.append(ch)
            elif cp in STACKING_WAQF and had_madd:
                continue  # would collapse onto the madd — drop it
            else:
                out.append(ch)
        else:
            had_madd = False  # base letter resets the cluster
            out.append(ch)
    return "".join(out)


def normalise(s: str) -> str:
    out: list[str] = []
    for ch in s:
        cp = ord(ch)
        if cp in WAQF_STRIP or cp in FORMAT_STRIP:
            continue
        if cp in PUA_VOWEL_MAP:
            out.append(chr(PUA_VOWEL_MAP[cp]))
        elif cp in LETTER_MAP:
            out.append(chr(LETTER_MAP[cp]))
        elif cp in SPACE_MAP:
            out.append(chr(SPACE_MAP[cp]))
        else:
            out.append(ch)
    # collapse any doubled / edge spaces left by stripped marks
    return _drop_stacking_waqf(" ".join("".join(out).split()))


def main() -> None:
    if not SRC.exists():
        raise SystemExit(
            f"missing {SRC} — the cached Quran.com IndoPak snapshot "
            "(text_indopak field) must be present"
        )
    raw = json.loads(SRC.read_text(encoding="utf-8"))
    if len(raw) != EXPECTED:
        raise SystemExit(f"expected {EXPECTED} ayahs, got {len(raw)}")

    text: dict[tuple[int, int], str] = {}
    for key, val in raw.items():
        s, a = key.split(":")
        text[(int(s), int(a))] = normalise(val)

    if OUT.exists():
        OUT.unlink()
    out = sqlite3.connect(OUT)
    out.execute(
        "CREATE TABLE arabic_text (sura INTEGER, ayah INTEGER, text TEXT, "
        "PRIMARY KEY (sura, ayah))"
    )
    out.executemany(
        "INSERT INTO arabic_text(sura, ayah, text) VALUES (?,?,?)",
        [(s, a, text[(s, a)]) for (s, a) in sorted(text)],
    )
    out.commit()
    n = out.execute("SELECT COUNT(*) FROM arabic_text").fetchone()[0]
    empty = out.execute(
        "SELECT COUNT(*) FROM arabic_text WHERE text IS NULL OR text = ''"
    ).fetchone()[0]
    out.close()
    print(f"wrote {OUT}: {n} ayahs, {empty} empty (authentic Quran.com IndoPak, PUA-normalised)")
    if n != EXPECTED or empty:
        raise SystemExit("sanity check failed")


if __name__ == "__main__":
    main()
