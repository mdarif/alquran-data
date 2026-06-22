# Al Quran — Data Pipeline

Compiles the **bundled SQLite seed database** for the Al Quran Flutter
app from [QUL (Quranic Universal Library)](https://qul.tarteel.ai) source files.

This is the *data* repo (the Python compilation pipeline). The Flutter app
reads the resulting `quran.db` as a bundled, fully-offline asset.

Implements PRD **v1.1.1**, Section 5.1 (schema), Section 6 (QUL sourcing),
Section 11 (this pipeline). MVP scope: **Uthmani/Madani Arabic + Urdu + Hindi**,
with Page / Juz / Hizb / Rub / Ruku / Sajda navigation indices.

---

## What it does

1. Reads QUL source files (SQLite/JSON) declared in `config/sources.yaml`.
2. **Auto-detects** each source's columns (tolerates package-to-package naming
   differences), so you rarely need manual overrides.
3. Aggregates word-by-word scripts into ayah text *or* uses ayah-level text directly.
4. Builds one normalized `quran.db` matching `pipeline/schema.sql`.
5. Records a **SHA-256 of every input** in the `db_meta` table (PRD Risk #1 integrity gate).

## Repo layout

```
pipeline/
  schema.sql        target app schema (surahs, ayahs, resources, translations)
  build_db.py       the compiler
  verify_db.py      post-build sanity checks (114 surahs / 6236 ayahs / coverage)
config/
  sources.example.yaml   copy to sources.yaml and edit
sources/            put downloaded QUL files here (git-ignored)
assets/             build output: quran.db (git-ignored)
tests/
  make_fixtures.py  generates tiny synthetic sources for a smoke test
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate   # optional
pip install -r requirements.txt
```

## Download the QUL sources

From https://qul.tarteel.ai, download the **SQLite** export of each, into `./sources/`:

| Resource | QUL category | MVP choice |
|---|---|---|
| Arabic Uthmani script | Quran Script | KFGQPC Hafs / Uthmani |
| Urdu translation | Translations | Maulana Muhammad Junagarhi |
| Surah names | Quran Metadata | Surah names dataset |
| Structural metadata | Quran Metadata | juz / hizb / rub / page / ruku / sajda |

> **License note:** before release, open each resource's QUL page, confirm its
> license permits store distribution, and record it in the `license:` field of
> `config/sources.yaml`. It flows into the `resources.license` column.

### Hindi translation (not on QUL)

The bundled Hindi is **Suhel Farooq Khan & Saifur Rahman Nadwi** (Tanzil edition
`hi.hindi`), which QUL does not carry. Regenerate its source DB from the AlQuran
Cloud API (mirrors Tanzil verbatim) — it's git-ignored like the QUL sources:

```bash
python pipeline/build_hindi_source.py   # -> sources/hi-suhel-farooq-nadwi-simple.db
```

## Build

```bash
cp config/sources.example.yaml config/sources.yaml
# edit config/sources.yaml to match your downloaded filenames
python pipeline/build_db.py --config config/sources.yaml
python pipeline/verify_db.py --db assets/quran.db
```

`assets/quran.db` is the file the Flutter app bundles.

## Smoke test (no downloads needed)

```bash
python tests/make_fixtures.py
python pipeline/build_db.py --config tests/fixtures/sources.yaml
```

## Structural metadata: two modes

`config/sources.yaml -> sources.metadata.mode`:

- `per_ayah` — the source already has one row per ayah with page/juz/hizb/… columns.
- `markers` — a JSON file of *start markers* per dimension (e.g. 30 juz starts,
  604 page starts, sajda ayahs). The pipeline expands markers into per-ayah numbers.

## Push to GitHub

Create an **empty** repo on GitHub (no README/license), then:

```bash
git remote add origin git@github.com:<you>/alquran-data-pipeline.git
git branch -M main
git push -u origin main
```

(The initial commit is already made for you.)
