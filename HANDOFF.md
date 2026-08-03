# HANDOFF — alquran-data

This file is the briefing for an agent (Claude Cowork or Claude Code) picking up
this project locally. Read it fully, then continue from **Next Steps**.

---

## SESSION HANDOFF — 2026-08-03: Roman Urdu ingested, kill switch built, nothing committed or published yet

**Read this block first if you're a fresh session.** Everything below it is
older context; this block is the current state and the concrete next actions.

### What happened this session

1. **Roman Urdu is now a real edition.** `../alquran-roman-urdu` reached full
   coverage (6,236/6,236 verses, all 114 surahs, transliterated by **Abu
   Rayyan** / Mohammad Arif). It's ingested here as `resources.slug =
   ur-roman-almarfa`, `type: transliteration`, via a new importer:
   `pipeline/roman_urdu/export_simple_db.py` (modeled on
   `pipeline/ahsanul_kalam/export_simple_db.py` — same "per-surah JSON with an
   `ayahs` dict" shape). It also refuses to ingest any verse containing a
   digit (the fused-footnote-marker defect class), as an extra safety net.
   Full detail + the exact credit strings: `TRANSLATIONS-ROADMAP.md`'s Roman
   Urdu entry and `ATTRIBUTION.md`'s Roman Urdu section — read those before
   touching this edition again, don't re-derive from scratch.
2. **The retired third-party Roman Urdu (`ur-roman-junagarhi-experimental`,
   Al-QuranJino/Muhammad Kazim) is now `enabled: false`** in
   `config/sources.yaml` — kept in the repo (do not delete it, do not "fix"
   its text) purely as a reproducible rejected-comparison artifact.
3. **Built a per-edition kill switch, end to end.** New `resources.enabled`
   column (`pipeline/schema.sql`), threaded through `build_db.py`'s insert +
   a new config validation check, and enforced in `build_editions.py`: any
   resource with `enabled: false` is skipped entirely — not built, not in
   `catalogue.json`. Confirmed this needs **zero app-side code changes** by
   reading `alquran-app/lib/features/translations/presentation/cubit/
   translations_cubit.dart` directly — it already iterates whatever
   `catalogue().editions` returns, no hardcoded slug allowlist. **Every
   edition in `config/sources.yaml` now has an explicit `enabled: true` or
   `enabled: false`** (11 lines — nothing relies on the column's implicit
   default anymore), so the config file alone answers "what's live."
4. **Rebuilt and verified locally, three times, after each round of changes:**
   `python3 pipeline/build_db.py --config config/sources.yaml` →
   `python3 pipeline/verify_db.py --db assets/quran.db` (clean, `OK`) →
   `python3 pipeline/build_editions.py --db assets/quran.db --out
   dist/editions`. Also re-ran the smoke test
   (`tests/make_fixtures.py` + `build_db.py --config
   tests/fixtures/sources.yaml`) after adding an `enabled: false` fixture
   case — passes, logs `[DISABLED — not published]` for it as expected.
5. **Updated four docs** that would otherwise be stale: `AGENTS.md` (new
   "Kill switch" paragraph under "Editions on R2"), `TRANSLATIONS-ROADMAP.md`
   (full rewrite of the Roman Urdu section — it previously said "325 of 6,236
   verses" and "not yet a DB resource"), `ATTRIBUTION.md` (same — previously
   headed "Roman Urdu (upcoming — not yet a resource in this repo)", and
   wrongly described it as a phonemic-store rendering, which is the
   *Devanagari* track's method, not this one), and this file's now-corrected
   "catalogue lists exactly the three bundled editions" claim further down
   (search for "Stale as of 2026-08-03").

### Exact current state — check this yourself, don't trust prose that ages

```bash
git status --short          # 9 modified + 1 new untracked dir (pipeline/roman_urdu/), NOTHING committed
git diff --stat              # ~235 insertions across config/sources.yaml, pipeline/*.py, pipeline/schema.sql, 4 docs, tests/make_fixtures.py
```

**Local** `dist/editions/catalogue.json`: 10 editions, includes
`ur-roman-almarfa` (428 KB gzipped). **Live** at
`https://editions.alquranreader.com/catalogue.json` (checked this session):
**9 editions, `generatedAt: 2026-07-30`, does NOT include Roman Urdu** —
publishing now would add exactly one new edition to what's already live,
nothing else changes. Note the other 9 apparently got published live at some
point after this file's stale "exactly three bundled editions" line was
written — don't trust that number either; always check the live URL directly.

