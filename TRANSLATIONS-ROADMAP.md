# Translations roadmap — shared across app + web

Living backlog of translations/editions to add to `assets/quran.db`. This repo
is the single source of truth for translation data (both
`../alquran-app` and `../al-quran-web` consume the DB this pipeline builds —
see `HANDOFF.md`), so a new edition is added **once, here**, then flows to both
consumers on their next DB refresh. Don't duplicate this list in either
consumer repo; link back to this file instead.

Current lineup (shipped): Urdu (Junagarhi), Hindi (Farooq Khan/Nadwi), English
(Hilali & Khan). Licensing basis for each: `ATTRIBUTION.md`.

## The edition model (landed 2026-07-28) — read before adding any translation

Adding a translation used to mean touching three repos. It is now a
`config/sources.yaml` entry plus an R2 upload, because editions carry a **stable
identity** and every consumer is driven by data rather than a hardcoded language
list.

- **`resources.slug` is the identity** (`ur-junagarhi`, `hi-suhel-farooq-nadwi`,
  `en-hilali-khan`). Consumers persist the slug; artifacts are named by it.
  **Never rename a shipped slug** — it is the key in saved reader preferences and
  in the download catalogue.
- **`resources.id` is NOT stable.** `build_db.py` takes it from `cur.lastrowid`,
  so it follows position in `sources.yaml` and every id shifts when an edition is
  inserted or reordered. Anything that persists an id silently points at the
  wrong edition after the next build.
- **`language_code` groups only.** Several editions may share a language. Two
  Hindi rows is now a supported, expected state.
- **Selector metadata lives in the DB**, not in consumer code: `native_name`,
  `direction`, `sort_order`, `default_on`. Adding a language no longer means
  editing a hardcoded list in the web toolbar or the Flutter picker.
- **`build_editions.py`** emits `<slug>-<sha12>.db.gz` + `catalogue.json` (with
  sha256 and byte sizes) for hosting on **Cloudflare R2**, so new editions
  download on demand instead of growing the app. Artifacts are deterministic — an
  unchanged edition rebuilds byte-identical, so its hash doesn't churn and
  readers aren't told to re-download text that never changed. **Nothing that
  varies per build run may go inside an artifact** — the embedded `built_at`
  timestamp broke this until 2026-07-28, churning all three digests on every
  rebuild; the build time lives in the catalogue's `generatedAt` instead. Same
  reason gzip is written with `mtime=0`. Artifact names are
  **content-addressed** so a corrected edition gets a new URL; a stable filename
  behind the CDN would serve stale bytes and surface as a bogus checksum error.
  Live at **https://editions.alquranreader.com** (bucket `al-quran-editions`);
  publish with `pipeline/publish_editions.sh`, then `verify_editions.py`. See
  `CLAUDE.md` for the three traps that all fail quietly (`--remote`,
  `Content-Encoding`, cache TTLs).
- **Bundled vs downloadable:** today's three editions stay bundled in
  `quran.db`; everything new is a download. No first-run network requirement.
  **Expected consequence:** the live catalogue currently lists exactly the three
  bundled editions, so the app's Translations screen shows all three as
  "Included" and offers nothing to download. That is correct, not a regression —
  it stays that way until a non-bundled edition (Ahsanul Kalam) lands. To exercise
  the download path before then, publish a throwaway edition under a staging
  prefix and point a debug build at it with `--dart-define`.
- **App constraint:** downloaded editions must live in a separate `editions.db`.
  The app re-seeds `quran.db` from its asset whenever the version marker changes
  (`db_seeder.dart`), so anything written into it is destroyed on app update.

Guards, because both failure modes here are silent rather than loud:
`build_db.py` refuses a missing or duplicate slug **before** deleting the
previous DB, and `verify_db.py` treats either as a hard FAIL.

## Candidate: Hindi (Ahsanul Kalam) — Rais Qureshi, print-only → OCR

- **Requested 2026-07-28 (owner).** Resolves the "Rais Qureshi does not exist as
  a digital source" dead end below — not through any ingestion channel, but by
  the owner obtaining the PDF from the translator directly, having spoken to him.

