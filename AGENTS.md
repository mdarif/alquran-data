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
pipeline/build_editions.py    --db assets/quran.db --out dist/editions  (per-edition .db.gz + catalogue.json)
pipeline/publish_editions.sh  upload dist/editions -> R2 bucket al-quran-editions
pipeline/verify_editions.py   check the LIVE published editions match their digests
```

Build (use a normal local disk — SQLite writes fail on network/synced mounts):
```bash
pip install -r requirements.txt
python pipeline/prepare_sources.py
python pipeline/build_db.py --config config/sources.yaml
python pipeline/verify_db.py --db assets/quran.db
python pipeline/build_editions.py --db assets/quran.db --out dist/editions   # only when publishing downloads
pipeline/publish_editions.sh                                                # then upload + verify
```

Smoke test (no downloads): `python tests/make_fixtures.py && python pipeline/build_db.py --config tests/fixtures/sources.yaml`.

## Sources (real QUL pull, in `sources/`, git-ignored)

Arabic KFGQPC Hafs word-by-word (#312) · QPC V2 604-page layout (#10, for page
numbers) · Urdu Junagarhi (#305) · Hindi Suhel Farooq Khan/Nadwi
(Tanzil `hi.hindi`, not on QUL — mirrored via the AlQuran Cloud API) · surah names + juz/hizb/rub/ruku/sajda
metadata. `prepare_sources.py` aggregates words→ayahs and derives per-ayah
page/juz/hizb/rub/ruku/sajda (`per_ayah` mode).

## Editions on R2 (downloadable translations)

Live at **https://editions.alquranreader.com** (bucket `al-quran-editions`,
APAC, custom domain on the `alquranreader.com` zone — same arrangement as
`al-quran-audio` → `audio.alquranreader.com`; the r2.dev URL stays disabled).

Publish with `pipeline/publish_editions.sh`, then `pipeline/verify_editions.py`.
Four traps, all of which fail quietly:

- **`--remote` is mandatory** on every `wrangler r2 object` command. Without it
  wrangler writes to a LOCAL simulated bucket and still prints "Upload
  complete". This happened on the first publish — the bucket read back empty
  while every upload had "succeeded".
- **Never set `Content-Encoding: gzip`.** The artifacts are gzip *files*, not
  gzip-encoded responses. Marking them encoded makes HTTP clients decompress
  transparently, so the bytes the app hashes stop matching the catalogue's
  `sha256` and every install is rejected as corrupt. `verify_editions.py`
  asserts the header is absent.
- **Artifacts are content-addressed** (`<slug>-<sha12>.db.gz`) and cached
  immutably; only `catalogue.json` gets a short TTL (300s). A stable filename
  behind a CDN would serve stale bytes after an edition is corrected, and the
  reader would see a checksum error that is really a cache.
- **Nothing per-build-run may go inside an artifact.** An embedded `built_at`
  timestamp churned all three digests on every rebuild (fixed 2026-07-28), so the
  app was told to re-download editions whose text never changed. Build time lives
  in the catalogue's `generatedAt`; gzip is written with `mtime=0`. Two builds of
  an unchanged DB must be byte-identical.

Upload artifacts first, catalogue last — the catalogue is what points at them.

## State & open items

- **Editions carry a stable `slug`** (schema_version 2). Consumers select and
  persist on slug — **never** on `resources.id`, which comes from `cur.lastrowid`
  and shifts whenever `config/sources.yaml` is reordered. `language_code` groups
  only: several editions per language is now a supported state. Selector metadata
  (`native_name`, `direction`, `sort_order`, `default_on`) lives in the DB so no
  consumer needs a hardcoded language list. Full rationale + the Ahsanul Kalam
  candidate: **`TRANSLATIONS-ROADMAP.md`**.

- **Done:** real data downloaded, `quran.db` builds + verifies clean, pushed to GitHub.
- **Licensing** (see `ATTRIBUTION.md` — canonical). App ships **free /
  non-commercial (da'wah)**. Shipping: Urdu (Junagarhi), Hindi (Suhel Farooq
  Khan/Nadwi), English (Hilali & Khan).
  - **Urdu (Junagarhi) = PUBLIC DOMAIN** (owner determination 2026-07-27).
    Translator d. 1941; life+60 clears it ~2001. Tanzil is a *redistributor*, not
    a rights holder — credited by courtesy. **No verbatim-only clause and no
    non-commercial restriction**, so derivatives (Roman Urdu, Devanagari) need no
    permission, and monetization needs no re-clearing.
  - Hindi (Tanzil `hi.hindi`) — non-commercial + attribution, **verbatim**; the
    Khuda→Allah adaptation was reverted 2026-07-27. Still needs re-clearing if
    monetized; no public-domain argument is available for it.
  - Arabic = KFGQPC (credit; font is an app-side obligation).
  - Hindi (al-Umari) — **REJECTED on register**, not deferred (Sanskritic; the
    product needs Perso-Arabic). See `TRANSLATIONS-ROADMAP.md`.
  - **Still open:** confirm KFGQPC V2 604-page *layout* redistribution terms;
    pick a pipeline-code license.
- **Decision pending — ayah-number glyph:** Arabic text keeps QPC's end-of-ayah
  number (e.g. `١`). Strip it in `prepare_sources.py` if unwanted.
- **Note:** downloading QUL files requires being signed in at qul.tarteel.ai.

## Gotcha

`sources/`, `assets/*.db`, and `config/sources.yaml` are git-ignored (`config/sources.yaml`
was force-added so the real config is tracked). Don't commit the large data files.
