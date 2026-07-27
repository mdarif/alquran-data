# Translations roadmap — shared across app + web

Living backlog of translations/editions to add to `assets/quran.db`. This repo
is the single source of truth for translation data (both
`../alquran-app` and `../al-quran-web` consume the DB this pipeline builds —
see `HANDOFF.md`), so a new edition is added **once, here**, then flows to both
consumers on their next DB refresh. Don't duplicate this list in either
consumer repo; link back to this file instead.

Current lineup (shipped): Urdu (Junagarhi), Hindi (Farooq Khan/Nadwi), English
(Hilali & Khan). Licensing basis for each: `ATTRIBUTION.md`.

## Candidate: Saheeh International (English)

- **Requested:** 2026-07-20 (owner, via al-quran-web session) — a second,
  *alternate* English edition alongside the existing Hilali & Khan text (this
  is not "unlocking English" — English already ships). Framed as an editorial
  choice: readers who find Hilali & Khan's bracketed-gloss style dense often
  prefer Saheeh International's plainer register. Same idea would need to land
  in the app too, since both read from the same DB.
- **Source — NOT settled, needs a real look before building anything:**
  quranproject.org (the URL the owner pointed at) turns out to **not** host
  Saheeh International — it's their own house translation, unrelated. Saheeh
  International text most likely already exists among QUL's 201 translation
  resources (this pipeline already sources everything through QUL — see
  `pipeline/prepare_sources.py`), which would make this a `config/sources.yaml`
  addition rather than a new ingestion path. **Confirm the QUL resource ID and
  its license terms before scoping further** — do not assume non-commercial
  terms carry over from the Tanzil-sourced Urdu/Hindi editions; Saheeh
  International's terms need their own check, same rigor as `ATTRIBUTION.md`
  §2/§3.
- **Shape of the work, once the source is confirmed:**
  1. Add the resource to `config/sources.yaml`, rebuild + `verify_db.py`.
  2. Record it in `ATTRIBUTION.md` (license, required credit, any commercial
     caveat) — this repo's existing gate, don't skip it.
  3. **App:** new translation becomes selectable wherever English/Urdu/Hindi
     already are (see `alquran-app/lib/core/database/app_database.dart`
     resource-ordering comment) — likely a "choose your English edition"
     setting rather than a silent replacement, since Hilali & Khan stays.
  4. **Web:** `al-quran-web/src/lib/quran.ts` (`translatorName`) and
     `Ayah.astro`'s per-language blocks are keyed by `resources.lang` today
     (one row per language) — two English editions means that assumption
     needs revisiting (a `resources.edition` or similar disambiguator), not
     just dropping in a second `en` row.
- **Status:** not started. Not scheduled. Flagging here so it isn't
  re-discovered from scratch next time it comes up.

## Other deferred items (carried over from `HANDOFF.md`)

- Roman Urdu — has its own dedicated project now: `../alquran-roman-urdu`
  (lexicon) + a hand-transliterated pilot already live on the web (see
  `al-quran-web/docs/roman-urdu-pilot.md`). Not yet a DB resource; folds into
  this pipeline once the lexicon is reviewed.
- IndoPak/Asian Arabic script — Phase-2 beta per the original MVP scope.
- Audio recitation, bookmarks, tafsir, word-by-word — app-side features, not
  translation data; tracked in `alquran-app/docs/quality-backlog.md`, not here.
