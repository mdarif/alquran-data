# AGENTS.md — Al Quran data pipeline (`alquran-data`)

Context for Codex in this repo. **Read `HANDOFF.md` first** — it has the
full briefing, decisions, and step-by-step status. This file is the short version.

## What this is

The Python pipeline that compiles the bundled, offline **`assets/quran.db`** seed
database for the **Al Quran** Flutter app (`../alquran-app`) from
[QUL](https://qul.tarteel.ai) sources. Implements PRD v1.1.1 §5.1 / §6 / §11.
(The product is "Al Quran" — older text said "AlMarfa360 Quran"; that name is wrong.)

GitHub: https://github.com/mdarif/alquran-data (owner: mdarif / Mohammad Arif,
sole contributor).

## Pipeline

```
pipeline/prepare_sources.py   raw QUL files  -> arabic-ayah.sqlite + structure.sqlite
pipeline/build_db.py          --config config/sources.yaml -> assets/quran.db
pipeline/verify_db.py         --db assets/quran.db  (114 surahs / 6236 ayahs / index coverage)
pipeline/build_editions.py    --db assets/quran.db --out dist/editions  (per-edition .db.gz + catalogue.json for R2)
```

Build (use a normal local disk — SQLite writes fail on network/synced mounts):
```bash
pip install -r requirements.txt
python pipeline/prepare_sources.py
python pipeline/build_db.py --config config/sources.yaml
python pipeline/verify_db.py --db assets/quran.db
python pipeline/build_editions.py --db assets/quran.db --out dist/editions   # only when publishing downloads
```

Smoke test (no downloads): `python tests/make_fixtures.py && python pipeline/build_db.py --config tests/fixtures/sources.yaml`.

## Sources (real QUL pull, in `sources/`, git-ignored)

Arabic KFGQPC Hafs word-by-word (#312) · QPC V2 604-page layout (#10, for page
numbers) · Urdu Junagarhi (#305) · Hindi al-Umari (#166, substituted for the
PRD's unavailable Farooq Khan/Ahmed) · surah names + juz/hizb/rub/ruku/sajda
metadata. `prepare_sources.py` aggregates words→ayahs and derives per-ayah
page/juz/hizb/rub/ruku/sajda (`per_ayah` mode).

## State & open items

- **Editions carry a stable `slug`** (schema_version 2). Consumers select and
  persist on slug — **never** on `resources.id`, which comes from `cur.lastrowid`
  and shifts whenever `config/sources.yaml` is reordered. `language_code` groups
  only: several editions per language is now a supported state. Selector metadata
  (`native_name`, `direction`, `sort_order`, `default_on`) lives in the DB so no
  consumer needs a hardcoded language list. Full rationale + the Ahsanul Kalam
  candidate: **`TRANSLATIONS-ROADMAP.md`**.

- **Done:** real data downloaded, `quran.db` builds + verifies clean, pushed to GitHub.
- **Licensing — RESOLVED for the MVP** (2026-06-20; see `ATTRIBUTION.md`). App
  ships **free / non-commercial (da'wah)**, MVP is **Urdu (Junagarhi) only**.
  Junagarhi cleared under Tanzil's non-commercial-with-attribution terms (ship
  verbatim; credit translator + Tanzil w/ link). Arabic = KFGQPC (credit; font
  is an app-side obligation). Hindi (al-Umari) **deferred** — already permissive
  via QuranEnc.com, commented out in `config/sources.yaml`.
  - **Still open:** confirm KFGQPC V2 604-page *layout* redistribution terms;
    pick a pipeline-code license. **Re-clear Junagarhi if the app is ever
    monetized** (Tanzil terms are non-commercial only).
  - **Action:** the bundled DB still contains Hindi — rebuild from the updated
    config to ship Urdu-only.
- **Decision pending — ayah-number glyph:** Arabic text keeps QPC's end-of-ayah
  number (e.g. `١`). Strip it in `prepare_sources.py` if unwanted.
- **Note:** downloading QUL files requires being signed in at qul.tarteel.ai.

## Gotcha

`sources/`, `assets/*.db`, and `config/sources.yaml` are git-ignored (`config/sources.yaml`
was force-added so the real config is tracked). Don't commit the large data files.
