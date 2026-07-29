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

## 4. Hindi translation — Ahsanul Kalam (Shaikh Muhammad Rais Qureshi Salafi) — EXPERIMENTAL

**Status: owner-confirmed OK to ship as an experimental/pilot edition
(2026-07-29), pending both a formal permission grant and an OCR quality
review.** Distinct from the two other Hindi-ish editions on the site: §3 above
is Suhel Farooq Khan & Saifur Rahman Nadwi's translation; the Devanagari
pilot (`alquran-roman-urdu`) is Junagarhi's *Urdu* transliterated into
Devanagari script. This is a third, separate translation, in the Perso-Arabic
Hindi register, publisher Alkhair (Indore).

- **Source:** machine OCR of the publisher's (Alkhair, Indore) master PDF, not
  sourced via Tanzil or QUL. Stored as file sidecars in `data/ahsanul-kalam/`
  in `al-quran-web` rather than a DB resource (see that repo's
  `scripts/export-quran.mjs`), specifically because neither blocker below is
  resolved yet.
- **Permission — not formally granted.** No grant letter or written permission
  from Alkhair, Indore is on file. Owner reviewed the situation and confirmed
  OK to ship anyway for this free, non-commercial, no-ads deployment with
  credit given (surfaced on `/credits/`) — the same treatment given to the
  Hilali-Khan English clearance in §1's sibling entry. This is an
  owner-confirmed judgment call, not a documented grant; revisit if Alkhair
  ever objects or a formal permission becomes available.
- **OCR quality — NOT reviewed against the print.** Nuktas are unrestored and
  there is a known OCR error class that changes meaning (मैं "I" misread as
  में "in"). Owner decision: ship anyway, but **only** in the
  experimental/pilot lane — `partial: true` + `feedback: true` in the export
  script keep the "Experimental" pill, the coverage note, and a
  "Suggest a correction" affordance visible so readers aren't misled into
  treating it as a reviewed text. Do not promote it out of the experimental
  lane without an actual text review against the print.
- **Required credit:** "Hindi translation by Shaikh Muhammad Rais Qureshi Salafi.
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

## Roman Urdu (upcoming — not yet a resource in this repo)

The Roman Urdu transliteration project lives in `../alquran-roman-urdu` and is
not yet ingested here (see `TRANSLATIONS-ROADMAP.md`, "Other deferred items").
Recording the licensing position now so it doesn't need re-deriving once it
ships: the Junagarhi Urdu source is public domain (§2) and stays that way —
nobody, including us, can restrict the underlying words. But the vowelized
Roman transliteration itself (the phonemic-store rendering built in that
project, per its ADR 0003) is original creative and editorial labor, not a
mechanical 1:1 transcription, and is Al Marfa Technologies' own protectable
expression once it lands as a `resources.type = "transliteration"` row here.
The same "we own the rendering, not the source" claim as above applies, and
the parallel copyright/licensing language needs to be added to
`alquran-roman-urdu`'s own `ATTRIBUTION.md`/`LICENSE` — not done as part of
this pass.

### (Previously) Hindi — Maulana Azizul Haque al-Umari — SUPERSEDED

Earlier builds used the al-Umari Hindi (QuranEnc `hindi_omari`, QUL #166;
redistribution permitted if unmodified + "QuranEnc.com" + version credited +
embedded metadata preserved). Replaced by the Tanzil edition above; the source
DB (`sources/maulana-azizul-haque-al-umari-simple.db`) and a commented block in
`config/sources.yaml` remain if a switch back is ever wanted.

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
