# ATTRIBUTION — bundled `assets/quran.db`

The compiled database mixes sources that each carry their own terms. This file
records the required credits and the legal basis for the MVP. **The Flutter app
must surface these credits** (e.g. an "About / Credits" screen) and link out as
noted below.

> Scope: this covers the **content** bundled by the pipeline. The pipeline
> *code* is licensed separately — see `LICENSE`.

## Distribution model (the basis for clearance)

**Al Quran ships as a free, non-commercial / da'wah application.** The clearances
below depend on that. **If the app is ever monetized** (paid, ads, IAP, or
otherwise commercial), the Urdu translation must be re-cleared before release —
see the caveat under Urdu.

---

## 1. Arabic Qur'anic text — KFGQPC Hafs

- **Source:** King Fahd Glorious Qur'an Printing Complex (KFGQPC), Al-Madinah,
  Kingdom of Saudi Arabia — QPC Hafs Uthmani text, **ayah-by-ayah**, ingested
  verbatim from `quran.ar.uthmani.v2.db` as shipped by the quran.com / quran-ios
  apps (github.com/quran/quran-ios, `Domain/QuranResources/Databases`; repo code is
  Apache-2.0, the Qur'anic text itself is KFGQPC). This is the text co-designed with
  the KFGQPC font, so it is ingested with **no modification** (no tatweel-grafting,
  no mark-stripping).
- **Page numbers:** KFGQPC V2 (1421H) 604-page Mushaf layout (via QUL #10); other
  navigation indices (juz/hizb/rub/ruku/sajda) via QUL metadata.
- **Terms:** Verbatim Qur'anic text. Ship unmodified. Credit KFGQPC.
- **Required credit:** "Arabic Qur'an text and page layout © King Fahd Glorious
  Qur'an Printing Complex (KFGQPC)."
- **App-side note (NOT this repo):** the app renders this text with the matched
  KFGQPC **UthmanicHafs1 Ver18 (Regular)** font (the face quran.com's web reader
  ships, via the Quran Foundation CDN), which is free to use and distribute **but
  must not be modified**. That obligation belongs to the app, not this data repo.

## 2. Urdu translation — Maulana Muhammad Junagarhi

**Status: PUBLIC DOMAIN — cleared (owner determination, 2026-07-27).**

- **Source lineage:** Tanzil Project, `ur.junagarhi` (via QUL #305). *Not* King
  Fahd Complex — that is the English (Hilali & Khan) in §1. The distinction
  matters: Tanzil is a redistributor here, not a rights holder.
- **Basis — public domain.** Maulana Muhammad Junagarhi died in **1941**. India
  and Pakistan both apply life-plus-sixty, so the translation entered the public
  domain around **2001**; life-plus-seventy jurisdictions clear it by **2011**.
  The work is also distributed openly and at scale as an Islamic educational
  text — Quran.com, Tanzil, Islam360 and others carry it with no licensing
  step.
- **On Tanzil's terms.** Tanzil asks for non-commercial use with attribution.
  That request attaches to *their distribution*; it is not a copyright claim
  over Junagarhi's translation, which Tanzil does not own and cannot license.
  With the underlying text in the public domain, those terms are a **courtesy we
  choose to honour, not an obligation that binds us**.
- **What we do anyway, because it is right:**
  - Credit the translator by name, always.
  - Credit the Tanzil Project as the source of our digital copy, with a link.
- **Required credit:** "Urdu translation by Maulana Muhammad Junagarhi. Source:
  Tanzil Project — https://tanzil.net"
- **No commercial-use caveat.** Previously flagged as non-commercial-only on the
  strength of Tanzil's terms. That caveat is **withdrawn**: a public-domain text
  carries no such restriction, so monetization needs no re-clearance here.
  (§1 Arabic/KFGQPC and §3 Hindi have their own terms — this paragraph is about
  the Urdu only.)
- **Residual, recorded not resolved:** the text carries parenthetical glosses in
  **1,479 verses** (e.g. 1:4 `بدلے کے دن (یعنی قیامت) کا مالک ہے۔`). These are a
  hallmark of Junagarhi's own translation and are public domain with the rest.
  A publisher (Darussalam) could in principle assert rights over a specific
  *edition's* apparatus — typesetting, orthographic normalisation — separate
  from the translation. Assessed as a thin claim against a text mirrored this
  widely, and not a blocker. Revisit only if a publisher raises it.
- **Derivative works are unblocked.** Because the text is public domain, the
  Devanagari transliteration (`../alquran-roman-urdu`, ADR 0003) and Roman Urdu
  need no permission from Tanzil or anyone else. Verbatim-only no longer binds
  either. The remaining gate on those is **editorial review quality**, not
  licensing.

## 3. Hindi translation — Suhel Farooq Khan & Saifur Rahman Nadwi — BUNDLED

Bundled as of 2026-06 (owner-approved re-introduction of Hindi; the PRD MVP had
Hindi deferred).

- **Source:** Tanzil Project edition `hi.hindi`. NOT available on QUL — fetched
  via the AlQuran Cloud API (`https://api.alquran.cloud/v1/quran/hi.hindi`),
  which mirrors the Tanzil text verbatim, and compiled into
  `sources/hi-suhel-farooq-nadwi-simple.db`.
- **Terms (Tanzil):** free for **non-commercial** use with **attribution**,
  **verbatim only** (no edits) — same family of terms as the Urdu (Junagarhi)
  edition above. Credit the translators + the **Tanzil Project** with a link to
  https://tanzil.net/trans/.
- **CAVEAT:** monetizing the app later requires re-clearing — Tanzil's
  translation terms are non-commercial only.

## 4. Hindi translation — Ahsanul Kalam (Shaikh Muhammad Rais Qureshi) — EXPERIMENTAL

**Status: permission granted; ship as an experimental/pilot edition
(2026-07-30), pending OCR quality review.** Distinct from the two other Hindi-ish editions on the site: §3 above
is Suhel Farooq Khan & Saifur Rahman Nadwi's translation; the Devanagari
pilot (`alquran-roman-urdu`) is Junagarhi's *Urdu* transliterated into
Devanagari script. This is a third, separate translation, in the Perso-Arabic
Hindi register, publisher Alkhair (Indore).

- **Source:** machine OCR of the publisher's (Alkhair, Indore) master PDF, not
  sourced via Tanzil or QUL. Stored as file sidecars in `data/ahsanul-kalam/`
  in `al-quran-web` rather than a DB resource (see that repo's
  `scripts/export-quran.mjs`), specifically because neither blocker below is
  resolved yet.
- **Permission granted.** Owner confirmed permission on 2026-07-30 for this
  free, non-commercial, no-ads deployment with credit given.
- **OCR quality — NOT reviewed against the print.** Nuktas are unrestored and
  there is a known OCR error class that changes meaning (मैं "I" misread as
  में "in"). Owner decision: ship anyway, but **only** in the
  experimental/pilot lane — `partial: true` + `feedback: true` in the export
  script keep the "Experimental" pill, the coverage note, and a
  "Suggest a correction" affordance visible so readers aren't misled into
  treating it as a reviewed text. Do not promote it out of the experimental
  lane without an actual text review against the print.
- **Required credit:** "Hindi translation by Shaikh Muhammad Rais Qureshi.
  Publisher: Alkhair, Indore."
- **Plan:** owner intends this to eventually **replace** §3 (Suhel Farooq Khan)
  as the primary Hindi edition once reviewed. Until then both ship
  side-by-side.
- **Copyright in the digital reconstruction — asserted.** This edition does
  not exist anywhere else in digital form; the compiled Hindi text bundled
  here is the product of original work by this project: OCR extraction from
  Win2PDF-tiled line images, verse/line segmentation (the dual-OCR-pass,
  monotone-DP-alignment pipeline in `pipeline/ahsanul_kalam/`), and lexical
  nukta restoration. That reconstruction is Al Marfa Technologies' own
  protectable expression, layered on top of — and without displacing —
  Rais Qureshi's and Alkhair's rights in the underlying translation/tafsir
  (permission still pending, see above) and the fact that no one owns the
  public-domain Arabic/Urdu the translation is compiled from. **Bulk
  extraction, scraping, or reuse of this compiled text (as distinct from an
  independent re-transcription from the printed book) requires the owner's
  prior written permission**, same as the pipeline code under `LICENSE`.

## 5. English translation — Sahih International — DOWNLOADABLE

**Status: source confirmed in QUL as resource #193; source file pending local
download. Licence terms still need verification before release.**

- **Source:** QUL translation resource #193,
  `https://qul.tarteel.ai/resources/translation/193`, exported as
  `simple.sqlite` and ingested as `sources/en-sahih-international-simple.db`.
- **Use in app:** installable/downloadable English alternative to Hilali & Khan.
  It is not bundled and not default-on; it appears before Hilali & Khan in the
  English list for reader familiarity.
- **Required credit draft:** "English translation by Sahih International.
  Source: Quranic Universal Library — https://qul.tarteel.ai/resources/translation/193"
- **Release gate:** confirm QUL/resource-specific license terms and any
  commercial-use caveat before public release.

## Roman Urdu — Al Marfa (Abu Rayyan) — DOWNLOADABLE, UNVERIFIED

**Ingested 2026-08-03** as `resources.type = "transliteration"`, slug
`ur-roman-abu-rayyan`. The project lives in `../alquran-roman-urdu`; see
`TRANSLATIONS-ROADMAP.md`'s Roman Urdu entry for the full pipeline/kill-switch
detail. One correction to what this section used to say: the text is **not** a
phonemic-store rendering (that description belonged to the *Devanagari* track,
ADR 0003, a different project within that repo) — Roman Urdu is hand- and
assistant-transliterated directly against the Junagarhi Urdu source, per that
repo's ADR 0004, with no shared renderer between the two scripts.

- **Source:** `../alquran-roman-urdu/data/roman-urdu/`, all 6,236 verses / 114
  surahs, transliterated by **Abu Rayyan** (Mohammad Arif) in the popular
  register.
- **Underlying words:** the Junagarhi Urdu translation, public domain (§2) —
  nobody, including us, can restrict those. The transliteration itself
  (vowelization choices, house style per ADR 0004, izafat/homograph
  judgment calls) is original creative and editorial labor, not a mechanical
  1:1 transcription, and is Al Marfa Technologies' own protectable expression,
  same "we own the rendering, not the source" claim as the Devanagari section
  above. The parallel copyright/licensing language was added to
  `alquran-roman-urdu`'s own `LICENSE`/`ATTRIBUTION.md` on 2026-08-04 — keep
  both in sync if either changes.
- **Required credit draft:** "Muhammad Junagarhi; transliterated by Abu
  Rayyan. Junagarhi translation is public domain. Transliteration ©
  Abu Rayyan." (matches `config/sources.yaml`'s `author`/`license` fields and
  `al-quran-web/scripts/export-quran.mjs`'s overlay verbatim.)
- **Review status:** every verse is `status: beta-unverified` in the source
  repo — nothing has been human-reviewed. Shipped installable
  (`enabled: true`) but not default-on (`default_on: false`), same posture as
  the third-party edition it replaces before it, matching that project's own
  AGENTS.md non-negotiable ("nothing ships unreviewed" means unreviewed text
  stays opt-in and visibly unverified, not that it can never be distributed as
  a labelled beta).
- **Supersedes, does not delete:** `ur-roman-junagarhi-experimental`
  (Al-QuranJino / Muhammad Kazim) — rejected on quality (see
  `config/sources.yaml`), now `enabled: false`, kept only as a reproducible
  comparison artifact. That row's attribution is to Muhammad Kazim /
  Al-QuranJino, never to Abu Rayyan or Al Marfa.

## 6. Hindi translation — Maulana Azizul Haque al-Umari — DOWNLOADABLE

Non-default/installable Hindi option from QUL #166.

- **Source:** QUL translation resource #166,
  `https://qul.tarteel.ai/resources/translation/166`, exported as
  `simple.sqlite` and ingested as
  `sources/maulana-azizul-haque-al-umari-simple.db`.
- **Terms:** QuranEnc terms — use unmodified, credit QuranEnc.com, preserve
  embedded/version metadata where applicable. Confirm current resource terms
  before release.
- **Required credit draft:** "Hindi translation by Maulana Azizul Haque
  al-Umari. Source: Quranic Universal Library / QuranEnc.com."
- **Use in app:** downloadable Hindi alternative, not bundled and not default-on.

## 7. Bengali translation — Dr. Abu Bakr Muhammad Zakaria — DOWNLOADABLE, LIVE

**Status: published 2026-07-30.** Requested by the owner (who follows
Salafi/Ahle Hadith creed) as part of a wider sweep for verified Salafi-creed
translations across QUL's catalogue.

- **Source:** QUL translation resource #200,
  `https://qul.tarteel.ai/resources/translation/200`, exported as
  `simple.sqlite` and ingested as `sources/bn-abu-bakr-zakaria-simple.db`.
- **Creed verification:** Athari creed, Ghayr Muqallid (non-madhab, consistent
  with Ahle Hadith practice), studied directly under Sheikh Muhammad ibn
  Salih al-Uthaymin. Published by King Fahd Complex — same publishing lineage
  as §1 (Arabic) and the shipped Hilali & Khan English edition.
- **Terms:** owner determination 2026-07-30 — QUL/King Fahd Complex material
  is distributed for free Islamic/da'wah use, no explicit per-resource
  license text is published on the QUL page itself (checked; only generic
  Tarteel terms-of-use links are present). Ship on that basis, consistent
  with how §1 and the Hilali & Khan English edition are already handled.
  Revisit if a more specific restriction surfaces from the publisher directly.
- **Required credit draft:** "Bengali translation by Dr. Abu Bakr Muhammad
  Zakaria. Source: Quranic Universal Library — King Fahd Quran Complex."
- **Use in app:** installable/downloadable, not bundled, not default-on.

## 8. Indonesian translation — King Fahd Quran Complex — DOWNLOADABLE, LIVE

**Status: published 2026-07-30.** Same Salafi-creed sweep as §7.

- **Source:** QUL translation resource #173,
  `https://qul.tarteel.ai/resources/translation/173`, exported as
  `simple.sqlite` and ingested as `sources/id-king-fahd-complex-simple.db`.
- **Institutional basis:** same publisher as §1 (Arabic) and the shipped
  Hilali & Khan English edition. No individual translator named on the QUL
  page. Preferred over Indonesian's other QUL options (Sabiq company #194,
  Indonesian Islamic affairs ministry #224), neither of which was
  creed-verified.
- **Known minor defect:** footnote-marker digits leak into the plain text on
  2 of 6236 verses — 1:2 and 2:194 (see `TRANSLATIONS-ROADMAP.md` for the
  exact strings). This is a QUL source-export bug (footnote-tagged variant's
  markers bled into the plain `simple.sqlite`), not introduced by this
  pipeline. Owner decision 2026-07-30: ship as-is, fix later.
- **Terms:** owner determination 2026-07-30, same basis as §7 — no
  per-resource license text on the QUL page itself; shipped on the King Fahd
  Complex free-distribution basis already established for §1.
- **Required credit draft:** "Indonesian translation by King Fahd Quran
  Complex. Source: Quranic Universal Library."
- **Use in app:** installable/downloadable, not bundled, not default-on.

## 9. Swahili translation — Rowwad Translation Center — DOWNLOADABLE, LIVE

**Status: published 2026-07-30.** Same Salafi-creed sweep as §7/§8.

- **Source:** QUL translation resource #466,
  `https://qul.tarteel.ai/resources/translation/466`, exported as
  `simple.sqlite` and ingested as `sources/sw-rowwad-simple.db`.
- **Creed verification:** Rowwad Translation Center (Markaz Rawwād
  al-Tarjama) is a Saudi charity founded 2018 under IslamHouse.com by
  Ibrahim al-Ali, funded by the Awqaf Muhammad Abd al-Aziz al-Rajihi
  Foundation — a committee-vetted institutional Salafi source, not a single
  named scholar, publishing in 60+ languages via QuranEnc.com.
- **Terms:** owner determination 2026-07-30, same basis as §7/§8 — no
  per-resource license text found on the QUL page itself.
- **Required credit draft:** "Swahili translation by Rowwad Translation
  Center. Source: Quranic Universal Library."
- **Use in app:** installable/downloadable, not bundled, not default-on.
- **Related, not shipped:** Albanian and German editions from the same Rowwad
  institution were attempted in this pass but are blocked on bad source
  downloads (Albanian: a 3-language bundle, not single-language; German: only
  surahs 1-44, incomplete) — see `TRANSLATIONS-ROADMAP.md` and the commented
  block in `config/sources.yaml` for the re-download steps once QUL serves a
  correct export.

---

## Still open / owner to confirm

- **KFGQPC redistribution of the V2 604-page layout** as page-number data —
  low risk (we store an "ayah → page number" mapping, not the layout/glyphs),
  but confirm with KFGQPC's developer terms before a wide public release.
- ~~**Pipeline code license**~~ — **RESOLVED 2026-07-28: proprietary, all rights
  reserved** (owner). Reuse of any part of this repository requires the owner's
  prior written permission. MIT was recorded earlier the same day and
  **withdrawn** — the effort in the pipeline and in this licensing research is
  the owner's, and reuse requires asking. `LICENSE` also states the limit of that
  reservation: it covers our own work only and grants nobody rights over the
  source texts, which stay governed by this file. Note the Junagarhi translation
  is public domain and **cannot** be claimed by us either.
  - **Public repos are accepted (owner, 2026-07-28).** `alquran-data`,
    `alquran-app` and `alquran-roman-urdu` stay public; `al-quran-web` is private.
    The owner's position is that an all-rights-reserved notice is the point, and
    visibility is not a reason to hold anything back. Recorded so it is not
    re-raised: the reservation asserts the right, it does not prevent copying.
