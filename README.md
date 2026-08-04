# Al Quran — Data Pipeline

Compiles the **bundled SQLite seed database** (`assets/quran.db`) and the
**downloadable translation editions** (`dist/editions/`, published to
Cloudflare R2) for the **Al Quran** apps from
[QUL (Quranic Universal Library)](https://qul.tarteel.ai) and a few
non-QUL sources.

This is the *data* repo (the Python compilation pipeline). `../alquran-app`
(Flutter) bundles `quran.db` as a fully-offline asset and downloads
additional editions at runtime; `../al-quran-web` bundles the same
`quran.db`. Implements PRD v1.1.1, Section 5.1 (schema), Section 6 (QUL
sourcing), Section 11 (this pipeline).

For full context, decisions, and current state, **read `HANDOFF.md` first**
— this file is the short version. `AGENTS.md`/`CLAUDE.md` are the same short
version, written for coding agents.

GitHub: https://github.com/mdarif/alquran-data (owner: mdarif / Mohammad Arif).

---

## What it does

1. Reads QUL source files (SQLite/JSON) declared in `config/sources.yaml`,
   plus a handful of non-QUL sources with their own importers (Hindi, Roman
   Urdu, IndoPak — see below).
2. **Auto-detects** each source's columns (tolerates package-to-package naming
   differences), so you rarely need manual overrides.
3. Aggregates word-by-word scripts into ayah text *or* uses ayah-level text
   directly.
4. Builds one normalized `quran.db` matching `pipeline/schema.sql`.
5. Records a **SHA-256 of every input** in the `db_meta` table (PRD Risk #1
   integrity gate).
6. Optionally packages every translation/transliteration as a standalone
   `.db.gz` + `catalogue.json` for download-on-demand distribution
   (`build_editions.py` → `publish_editions.sh`).

## Repo layout

```
pipeline/
  schema.sql            target app schema (surahs, ayahs, resources, translations)
  prepare_sources.py    raw QUL files -> arabic-ayah.sqlite + structure.sqlite
  build_db.py           the compiler: config/sources.yaml -> assets/quran.db
  verify_db.py          post-build sanity checks (114 surahs / 6236 ayahs / coverage)
  build_hindi_source.py Hindi (Suhel Farooq Khan/Nadwi) via the AlQuran Cloud API (not on QUL)
  build_indopak_source.py  Arabic IndoPak script, normalised for the Noorehuda font
  ahsanul_kalam/         importer for the Ahsanul Kalam Hindi OCR pilot
  roman_urdu/             importer for the Al Marfa (Abu Rayyan) Roman Urdu edition
  build_editions.py     assets/quran.db -> dist/editions (.db.gz per edition + catalogue.json)
  publish_editions.sh   uploads dist/editions -> Cloudflare R2 (al-quran-editions bucket)
  verify_editions.py    checks the LIVE published editions match their catalogue digests
config/
  sources.example.yaml   copy to sources.yaml and edit
  sources.yaml            the real, tracked config (force-added; see Gotcha below)
sources/            downloaded/generated source files (git-ignored)
assets/             build output: quran.db (git-ignored)
dist/editions/      build output: per-edition .db.gz + catalogue.json (git-ignored)
tests/
  make_fixtures.py  generates tiny synthetic sources for a smoke test, incl. a
                     transliteration-type edition and a disabled (kill-switch) edition
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate   # optional
pip install -r requirements.txt
```

Build on a normal local disk — SQLite writes fail on network/synced mounts
(iCloud Drive, some NAS mounts).

## Download the QUL sources

From https://qul.tarteel.ai (requires being signed in), download the
**SQLite** export of each resource into `./sources/`. Current picks (see
`config/sources.yaml` for the full, current list — it has grown well past
the MVP set below and is the source of truth):

