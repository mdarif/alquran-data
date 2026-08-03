-- Al Quran — bundled seed database schema
-- Matches PRD v1.1.1, Section 5.1 (MVP). Word-by-word / page-layout tables are
-- intentionally deferred (Section 5.2) and not created here for the MVP build.

-- 1024-byte pages: Quran rows are short; smaller pages reduce I/O and compress
-- better inside the APK. Must be set before any table is created.
PRAGMA page_size = 1024;
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
--
-- `slug` is the STABLE identity of an edition and the only safe thing for a
-- consumer to persist. `id` is NOT stable: build_db.py assigns it from
-- cur.lastrowid, so it follows insertion order in config/sources.yaml and every
-- id shifts when an edition is added or reordered. A saved preference or a
-- download filename keyed on id silently points at the wrong edition after the
-- next build; keyed on slug it survives.
--
-- `language_code` is a GROUPING field only. Several editions may share one
-- language (two Hindi translations, say) — consumers must never assume one row
-- per language.
CREATE TABLE IF NOT EXISTS resources (
    id            INTEGER PRIMARY KEY,
    slug          TEXT NOT NULL UNIQUE,           -- stable id, e.g. "ur-junagarhi"
    type          TEXT NOT NULL,                  -- "translation" | "tafsir" | "transliteration"
    language_code TEXT NOT NULL,                  -- ISO-639, e.g. "ur", "hi"
    name          TEXT NOT NULL,                  -- edition name, e.g. "Ahsanul Kalam"
    native_name   TEXT,                           -- selector label in its own script: हिन्दी, اردو
    author        TEXT,
    direction     TEXT,                           -- "rtl" | "ltr"; drives layout without a hardcoded lang list
    sort_order    INTEGER NOT NULL DEFAULT 0,     -- display order within a language group
    default_on    INTEGER NOT NULL DEFAULT 0,     -- 1 = shown by default to a new reader
    enabled       INTEGER NOT NULL DEFAULT 1,     -- 0 = kill switch: excluded from
                                                   -- dist/editions + catalogue.json
                                                   -- entirely (build_editions.py).
                                                   -- Still built into quran.db, so
                                                   -- re-enabling needs no re-import.
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

-- Manually verified local moon-sighting corrections for the Hijri date the app
-- displays, keyed by the Gregorian date FROM WHICH the correction applies
-- (until superseded by a later anchor for the same region). Replaces a pure
-- tabular (Kuwaiti) calendar, which is astronomically calculated and drifts
-- from the region's actual sighting-based announcement by a variable (not
-- constant) number of days. See config/hijri_anchors.yaml for the source data
-- and Al Quran's lib/core/hijri/ for the app-side consumer.
CREATE TABLE IF NOT EXISTS hijri_anchor_points (
    gregorian_date   TEXT    NOT NULL,   -- 'YYYY-MM-DD', from-date (inclusive)
    region           TEXT    NOT NULL,   -- e.g. 'PK', 'IN' — sighting authority
    correction_days  INTEGER NOT NULL,   -- applied to the tabular result
    source           TEXT,               -- e.g. 'Ruet-e-Hilal Committee PK'
    PRIMARY KEY (gregorian_date, region)
);

-- Navigation indices: every dimension the dashboard browses by must be fast.
CREATE INDEX IF NOT EXISTS idx_ayahs_surah  ON ayahs(surah_id);
CREATE INDEX IF NOT EXISTS idx_ayahs_page   ON ayahs(page_number);
CREATE INDEX IF NOT EXISTS idx_ayahs_juz    ON ayahs(juz_number);
CREATE INDEX IF NOT EXISTS idx_ayahs_hizb   ON ayahs(hizb_number);
CREATE INDEX IF NOT EXISTS idx_ayahs_rub    ON ayahs(rub_el_hizb);
CREATE INDEX IF NOT EXISTS idx_ayahs_ruku   ON ayahs(ruku_number);
-- Covers "load all translations for a given page/juz/etc" joins efficiently
CREATE INDEX IF NOT EXISTS idx_tr_resource_ayah ON translations(resource_id, ayah_id);
CREATE INDEX IF NOT EXISTS idx_tr_ayah      ON translations(ayah_id);
CREATE INDEX IF NOT EXISTS idx_tr_resource  ON translations(resource_id);
