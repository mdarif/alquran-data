# Translations roadmap — shared across app + web

Living backlog of translations/editions to add to `assets/quran.db`. This repo
is the single source of truth for translation data (both
`../alquran-app` and `../al-quran-web` consume the DB this pipeline builds —
see `HANDOFF.md`), so a new edition is added **once, here**, then flows to both
consumers on their next DB refresh. Don't duplicate this list in either
consumer repo; link back to this file instead.

Current lineup (shipped): Urdu (Junagarhi), Hindi (Farooq Khan/Nadwi), English
(Hilali & Khan). Licensing basis for each: `ATTRIBUTION.md`.

## Candidate: Hindi in the Perso-Arabic register — via Junagarhi → Devanagari

- **Requested:** 2026-07-27 (owner). The ask started as "add a Salafi/Ahle
  Hadith Hindi translation by Mohammad Rais Qureshi" and resolved into something
  different once the sources were checked. Read the whole item before acting —
  the obvious moves are all wrong for non-obvious reasons.

- **Dead end — Mohammad Rais Qureshi does not exist as a digital source.**
  Checked 2026-07-27, all four ingestion channels this pipeline can reach:

  | Channel | Hindi editions carried |
  |---|---|
  | QUL `api/v1/resources/translations` | #122 Azizul Haque al-Umari **only** |
  | quran.com API v4 | #122 al-Umari only |
  | QuranEnc `api/v1/translations/list` | `hindi_omari` (al-Umari) only |
  | AlQuran Cloud / Tanzil `v1/edition?language=hi` | `hi.hindi` (Suhel Farooq Khan/Nadwi), `hi.farooq` (Farooq Khan/Ahmed) |

  Plus Archive.org full-text and web search in Latin, Devanagari
  (`मुहम्मद रईस क़ुरैशी`) and Arabic (`محمد رئيس قريشي`) — nothing. Existing Hindi
  Quran apps' translator menus list the same three names. **Do not re-run this
  search.** If it resurfaces, what's needed is identifying detail from the owner
  (publisher, Hindi title, cover, where they saw it), not another sweep. Most
  likely a print-only edition from an Ahle Hadith publisher, which would mean
  OCR — a new ingestion path, far larger than any edition added so far.

- **The actual constraint: register.** Hindi *script* carrying *Urdu*
  vocabulary. Sanskritised Hindi is rejected even when it fits on creed and
  licence. On 1:1:

  | Edition | Text | Register |
  |---|---|---|
  | al-Umari | अल्लाह के नाम से, जो **अत्यंत दयावान्, असीम** दया वाला है। | Sanskritic |
  | Suhel Farooq Khan (shipping) | अल्लाह के नाम से जो **रहमान व रहीम** है। | Perso-Arabic |
  | Junagarhi → Devanagari (target) | शुरू करता हूँ अल्लाह ताअला के नाम से जो बड़ा **मेहरबान निहायत रहम** वाला है। | Perso-Arabic |

- **al-Umari is REJECTED, not deferred.** It is the only Salafi/Ahle Hadith
  Hindi translation that exists, it is permissively licensed via QuranEnc, and
  `sources/maulana-azizul-haque-al-umari-simple.db` is already downloaded — and
  it is still the wrong artifact, because its register is the rejected one. The
  commented-out block in `config/sources.yaml` should be read as "rejected on
  register", not "cheap win waiting to be enabled". This is the single most
  likely thing for a future session to get wrong.

- **Therefore:** the only Salafi Hindi translation that exists is the one whose
  register is rejected; the only text in the wanted register with the wanted
  creed is **Junagarhi**, which is in Urdu script. Rendering Junagarhi into
  Devanagari is not an alternative route — it is the **only** route.

- **Shape of the work:** it lives in `../alquran-roman-urdu`, not here. That
  project already routes Urdu script → phonemes → Roman; Devanagari is a second
  renderer off the same phonemic store, so the expensive step (vowelization,
  6,787 unique keys) is shared rather than duplicated. See **ADR 0003** there —
  it also fixes the constraint that the phonemic store must preserve retroflex /
  aspirate / nukta distinctions that popular Roman collapses, or Devanagari
  can't be recovered without re-annotating the corpus.
  1. Lexicon review in `alquran-roman-urdu` (gates everything; nothing ships
     unreviewed — that repo's `AGENTS.md` §4).
  2. Clear the Junagarhi licence — still `UNVERIFIED` in that repo's
     `ATTRIBUTION.md`, and a script conversion is a derivative work.
  3. Ingest here as `resources.type = "transliteration"`, `language_code: hi`
     — **never** a second Hindi `translation` row. Credit the translator; never
     present it as "the Quran says".
  4. Consumers: two `hi` rows breaks the one-row-per-language assumption in
     `al-quran-web`, same blocker as Saheeh International below.

- **Status:** blocked on lexicon review + licence. Not scheduled.

- **Related decision (2026-07-27):** the Khuda→Allah adaptation on the Suhel
  Farooq Khan edition was **reverted** (`e280c79`); it now ships verbatim. It
  was never a register change — अल्लाह sits as comfortably in Urdu-flavoured
  Hindi as खुदा — so it bought nothing while costing Tanzil verbatim compliance.

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
  this pipeline once the lexicon is reviewed. **Shares its whole pipeline with
  the Hindi/Devanagari item above** — same phonemic store, two renderers — so
  reviewing that lexicon delivers both, and neither ships before it does.
- IndoPak/Asian Arabic script — Phase-2 beta per the original MVP scope.
- Audio recitation, bookmarks, tafsir, word-by-word — app-side features, not
  translation data; tracked in `alquran-app/docs/quality-backlog.md`, not here.
