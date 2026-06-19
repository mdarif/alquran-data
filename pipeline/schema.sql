-- AlMarfa360 Quran — bundled seed database schema
-- Matches PRD v1.1.1, Section 5.1 (MVP). Word-by-word / page-layout tables are
-- intentionally deferred (Section 5.2) and not created here for the MVP build.

PRAGMA foreign_keys = ON;

-- Key/value table for build metadata: schema version, build timestamp,
-- source file checksums (the SHA-256 integrity record from PRD Risk #1).
CREATE TABLE IF NOT EXISTS db_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS surahs (
    id               INTEGER PRIMARY KEY,        -- 1..114
    name_arabic      TEXT    NOT NULL,
    name_english     TEXT    NOT NULL,           -- transliterated name, e.g. "Al-Fatihah"
    revelation_place TEXT,                       -- "makkah" | "madinah" (nullable if source lacks it)
    total_ayahs      INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS ayahs (
    id                  INTEGER PRIMARY KEY,      -- global running ayah id (1..6236)
    surah_id            INTEGER NOT NULL REFERENCES surahs(id),
    ayah_number         INTEGER NOT NULL,         -- ayah number within the surah
    text_arabic_uthmani TEXT    NOT NULL,
    -- Reserved for the Phase 2 IndoPak beta; left NULL by the MVP build.
    text_arabic_indopak TEXT,
    -- Structural navigation indices (PRD Section 4.2).
    page_number         INTEGER,
    juz_number          INTEGER,
    hizb_number         INTEGER,
    rub_el_hizb         INTEGER,
    ruku_number         INTEGER,
    sajda               INTEGER NOT NULL DEFAULT 0, -- 0 = none, 1 = sajda ayah
    UNIQUE (surah_id, ayah_number)
);

-- A registry of every text resource (translation now; tafsir/transliteration later).
CREATE TABLE IF NOT EXISTS resources (
    id            INTEGER PRIMARY KEY,
    type          TEXT NOT NULL,                  -- "translation" | "tafsir" | "transliteration"
    language_code TEXT NOT NULL,                  -- ISO-639, e.g. "ur", "hi"
    name          TEXT NOT NULL,
    author        TEXT,
    license       TEXT,                           -- record the QUL/source license here
    source_url    TEXT
);

CREATE TABLE IF NOT EXISTS translations (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ayah_id      INTEGER NOT NULL REFERENCES ayahs(id),
    resource_id  INTEGER NOT NULL REFERENCES resources(id),
    text_content TEXT NOT NULL,
    UNIQUE (ayah_id, resource_id)
);

-- Navigation indices: every dimension the dashboard browses by must be fast.
CREATE INDEX IF NOT EXISTS idx_ayahs_surah  ON ayahs(surah_id);
CREATE INDEX IF NOT EXISTS idx_ayahs_page   ON ayahs(page_number);
CREATE INDEX IF NOT EXISTS idx_ayahs_juz    ON ayahs(juz_number);
CREATE INDEX IF NOT EXISTS idx_ayahs_hizb   ON ayahs(hizb_number);
CREATE INDEX IF NOT EXISTS idx_ayahs_ruku   ON ayahs(ruku_number);
CREATE INDEX IF NOT EXISTS idx_tr_ayah      ON translations(ayah_id);
CREATE INDEX IF NOT EXISTS idx_tr_resource  ON translations(resource_id);
