# HANDOFF — alquran-data

This file is the briefing for an agent (Claude Cowork or Claude Code) picking up
this project locally. Read it fully, then continue from **Next Steps**.

## What this project is

`alquran-data` is the **data-compilation pipeline** for the AlMarfa360 Quran
Flutter app (parent firm: Al Marfa Technologies, almarfa.co). It turns
[QUL — Quranic Universal Library](https://qul.tarteel.ai) source files into a
single bundled, offline SQLite database (`assets/quran.db`) that the Flutter app
ships as an asset.

Full product spec: "AlMarfa360 Quran Mobile App — Master PRD v1.1.1" (in the
owner's Google Drive). This repo implements PRD Section 5.1 (schema), Section 6
(QUL sourcing), and Section 11 (this pipeline).

## Repo conventions

- All repos live under `/Users/mohammadarif/code/`.
- This repo: `/Users/mohammadarif/code/alquran-data`.
- The Flutter app (not built yet) will be `/Users/mohammadarif/code/alquran-app`.

## MVP scope (decided — do not expand without owner sign-off)

- Arabic script: **Uthmani/Madani only** (KFGQPC Hafs primary, Kitab alternate).
  IndoPak/Asian script is a deferred Phase-2 beta.
- Translations: **Urdu (Junagarhi) + Hindi (Farooq Khan/Ahmed) only.**
  English (Sahih International) and Roman Urdu are deferred.
- Navigation views: **Surah, Page, Juz, Hizb, Ruku** (Rub-al-Hizb + Sajda stored too).
- **Pinch-to-zoom is a hard accessibility requirement** (low-vision users).
- Deferred to backlog: audio recitation, bookmarks, last-read, dark mode, tajweed,
  full-text search, tafsir, word-by-word, exact-Mushaf page rendering.

## Current status

- Pipeline is written, smoke-tested, and now **run end-to-end on real QUL data**.
- **Real QUL sources downloaded** (2026-06-19, into `sources/`, git-ignored) and
  the bundled `assets/quran.db` builds and verifies clean: 114 surahs / 6236
  ayahs, Urdu + Hindi both complete, and page/juz/hizb/rub/ruku all fully
  populated (page 1–604, juz 1–30, hizb 1–60, rub 1–240, ruku 1–558, 15 sajdas).
  Spot-checked: Ayatul Kursi (2:255) → page 42, Juz 2 → 2:142, 2:1 = الٓمٓ.
- SHA-256 of every input is recorded in the DB `db_meta` table (PRD Risk #1).

### What changed during the real build (read this)

- **Hindi translation substituted.** The PRD's named Hindi (Farooq Khan / Ahmed)
  is **not in QUL's current catalog**. Used **Maulana Azizul Haque al-Umari**
  (`/resources/translation/166`, simple.sqlite) instead — the ayah-by-ayah Hindi
  option on QUL. Revisit if the owner wants a specific Hindi edition.
- **QUL requires sign-in to download.** All resource downloads 302 to a login
  modal until you are authenticated on qul.tarteel.ai.
- **The raw QUL shapes don't map 1:1 onto build_db.py**, so a preprocessing step
  was added — `pipeline/prepare_sources.py`. It produces two derived inputs:
  - `sources/arabic-ayah.sqlite` — ayah text aggregated from the KFGQPC Hafs
    **word-by-word** export (`/quran-script/312`).
  - `sources/structure.sqlite` — per-ayah page/juz/hizb/rub/ruku/sajda.
- **Page data needed a separate Mushaf layout.** There is **no page table in
  quran-metadata** and the word-by-word script carries no page column. Page
  numbers come from the **KFGQPC V2 (1421H) 604-page layout**
  (`/resources/mushaf-layout/10`), mapping its line word-id ranges to ayahs.
- The structural OPEN ITEM below is therefore **resolved as `per_ayah`** (the
  derived `structure.sqlite`), built from QUL's marker tables + the layout.

### Raw files in `sources/` (the real QUL pull)

| Role | QUL resource | File |
|---|---|---|
| Arabic (word-by-word) | quran-script/312 | qpc-hafs-word-by-word.db |
| Page layout (604pp) | mushaf-layout/10 | qpc-v2-15-lines.db |
| Urdu (Junagarhi) | translation/305 | ur-junagarri-simple.db |
| Hindi (al-Umari) | translation/166 | maulana-azizul-haque-al-umari-simple.db |
| Surah names | quran-metadata/70 | quran-metadata-surah-name.sqlite |
| Juz / Hizb / Rub / Ruku / Sajda | quran-metadata/68,67,63,65,64 | quran-metadata-*.sqlite |

Derived (built by `prepare_sources.py`): `arabic-ayah.sqlite`, `structure.sqlite`.

## Repo structure

```
pipeline/schema.sql        target schema (surahs, ayahs, resources, translations, db_meta)
pipeline/build_db.py       the compiler  (--config config/sources.yaml)
pipeline/verify_db.py      checks 114 surahs / 6236 ayahs / coverage / index ranges
config/sources.example.yaml  copy to config/sources.yaml and edit
sources/                   put downloaded QUL files here (git-ignored)
assets/                    build output quran.db lands here (git-ignored)
tests/make_fixtures.py     synthetic smoke test
```

## How to build

Smoke test (no downloads needed — verify the toolchain works):
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python tests/make_fixtures.py
python pipeline/build_db.py --config tests/fixtures/sources.yaml
```

Real build (config/sources.yaml is already filled in for the real QUL files):
```bash
python pipeline/prepare_sources.py            # raw QUL -> arabic-ayah + structure
python pipeline/build_db.py --config config/sources.yaml
python pipeline/verify_db.py --db assets/quran.db
```
> Run on a normal local disk. On a network/synced mount (e.g. Drive/iCloud)
> SQLite writes fail with `disk I/O error`; build elsewhere and copy the result.

## QUL sources to download (SQLite exports) into ./sources/

| Role           | QUL category   | Choose                                   |
|----------------|----------------|------------------------------------------|
| Arabic Uthmani | Quran Script   | KFGQPC Hafs / Uthmani                     |
| Urdu           | Translations   | Maulana Muhammad Junagarhi               |
| Hindi          | Translations   | Muhammad Farooq Khan / Muhammad Ahmed    |
| Surah names    | Quran Metadata | Surah names dataset                      |
| Structural     | Quran Metadata | juz / hizb / rub / page / ruku / sajda   |

Links: https://qul.tarteel.ai/resources/quran-script ,
https://qul.tarteel.ai/resources/translation ,
https://qul.tarteel.ai/resources/quran-metadata

## OPEN ITEM — RESOLVED

The structural-metadata ingestion question is settled: `prepare_sources.py`
combines QUL's marker tables (juz/hizb/rub/ruku) + sajda list + the 604-page
Mushaf layout into a single per-ayah `structure.sqlite`, consumed in `per_ayah`
mode. `verify_db.py` confirms all indices populated and in range.

## Licensing (must clear before any public release) — STILL OPEN

Checked QUL (2026-06-19): **QUL does not publish a per-resource license.** Its
FAQ (#3, #9) says copyright "varies" and defers to each resource's author/source;
resource pages show no license field. So licensing can't be cleared from QUL
alone — it needs real diligence per source:
- **Arabic script + 604-page layout** → King Fahd Quran Printing Complex
  (per QUL Credits). Confirm KFGQPC usage/redistribution terms.
- **Urdu (Junagarhi)** and **Hindi (al-Umari)** → confirm redistribution rights
  with the translation owner / originating platform (Tanzil/Quran.com lineage).

`config/sources.yaml` license fields are marked `UNVERIFIED` deliberately — they
are placeholders, not legal clearance. (This is a legal task for the owner; the
above is research, not legal advice.)

## Next Steps (in order)

1. ~~Smoke test.~~ ✅ done.
2. ~~Download the QUL SQLite files into `sources/`.~~ ✅ done (10 files).
3. ~~Fill in `config/sources.yaml` + set metadata mode.~~ ✅ done (`per_ayah`,
   via `prepare_sources.py`).
4. ~~Build `assets/quran.db`.~~ ✅ done.
5. ~~Verify.~~ ✅ done — clean.
6. **Clear licensing** (see section above) before any public release. OPEN.
7. **Push to GitHub** — create an empty repo named `alquran-data`, then
   `git remote add origin …`, `git branch -M main`, `git push -u origin main`.
8. **Decide on the QPC end-of-ayah number glyph** in the Arabic text (kept as-is
   now, e.g. the `١` after 1:1). Strip it in `prepare_sources.py` if unwanted.
9. Revisit the **Hindi edition** choice (al-Umari substituted — see above).
10. Hand back to the owner; next project is the Flutter app (`alquran-app`).
```