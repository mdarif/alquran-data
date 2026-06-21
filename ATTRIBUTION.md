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

- **Source lineage:** Tanzil Project, `ur.junagarhi` (via QUL #305).
- **Basis:** Tanzil translation terms permit **non-commercial use with
  attribution** (<https://tanzil.net/trans/>). The app's free/da'wah model
  satisfies this. The underlying translation is also very likely public domain
  (translator d. 1941; life+50 ≈ 1991, life+60 ≈ 2001).
- **Obligations:**
  - Ship the text **verbatim** — no edits, additions, or deletions.
  - Credit the translator **and** the Tanzil Project, with a link to
    <https://tanzil.net>.
- **Required credit:** "Urdu translation by Maulana Muhammad Junagarhi. Source:
  Tanzil Project — https://tanzil.net"
- **⚠ CAVEAT — commercial use:** Tanzil's translation terms are
  **non-commercial only**. If Al Quran is ever monetized, this translation must
  be re-cleared (written permission from the translator's estate/publisher, or
  switch to a copy whose license permits commercial use).

## 3. Hindi translation — Maulana Azizul Haque al-Umari — DEFERRED

Not bundled in the MVP. When re-enabled, its licensing is already favourable:

- **Source:** QuranEnc.com — Encyclopedia of the Noble Qur'an (King Fahd
  Complex), `hindi_omari` (via QUL #166).
- **Terms (QuranEnc):** redistribution in apps is **explicitly permitted** if:
  text is **unmodified**, you **attribute "QuranEnc.com" + the version number**,
  **preserve the embedded transcript metadata**, report translation issues,
  keep to the latest version, and show no unsuitable advertisements.
- **Action when re-enabling:** add the "QuranEnc.com" + version credit here and
  in the app, then uncomment the Hindi block in `config/sources.yaml`.

---

## Still open / owner to confirm

- **KFGQPC redistribution of the V2 604-page layout** as page-number data —
  low risk (we store an "ayah → page number" mapping, not the layout/glyphs),
  but confirm with KFGQPC's developer terms before a wide public release.
- **Pipeline code license** — `LICENSE` says "choose a license (MIT
  recommended)"; pick one before publishing the repo publicly.