- **What it is.** *अहसनुल कलाम*, publisher **अलख़ैर (Alkhair), Indore**; 1st ed.
  Oct 2019, 2nd Dec 2023. Hindi tarjuma **Shaikh Muhammad Rais Qureshi** (Ujjain);
  Urdu base credited on the title page to **Hafiz Salahuddin Yusuf** — who is the
  *commentator* of Ahsan-ul-Bayan, whose Urdu translation is Junagarhi's, so the
  attribution is loose. Compiled (माख़ूज़) from six works: Ahsanul Kalam, Ahsanul
  Bayan, Al-Quran Al-Kareem, Taysirul Quran, Sirajul Bayan, Fahmul Quran.

- **It is a compilation, not a rendering of Junagarhi.** Checked verse by verse
  against our Junagarhi source on al-Fatiha: 1:5 and 1:7 track it very closely
  (1:7 differs only राह→रास्ता and the resulting की→का agreement), 1:4's spine
  matches — but 1:2 replaces पालने वाला with **रब**, and 1:1 drops
  शुरू करता हूँ entirely. Junagarhi is one thread of several. Under
  `alquran-roman-urdu`'s STYLE_GUIDE §0 it is therefore **evidence, never
  authority**.

- **Why the owner wants it:** Salafi creed, Perso-Arabic register, *and* it
  serves pure-Hindi readers — every Perso-Arabic term carries a tatsama gloss in
  brackets: तारीफें (प्रशंसायें), बदले (प्रतिकार), रास्ता (सुपथ), इनाम (पुरस्कार).
  That is an affordance the Junagarhi→Devanagari route does not have.