`assets/quran.db` and `sources/ur-roman-almarfa-simple.db` are both
git-ignored, already built locally, present on disk — no re-run needed unless
you change something.

### What is NOT done — pick up here

1. **Nothing is committed.** There's also a **pre-existing uncommitted
   scaffolding diff from a session before this one** (the `type:
   transliteration` support in `build_db.py`/`build_editions.py`/
   `tests/make_fixtures.py`, and the original dormant
   `ur-roman-junagarhi-experimental` config block) that this session built on
   top of rather than committing separately — so whatever you commit will
   bundle both. One commit or several is your/the owner's call; nothing here
   demands a particular split.
2. **Nothing is published.** `pipeline/publish_editions.sh` then
   `pipeline/verify_editions.py` — not run this session. Read the "Editions on
   R2" section below first (four traps, all fail quietly — `--remote` is
   mandatory, never set `Content-Encoding: gzip`, artifacts before catalogue).
3. **`alquran-app` and `al-quran-web` were deliberately left untouched** —
   confirmed neither needs code changes for `ur-roman-almarfa` to appear
   (app: generic catalogue consumption, verified directly; web: has its own
   separate Roman Urdu overlay mechanism in `al-quran-web/scripts/
   export-quran.mjs`, not this pipeline, already pointed at the same
   `ur-roman-almarfa` slug and the same Abu Rayyan credit strings — nothing to
   reconcile). Re-verify this claim rather than assuming it still holds if
   time has passed and either repo has changed.
4. **Not decided:** whether/when `ur-roman-almarfa`'s `default_on` should ever
   flip to `true`. Currently `false` because every verse in
   `../alquran-roman-urdu` is still `status: beta-unverified` (nothing
   reviewed). That's a content-review decision belonging to the
   `alquran-roman-urdu` repo, not a pipeline one — don't flip it here without
   checking that repo's review state first.

---

## What this project is

