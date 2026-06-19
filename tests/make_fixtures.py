#!/usr/bin/env python3
"""
Generate tiny synthetic QUL-shaped source files so the pipeline can be smoke-
tested without downloading the real (large) resources.

It creates, under tests/fixtures/:
  * surah-names.sqlite                (2 surahs)
  * quran-uthmani.sqlite             (word-by-word `words` table)
  * quran-metadata.sqlite            (per-ayah page/juz/hizb/rub/ruku/sajda)
  * translation-urdu.sqlite          (ayah-keyed text)
  * translation-hindi.sqlite         (verse_key keyed text)
and a matching tests/fixtures/sources.yaml.

Run:  python tests/make_fixtures.py && python pipeline/build_db.py --config tests/fixtures/sources.yaml
"""
import sqlite3
from pathlib import Path

FX = Path(__file__).parent / "fixtures"
FX.mkdir(parents=True, exist_ok=True)

# Surah 1 (Al-Fatihah, 7 ayahs) and a tiny stand-in surah 2 (3 ayahs).
SURAHS = [
    (1, "الفاتحة", "Al-Fatihah", "makkah", 7),
    (2, "البقرة", "Al-Baqarah", "madinah", 3),
]
AYAT = {
    (1, 1): "بِسْمِ اللَّهِ الرَّحْمَٰنِ الرَّحِيمِ",
    (1, 2): "الْحَمْدُ لِلَّهِ رَبِّ الْعَالَمِينَ",
    (1, 3): "الرَّحْمَٰنِ الرَّحِيمِ",
    (1, 4): "مَالِكِ يَوْمِ الدِّينِ",
    (1, 5): "إِيَّاكَ نَعْبُدُ وَإِيَّاكَ نَسْتَعِينُ",
    (1, 6): "اهْدِنَا الصِّرَاطَ الْمُسْتَقِيمَ",
    (1, 7): "صِرَاطَ الَّذِينَ أَنْعَمْتَ عَلَيْهِمْ",
    (2, 1): "الم",
    (2, 2): "ذَٰلِكَ الْكِتَابُ لَا رَيْبَ فِيهِ",
    (2, 3): "الَّذِينَ يُؤْمِنُونَ بِالْغَيْبِ",
}


def fresh(name):
    p = FX / name
    if p.exists():
        p.unlink()
    return sqlite3.connect(p), p


def make_surahs():
    conn, _ = fresh("surah-names.sqlite")
    conn.execute("CREATE TABLE chapters(id INT, name_arabic TEXT, name_simple TEXT, revelation_place TEXT, verses_count INT)")
    conn.executemany("INSERT INTO chapters VALUES (?,?,?,?,?)", SURAHS)
    conn.commit(); conn.close()


def make_arabic_words():
    # word-by-word `words` table, like a QUL script export
    conn, _ = fresh("quran-uthmani.sqlite")
    conn.execute("CREATE TABLE words(word_index INT, word_key TEXT, surah INT, ayah INT, text TEXT)")
    wi = 1
    rows = []
    for (s, a), text in sorted(AYAT.items()):
        for w in text.split(" "):
            rows.append((wi, f"{s}:{a}", s, a, w)); wi += 1
    conn.executemany("INSERT INTO words VALUES (?,?,?,?,?)", rows)
    conn.commit(); conn.close()


def make_metadata():
    conn, _ = fresh("quran-metadata.sqlite")
    conn.execute("CREATE TABLE ayah_meta(surah INT, ayah INT, page INT, juz INT, hizb INT, rub INT, ruku INT, sajda INT)")
    rows = []
    for (s, a) in sorted(AYAT.keys()):
        page = 1 if s == 1 else 2
        rows.append((s, a, page, 1, 1, 1, 1 if s == 1 else 2, 0))
    conn.executemany("INSERT INTO ayah_meta VALUES (?,?,?,?,?,?,?,?)", rows)
    conn.commit(); conn.close()


def make_urdu():
    conn, _ = fresh("translation-urdu.sqlite")
    conn.execute("CREATE TABLE translations(surah INT, ayah INT, text TEXT)")
    rows = [(s, a, f"اردو ترجمہ {s}:{a}") for (s, a) in sorted(AYAT.keys())]
    conn.executemany("INSERT INTO translations VALUES (?,?,?)", rows)
    conn.commit(); conn.close()


def make_hindi():
    # verse_key style, like some QUL exports
    conn, _ = fresh("translation-hindi.sqlite")
    conn.execute("CREATE TABLE verses(verse_key TEXT, text TEXT)")
    rows = [(f"{s}:{a}", f"हिंदी अनुवाद {s}:{a}") for (s, a) in sorted(AYAT.keys())]
    conn.executemany("INSERT INTO verses VALUES (?,?)", rows)
    conn.commit(); conn.close()


def make_config():
    (FX / "sources.yaml").write_text(f"""output: {FX}/quran.test.db
db_version: "0.0.1-test"
schema_version: "1"
sources:
  surahs:
    file: {FX}/surah-names.sqlite
  arabic_uthmani:
    file: {FX}/quran-uthmani.sqlite
  metadata:
    file: {FX}/quran-metadata.sqlite
    mode: per_ayah
  translations:
    - file: {FX}/translation-urdu.sqlite
      language_code: ur
      name: "Test Urdu"
    - file: {FX}/translation-hindi.sqlite
      language_code: hi
      name: "Test Hindi"
""", encoding="utf-8")


if __name__ == "__main__":
    make_surahs(); make_arabic_words(); make_metadata(); make_urdu(); make_hindi(); make_config()
    print(f"fixtures written to {FX}")