- **Nukta discipline is inconsistent** — फ़ातिहा and ग़ज़ब carry nuktas, तारीफें
  does not. Good corroboration for *vocabulary*, unreliable for *orthography*. If
  it is ever wired into `alquran-roman-urdu/scripts/validate.py` as a second
  witness, a missing nukta there must **not** count as evidence against our
  faithful-nukta rule (that repo's STYLE_GUIDE §5).

- **Master files received 2026-07-28** (owner, from the translator), superseding
  the earlier scan: `AQ1`–`AQ6`, **661 letter-portrait pages**, one print page per
  PDF page, **Hindi only — no facing Arabic**, at
  `~/Dropbox/Private/Islam/Quran/Hindi/Source Files/`.

- **The format is not what it looks like.** `pdftotext` returns only folio
  numbers and `pdfimages` reports *zero* images, which reads as "empty PDF". It
  isn't: Win2PDF wrapped **every line of type in its own PDF tiling Pattern**, and
  neither tool traverses pattern resources. Each line is a separate FlateDecode
  RGB image at a uniform **297 DPI** — lossless, so no JPEG ringing around the
  nuktas. AQ2 alone yields 4,993 line strips; ~33k across the set.
  `pipeline/ahsanul_kalam/extract_lines.py` extracts them all with page geometry
  into `sources/ahsanul-kalam/` (git-ignored) + a `lines.jsonl` manifest.

- **This is better than a page scan.** Lines arrive pre-segmented with
  coordinates, so no layout analysis or line-finding is needed, and the **three
  streams separate by strip height**: **83px = translation body** (verse numbers
  inline, `(2)`, `(3)`), **72px = footnote text** (the मुख़्तसर तफ़्सीर),
  **48px = superscript footnote reference markers**. Reconstruct a line by
  grouping strips on `top` and sorting by `x` — *not* by paint order, which groups
  by text frame (footnotes are painted before the body they annotate, header
  last). Verified on al-Fatiha: assembles cleanly, verse numbers in place.

- **Scored against the print page (owner supplied a screenshot of folio 2,
  al-Fatiha).** Body reconstruction is **96% word-accurate, 100/100 words
  aligned** — 4 errors, and 3 of them are digits, not Devanagari:
  `फ़ातिहा-1`→`फातिहा-।`, `1 रूकू`→`| रूकू`, `(1)`→`()`. Every Hindi word on the
  page came back exact, including `ग़ज़ब` with both nuktas. The 48px strips are
  confirmed to be the superscript footnote markers ⁽¹⁾–⁽⁶⁾, as the print page
  shows, and the height-based stream split holds.

- **Two OCR passes, because the failure modes are complementary.** `-l hin` gets
  Devanagari right and digits wrong; `-l eng+hin` gets digits right and mangles
  Devanagari (`रहम`→`TA`, `रूकू`→`BHE`). So take **text from the `hin` pass and
  verse numbers from the `eng+hin` pass**. Measured over AQ2 pages 1–9:
  `eng+hin` recovered al-Fatiha 1–7 exactly and al-Baqarah 1–61 with a **single**
  error (32 read as 82), which the monotonic-sequence check flags on its own and
  interpolation repairs. The same span under `hin` alone gave 18 sequence breaks
  and a spurious verse 283. **Verse segmentation is therefore solved**; assert the
  sequence per surah and let it fail loudly.

- **Nukta fidelity under OCR: measured, and it is the remaining blocker.** Tesseract `hin`
  (`--psm 7`, per strip) is near-perfect on word shapes — al-Fatiha's
  `तारीफें (प्रशंसायें) अल्लाह ही के लिए हैं…` came back character-exact — but it
  **systematically drops nuktas on क/ख/ग/ज/फ**: ज़ादे→जादे, ज़रूरत→जरूरत,
  चीज़ें→चीजें, फ़ज़ीलत→फजीलत, and worse, तक़वा→तक्वा and क़बूल→कूबूल, where the
  nukta becomes a different mark and the result is a plausible wrong word rather
  than a visible error. `ड़`/`ढ़` survive (ordinary Hindi, well modelled). Across
  150 body lines / 2,077 words the output carried only ~51 nuktas — far below this
  edition's Perso-Arabic register. `script/Devanagari` and `hin+san` are slightly
  worse. So OCR alone cannot be trusted for the one feature the edition is wanted
  for; nuktas need lexicon-driven restoration (Perso-Arabic nukta placement is
  lexically determined — क़बूल is always क़) plus review, and
  `alquran-roman-urdu`'s lexicon is the obvious source. Note the print itself is
  inconsistent (`फ़ातिहा` and `ग़ज़ब` carry nuktas, `तारीफें` and `फरमाया` do not),
  so restoration cannot be validated against the page alone — which is another
  argument for getting the DTP source rather than perfecting the OCR.
  - **Do not retry macOS Vision.** It has no Devanagari at all —
    `supportedRecognitionLanguages()` on macOS 26 lists 30 languages, none Indic.
    A Vision pass returns empty strings for every strip, which looks like a bug in
    the caller rather than an unsupported script.
  - **Highest-leverage alternative: ask the translator for the DTP source file**
    (the Win2PDF output implies InPage/PageMaker/Word upstream). Real text would
    remove the OCR stage and its nukta risk entirely. The owner already has a
    direct line to him, so this is worth asking before investing in OCR
    correction.

- **Three streams must not be conflated** once text exists: the translation, the
  bracketed glosses, and the numbered footnotes. The two corpora's parentheses do
  different jobs — Junagarhi's are explanatory *(यानी क़ियामत)*, Ahsanul Kalam's
  are register glosses *(प्रतिकार)*.

- **Licensing.** The copyright page reserves rights over the *हाशिया / mukhtasar
  tafsir* to **Alkhair, Indore** — the publisher, not the translator — and states
  the PDF is *तुलबा के लिए* (for students). Owner has the translator's permission
  and is obtaining Alkhair's. Until both are recorded in `ATTRIBUTION.md`, the
  licence is `UNVERIFIED — clear before release`.
- **Licensing enforcement.** Separately from clearing the underlying
  translation/tafsir rights above, `ATTRIBUTION.md` §4 now asserts the owner's
  own copyright in the *digital reconstruction* — the OCR/segmentation/nukta-
  restoration work this pipeline does, which exists nowhere else — and
  `LICENSE` carries the matching exception to its source-text scope limit.
  Reuse of the compiled text requires permission even independent of the
  Alkhair clearance above.

- **Nukta policy — DECIDED 2026-07-28 (owner): restore nuktas lexically.** Store
  the fully-nuktaed form throughout, matching `alquran-roman-urdu`'s faithful-nukta
  rule (STYLE_GUIDE §5), rather than reproducing the print's inconsistency. This
  is a deliberate divergence from the page, so it needs its own note in
  `ATTRIBUTION.md` alongside the English display normalizations — **and it has to
  be checked against Alkhair's permission**, which may arrive with a
  no-modification clause that forbids exactly this.

- **Web pilot landed 2026-07-28 (owner request): 81 of 114 surahs, 3,600 verses.**
  `pipeline/ahsanul_kalam/build_pilot.py` emits per-surah JSON; it lives on
  `al-quran-web` as the `hi-ahsanul-kalam-pilot` file-edition, gated behind
  `PUBLIC_SHOW_AK=1` so it cannot auto-deploy — **two** independent blockers, no
  permission and no review. Details + the go-live checklist:
  `al-quran-web/docs/ahsanul-kalam-pilot.md`. The generator refuses any surah
  whose verses are not exactly 1..N against `quran.db`.

- **What the remaining 33 surahs need.** 11 have no usable title strip (12, 22,
  25, 26, 33, 34, 36, 45, 47, 95, 102) — titles are the only surah boundary
  marker, and a missing one also makes the preceding surah over-run, so 24, 32, 35
  and 46 fail as collateral. The other 22 lose one or two verse numbers to OCR
  (surah 7 misses only verse 62; al-Baqarah is in this group). Interpolating a
  missing number between intact neighbours would recover most of them, but that is
  **renumbering scripture from a guess** — an owner decision, not a default.

- **OCR runs in one parallel pass** (`--jobs`, default 8): 27,332 tesseract
  invocations corpus-wide in ~15 minutes. Serial, coverage expansion is impractical.

- **Two silent bugs worth not reintroducing.** The `hin` pass renders `(1)` as
  `(])`, so a digits-only slot pattern under-counted markers and dropped whole
  lines unspliced. And title digits cannot be trusted at all — **3 reads as 5**
  with total consistency (13, 23, 43, 63, 73, 83, 93) — so titles are assigned by
  monotone DP alignment, not by their printed number; greedy variants stranded
  every surah after a single high misread.

- **Status: full ingestion ON HOLD 2026-07-28 (owner).** No further ingestion work until the
  owner has asked Rais Qureshi whether a **DTP source file** exists (the Win2PDF
  output implies InPage/PageMaker/Word upstream). Real text removes the OCR stage
  and the nukta problem outright, so OCR repair is not worth building until that
  question is answered. Only AQ2 has been extracted so far.
  Also still blocked on the Alkhair licence. Ships as a normal `translation` row
  (`slug: hi-ahsanul-kalam`), **alongside** Suhel Farooq Khan, not replacing it —
  the owner's decision is to offer readers the choice.

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

- **~~Therefore: Devanagari is the only route.~~ SUPERSEDED 2026-07-28.** This
  item used to conclude that the only Salafi Hindi translation in existence had
  the rejected register, so rendering Junagarhi into Devanagari was *"not an
  alternative route — it is the **only** route."* That is **no longer true**:
  the owner obtained **Ahsanul Kalam** directly from its translator (see the
  candidate below), and it is Salafi, in Hindi script, in the Perso-Arabic
  register. The dead-end note above resolved exactly as it predicted it would —
  by identifying detail from the owner, not by another channel sweep.

  The Devanagari route keeps its **project** rationale regardless: it is a second
  renderer off the same phonemic store as the Roman Urdu lexicon, which is the
  real deliverable of `../alquran-roman-urdu`. What it has lost is its claim to
  being the *only* way to serve a Perso-Arabic-register Hindi reader.

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
  4. ~~Consumers: two `hi` rows breaks the one-row-per-language assumption.~~
     **Fixed 2026-07-28** by the edition model below — several editions per
     language are now first-class.

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