`alquran-data` is the **data-compilation pipeline** for the Al Quran
Flutter app (parent firm: Al Marfa Technologies, almarfa.co). It turns
[QUL — Quranic Universal Library](https://qul.tarteel.ai) source files into a
single bundled, offline SQLite database (`assets/quran.db`) that the Flutter app
ships as an asset.

Full product spec: "Al Quran Mobile App — Master PRD v1.1.1" (in the
owner's Google Drive). This repo implements PRD Section 5.1 (schema), Section 6
(QUL sourcing), and Section 11 (this pipeline).

## Repo conventions

- All repos live under `/Users/mohammadarif/code/`.
- This repo: `/Users/mohammadarif/code/alquran-data`.
- The Flutter app (not built yet) will be `/Users/mohammadarif/code/alquran-app`.

## MVP scope (decided — do not expand without owner sign-off)

- Arabic script: **Uthmani/Madani only** (KFGQPC Hafs primary, Kitab alternate).
  IndoPak/Asian script is a deferred Phase-2 beta.
- Translations: **three editions ship bundled** — Urdu (Junagarhi), Hindi (Suhel
  Farooq Khan/Nadwi), English (Hilali & Khan). (The earlier "Urdu-only MVP, Hindi
  deferred" scope is superseded; see ATTRIBUTION.md §1.) Further
  translation candidates (e.g. a second English edition, Roman Urdu) are
  tracked in **`TRANSLATIONS-ROADMAP.md`**, not here — that file is the shared
  backlog both `alquran-app` and `al-quran-web` read from.
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
- **Edition model landed (2026-07-28, schema_version 2).** Every translation
  carries a stable `resources.slug` plus selector metadata (`native_name`,
  `direction`, `sort_order`, `default_on`). Consumers select and persist on
  **slug** — never on `resources.id`, which comes from `cur.lastrowid` and shifts
  whenever `config/sources.yaml` is reordered. `language_code` groups only:
  several editions per language is supported. Rationale: `TRANSLATIONS-ROADMAP.md`.
- **Downloadable editions are live on R2** at
  https://editions.alquranreader.com (bucket `al-quran-editions`, APAC, custom
  domain on the `alquranreader.com` zone; r2.dev disabled). Built by
  `build_editions.py` as content-addressed `<slug>-<sha12>.db.gz` + a
  short-TTL `catalogue.json`, published by `publish_editions.sh` (artifacts
  first, catalogue last), checked live by `verify_editions.py`. The publish
  traps — `--remote` is mandatory, never set `Content-Encoding: gzip` — are
  documented in `CLAUDE.md`; both fail silently.
- **Stale as of 2026-08-03 — do not trust this bullet's edition count.** The
  locally-built `dist/editions/catalogue.json` now lists **10** editions
  (Urdu, Hindi ×3, English ×2, Bengali, Indonesian, Swahili, and the new Roman
  Urdu `ur-roman-almarfa` — see `TRANSLATIONS-ROADMAP.md`'s Roman Urdu entry),
  not the "exactly three" this line used to claim. **Not yet republished to
  R2** as of this edit — `dist/editions/catalogue.json`'s `generatedAt` is the
  source of truth for what's actually live; check it, don't trust this prose.
  Run `pipeline/publish_editions.sh` + `pipeline/verify_editions.py` to bring
  the live catalogue in sync, then update this bullet.

### What changed during the real build (read this)

- **Hindi translation substituted.** The PRD's named Hindi (Farooq Khan / Ahmed)
  is **not in QUL's current catalog**. Used **Maulana Azizul Haque al-Umari**
  (`/resources/translation/166`, simple.sqlite) at first — the ayah-by-ayah Hindi
  option on QUL. **Superseded:** al-Umari was later rejected on register
  (Sanskritic, wrong for this product) and the shipping Hindi is Tanzil's
  `hi.hindi` (Suhel Farooq Khan / Nadwi), `slug: hi-suhel-farooq-nadwi`.
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
- **English text cleaned for display (2026-07-06, owner decision).** Two
  presentational normalizations applied to the Hilali-Khan **English** source
  only, via per-source flags in `config/sources.yaml` + helpers in `build_db.py`
  (run on insert; Urdu/Hindi untouched):
  1. `strip_translit_diacritics: true` → `normalize_translit()` flattens the
     circumflex long-vowel letters `â î û Â Î → a i u A I` (`Allâh→Allah`,
     `Muhâjirûn→Muhajirun`). A fixed 5-char map, **not** a Unicode strip —
     embedded Arabic (`ﷺ`, `صلى الله عليه وسلم`) and curly quotes survive.
  2. `collapse_nbsp: true` → `collapse_nbsp()` turns the edition's ~4300 no-break
     spaces (U+00A0, which it uses to glue transliterated terms like
     `Al-Ansar and Al-Muhajirun`) into regular spaces + squeezes runs. NBSP
     forbids line-wrapping, so it left ragged gaps in the narrow reader column.
  Both intentionally diverge from the edition's exact orthography (meaning
  unchanged); note beside the licensing item before release. The app and web both
  consume this rebuilt DB verbatim. Verify each rebuild changed **only** English
  (diff Arabic/ur/hi = 0 rows).

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

## Licensing — RESOLVED for the MVP (2026-06-20)

Decision: **Al Quran ships free / non-commercial (da'wah)**. Three editions ship:
Urdu (Junagarhi), Hindi (Suhel Farooq Khan/Nadwi), English (Hilali & Khan). Full
notice and required app credits: **`ATTRIBUTION.md`** (canonical — this section is
the summary).

- **Urdu (Junagarhi)** → **PUBLIC DOMAIN** (owner determination, 2026-07-27;
  supersedes the Tanzil-terms framing this section previously carried).
  Translator d. 1941; India/Pakistan life+60 clears it ~2001. Tanzil is a
  *redistributor*, not a rights holder — their non-commercial-with-attribution
  request cannot bind a public-domain work, so we credit them by courtesy.
  **No verbatim-only clause, no non-commercial restriction**, and derivative
  works (Roman Urdu, Devanagari — see `TRANSLATIONS-ROADMAP.md`) need no
  permission.
- **Arabic script (KFGQPC)** → verbatim Qur'an text, credit KFGQPC. The KFGQPC
  HAFS **font** is an app-side obligation (free to use/distribute, no modify).
- **Hindi (Tanzil `hi.hindi`, Suhel Farooq Khan/Nadwi)** → ships, and ships
  **verbatim**: non-commercial + attribution + no modification. The Khuda→Allah
  adaptation was reverted 2026-07-27 for exactly this reason.
- **Hindi (al-Umari)** → **REJECTED on register**, not deferred. Its Sanskritic
  register is wrong for this product, which needs Perso-Arabic. Licensing was
  never the blocker. See `TRANSLATIONS-ROADMAP.md`.

Still open: confirm KFGQPC **V2 604-page layout** redistribution terms (we store
only page numbers, low risk); pick a pipeline-code license (`LICENSE` TODO).
Junagarhi no longer needs re-clearing on monetization — that caveat was tied to
Tanzil's terms and is withdrawn. **Hindi (`hi.hindi`) still does**: it is Tanzil
non-commercial + attribution + verbatim, and unlike the Urdu its translators are
recent enough that no public-domain argument is available.
(Research, not legal advice; final sign-off is the owner's.)

## Next Steps (in order)

1. ~~Smoke test.~~ ✅ done.
2. ~~Download the QUL SQLite files into `sources/`.~~ ✅ done (10 files).
3. ~~Fill in `config/sources.yaml` + set metadata mode.~~ ✅ done (`per_ayah`,
   via `prepare_sources.py`).
4. ~~Build `assets/quran.db`.~~ ✅ done.
5. ~~Verify.~~ ✅ done — clean.
6. ~~Clear licensing.~~ ✅ RESOLVED for the MVP (2026-06-20) — see the Licensing
   section + `ATTRIBUTION.md`. Remaining sub-items listed under "Owner-only"
   below. (Junagarhi no longer needs re-clearing on monetization — it is public
   domain; that caveat was tied to the withdrawn Tanzil framing.)
7. ~~Push to GitHub.~~ ✅ done.
8. ~~Edition model + downloadable editions on R2.~~ ✅ done 2026-07-28 (`cb4a23e`,
   branch `feat/edition-model`) — slugs, content-addressed artifacts, live
   catalogue, verified end to end.
9. **Decide on the QPC end-of-ayah number glyph** in the Arabic text (kept as-is
   now, e.g. the `١` after 1:1). Strip it in `prepare_sources.py` if unwanted.
10. **Roman Urdu ingested + per-edition kill switch built, 2026-08-03 — not
    committed, not published.** See "SESSION HANDOFF" at the top of this file
    for the full state and exact next commands.

Owner-only, still open:
- ~~**Repo visibility vs. the licence.**~~ **SETTLED 2026-07-28 (owner): repos
  stay public.** `LICENSE` is proprietary, all rights reserved (replacing a
  briefly-recorded MIT). `alquran-data`, `alquran-app` and `alquran-roman-urdu`
  are public; `al-quran-web` is private. The owner's call is that the notice is
  what matters and visibility holds nothing back. Do not re-raise.
- **Confirm KFGQPC V2 604-page layout redistribution terms** (we store page
  numbers only — low risk).
- **Alkhair Indore permission** for Ahsanul Kalam (see `TRANSLATIONS-ROADMAP.md`).
- App-side: `TranslationsPage` needs its entry in `home_overflow_menu.dart`
  (`../alquran-app`, left alone — uncommitted WIP there).
```