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