| Resource | QUL category | Current choice |
|---|---|---|
| Arabic Uthmani script | Quran Script | quran.com golden text (`quran.ar.uthmani.v2.db`), kashida-grafted from Tanzil |
| Arabic IndoPak script | Quran Script | quran.com IndoPak text, normalised for Noorehuda |
| Page layout | Quran Metadata | QPC V2 604-page layout (for page numbers) |
| Urdu translation | Translations | Maulana Muhammad Junagarhi (#305) |
| English translations | Translations | Sahih International (#193), Hilali & Khan (#301) |
| Bengali / Indonesian / Swahili | Translations | see `config/sources.yaml` for QUL resource IDs |
| Surah names + structural metadata | Quran Metadata | surah names, juz/hizb/rub/ruku/sajda markers |

> **License note:** before release, open each resource's QUL page, confirm its
> license permits store distribution, and record it in the `license:` field of
> `config/sources.yaml`. It flows into the `resources.license` column.
> `ATTRIBUTION.md` is the canonical, per-edition licensing record — keep it in
> sync with any config change.

### Sources not on QUL

A few editions are sourced outside QUL, each with its own importer:

- **Hindi (Suhel Farooq Khan & Saifur Rahman Nadwi)** — Tanzil edition
  `hi.hindi`, mirrored via the AlQuran Cloud API:
  ```bash
  python pipeline/build_hindi_source.py   # -> sources/hi-suhel-farooq-nadwi-simple.db
  ```
- **Hindi (Ahsanul Kalam)** — reviewed OCR pilot of a print-only translation:
  ```bash
  python pipeline/ahsanul_kalam/export_simple_db.py   # -> sources/hi-ahsanul-kalam-simple.db
  ```
- **Roman Urdu (Al Marfa / Abu Rayyan)** — transliterated in
  `../alquran-roman-urdu`:
  ```bash
  python pipeline/roman_urdu/export_simple_db.py   # -> sources/ur-roman-abu-rayyan-simple.db
  ```
- **Arabic IndoPak** — normalises the quran.com IndoPak export for the
  Noorehuda font (PUA marks -> Unicode, IndoPak-only waqf symbols stripped):
  ```bash
  python pipeline/build_indopak_source.py   # -> sources/arabic-indopak-quran-com.db
  ```

## Build

```bash
cp config/sources.example.yaml config/sources.yaml   # or use the real, tracked config
# edit config/sources.yaml to match your downloaded filenames

python pipeline/prepare_sources.py                    # -> arabic-ayah.sqlite, structure.sqlite
python pipeline/build_db.py --config config/sources.yaml
python pipeline/verify_db.py --db assets/quran.db
```

`assets/quran.db` is the file the Flutter app and web app bundle.

### Publishing downloadable editions

Only needed when a translation/transliteration edition changed and needs to
reach existing installs without an app-store release:

```bash
python pipeline/build_editions.py --db assets/quran.db --out dist/editions
pipeline/publish_editions.sh
python pipeline/verify_editions.py
```

Read the "Editions on R2" section of `AGENTS.md`/`CLAUDE.md` before running
this — there are four traps that fail *quietly* (wrong `--remote` flag,
`Content-Encoding: gzip`, non-content-addressed filenames, non-deterministic
build output). All four are enforced by `verify_editions.py` and the smoke
test, but read the reasoning before changing the publish script.

## Smoke test (no downloads needed)

```bash
python tests/make_fixtures.py
python pipeline/build_db.py --config tests/fixtures/sources.yaml
```

## Adding a new translation/transliteration edition

1. Get the source file into `sources/` — either a QUL SQLite export, or run
   the matching importer above for a non-QUL source.
2. Add a block under `translations:` in `config/sources.yaml`: pick a
   **stable `slug`** (never reuse or rename one that's shipped — it's the
   key consumers persist), `language_code`, `name`/`native_name`/`direction`,
   `sort_order` (leave gaps), `default_on` (almost always `false` for a new
   edition), `enabled: true`, `license`, `source_url`. Set `experimental:
   true` if the content hasn't been through full manual review yet, and
   `credit_name` only if `author` is a long multi-person licensing credit.
3. Rebuild: `build_db.py` → `verify_db.py` (confirms 114/6236 coverage for
   the new edition too).
4. Record the edition in `ATTRIBUTION.md` (licensing is the canonical
   clearance record) and, if it started life as a roadmap candidate, update
   its status in `TRANSLATIONS-ROADMAP.md`.
5. If it should reach existing installs without an app release: `build_editions.py`
   → `publish_editions.sh` → `verify_editions.py`.
6. To pull an edition back out without an app release (bad data, licensing
   issue), set `enabled: false` and republish — see the "Kill switch"
   paragraph in `AGENTS.md`/`CLAUDE.md`. It stays built into `quran.db` for
   reproducibility but disappears from `catalogue.json`.

## Structural metadata: two modes

`config/sources.yaml -> sources.metadata.mode`:

- `per_ayah` — the source already has one row per ayah with page/juz/hizb/… columns.
- `markers` — a JSON file of *start markers* per dimension (e.g. 30 juz starts,
  604 page starts, sajda ayahs). The pipeline expands markers into per-ayah numbers.

## Related docs in this repo

- `HANDOFF.md` — full session history, current state, "read this first."
- `AGENTS.md` / `CLAUDE.md` — short briefing for coding agents (same content).
- `TRANSLATIONS-ROADMAP.md` — candidate editions, creed/licensing checks, status.
- `ATTRIBUTION.md` — canonical per-edition licensing/attribution record.
- `pipeline/schema.sql` — the target schema, with inline column-level comments.

## Push to GitHub

```bash
git remote add origin git@github.com:mdarif/alquran-data.git
git branch -M main
git push -u origin main
```
