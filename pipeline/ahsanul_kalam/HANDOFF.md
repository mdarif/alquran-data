# Ahsanul Kalam ingestion — handoff

Read this instead of replaying the session that produced it. Written 2026-07-29.

## What this is

Turning the **Ahsanul Kalam** Hindi translation (Shaikh Muhammad Rais Qureshi,
publisher **Alkhair, Indore**) from the publisher's master PDFs into per-surah JSON
for `al-quran-web`. Owner obtained the PDFs from the translator directly.

Source: `~/Library/CloudStorage/Dropbox/Private/Islam/Quran/Hindi/Source Files/`
— `AQ1`–`AQ6`, 661 letter-portrait pages, **Hindi only, no facing Arabic**.

## Current state (2026-07-29)

| | |
|---|---|
| Surahs built | **110** of 114 |
| Surahs published (passed the gate) | **80** |
| Verses published | **3,344** |
| Live on the web | `al-quran-web` branch `feat/edition-model`, commit `55af50f` |
| Pipeline commits | `alquran-data` `b03d3b9`, `25f873e`, `ad3d000` |

**Nothing is deployed.** The edition is gated behind `PUBLIC_SHOW_AK=1`:

```bash
cd ~/code/al-quran-web && PUBLIC_SHOW_AK=1 npm run dev
```

Then click the "Ahsanul Kalam" pill — `defaultOn: false`, so it renders only when
the reader turns it on.

## Commands

```bash
cd ~/code/alquran-data && source .venv/bin/activate

# 1. extract line images from the PDFs (once; ~28k images into sources/, gitignored)
python3 pipeline/ahsanul_kalam/extract_lines.py --pdf-dir "<master PDFs>"

# 2. build per-surah JSON  (~13 min, 27,332 tesseract calls at --jobs 8)
python3 pipeline/ahsanul_kalam/build_pilot.py --surahs 1-114 --jobs 8

# 3. check + repair + quarantine  (~10s)
python3 pipeline/ahsanul_kalam/verify_pilot.py --apply --quarantine

# 4. publish (build + check + copy to the web repo, gated)
pipeline/ahsanul_kalam/publish_pilot.sh
```

`--apply` MUTATES `dist/pilot/ahsanul-kalam/`, so step 2 must be re-run before
step 3 is repeated. Quarantined surahs move to `dist/pilot/ahsanul-kalam-quarantine/`.

## The format (not what it looks like)

`pdftotext` returns only folio numbers and `pdfimages` reports **zero** images, so
the PDFs read as empty. They are not: Win2PDF wrapped **every line of type in its
own PDF tiling Pattern**, and neither tool traverses pattern resources. Each line
is a separate lossless FlateDecode RGB image at a uniform **297 DPI**.

Strip height separates the streams:

| height | content |
|---|---|
| 103px | centred surah title (`सूरह इख्लास-112`) — the boundary marker |
| 83px | translation body, verse numbers inline |
| 77px | running headers: surah at the left margin, **juz at the right** (`पारा - 2`) |
| 72px | footnote text (the मुख़्तसर तफ़्सीर) |
| 48px | superscript footnote reference markers |

Reconstruct a line by grouping strips on `top` and sorting by `x`. **Never use
paint order** — it groups by text frame, so footnotes are painted before the body
they annotate.

## Design decisions that must not be undone

**Verse numbers are never read.** Verses run 1..N, so marker POSITION determines
the number. Reading digits was the root of every numbering failure: 22 read as 29,
32 as 82. Worse, on the `eng+hin` pass Devanagari glosses become Latin gibberish —
`(प्रतिकार)` → `(AeA)`, sometimes numeric like `(99)` — so the two passes disagree
on how many markers a line holds. Digits are kept only to **corroborate**;
`--min-agreement` refuses a surah when they disagree too often.

**Two OCR passes, complementary failure modes.** `-l hin` reads Devanagari well and
digits badly; `-l eng+hin` the exact inverse (`रहम` → `TA`). Text from the first.

**Nuktas are decided by the parallel URDU, verse by verse.** The other Hindi
edition cannot settle orthography because it has not settled its own: `खूब` 98 vs
`ख़ूब` 90, `काफिरों` 75 vs `काफ़िरों` 72. Perso-Arabic script is unambiguous — one
Urdu letter per nukta (ق خ غ ز ذ ظ ض ف) — and Junagarhi's Urdu is verse-parallel
for all 6,236 verses.
  * `ں` (noon ghunna) maps to **nothing** — nasalisation, written as anusvara. As
    `न` every nasal-final word is one consonant too long and never matches.
  * `و`/`ی` are dropped in one skeleton variant: they are long vowels in exactly
    the words that matter (`خوب`, `عظیم`), which Devanagari writes as matras.
  * Adjacent Urdu token pairs are matched too, for compounds Urdu splits and
    Devanagari does not (`عظیم الشان` → `अज़ीमुश्शान`).
  * **NO corpus-wide fallback.** Tried; it corrupted the text — `की`→`क़ी`,
    `को`→`क़ो`, `कर`→`क़र`, `जो`→`ज़ो`, `खोल`→`ख़ोल` — reporting 34,606 "fixes"
    against the safe version's 4,810. Short skeletons match anything across the
    corpus. Verse-local is sound because the Urdu word in the same verse genuinely
    *is* the counterpart.

**`मैं`/`में` is repaired, not flagged** — the one error class that changes meaning
("I" vs "in"). Reference bigrams are too sparse (different translator's idiom), so
the deciding signals are that `P में` is attested zero times while `P` is common
(`में` is a postposition; `दीजिए` cannot take one, `पनाह` can) plus the English verse
being first person.

**Severity is tiered in the gate.** Length-vs-reference outliers are structural —
text crossed a verse boundary — so they quarantine the **whole surah**.
Orthographic suspicions publish with per-verse `verseFlags`. Flagging uniformly
quarantined 77 of 88 surahs and published 11, which is not rigour.

## Two silent corruptions this pipeline exists to prevent

Both numbered **perfectly** while holding another surah's text, so the 1..N check
could not see them. The length-vs-reference check is what caught them.

1. **Hud carried Surah Yusuf.** 11:96 held Yusuf's shirt-on-the-face verse. Yusuf
   has no printed title strip, so Hud's span ran through it.
2. **ad-Dukhan carried al-Jathiyah.** 44:5 was 45:5. Worse: al-Jathiyah's verse 1
   was itself misread, so there was no restart at 1 — the numbers merely repeated.

Boundary detection therefore splits a span where numbering fails to advance **and**
a sustained ascending run follows. A lone non-advancing number is a misread digit.

## What is still wrong (read before claiming completeness)

* **30 surahs quarantined on length outliers** — mostly 1–3 bad verses withholding
  an otherwise sound surah (surah 16 loses all 128 over a few). **Per-verse
  quarantine is the obvious next win**, but `al-quran-web`'s export enforces
  all-or-nothing per surah, so it needs that rule relaxed and a UI treatment for a
  withheld verse. Owner's call.
* **4 surahs short by one or two markers** — 2, 4, 12, 79. Each is a marker OCR
  mangled past recognition.
* **Word-level OCR errors remain.** `वद्यी` for `वह्यी` is *consistently* misread,
  so no consistency check can see it. `अपनी कम को` should be `अपनी क़ौम को` — a lost
  letter, not a nukta, and `कम` is a real Hindi word so it cannot be auto-corrected
  safely.
* **`अज़ीमुश्शान` and `जुल्मतों` still bare** — their verse Urdu yields no
  unambiguous skeleton. Left bare deliberately rather than guessed.
* **~9,900 "unknown" words** rank suspicion only. Most are genuine Ahsanul Kalam
  vocabulary the other translator never used (`बिलाशुब्ह`, `मअबूद`).

## Hard-won lesson

Four attempts regressed the corpus (110 → 101 → 99 → 110) and each time the cause
was **widening a rule instead of making its exception specific**. The marker width
was loosened twice; the missed-marker anchor trusted a lone forward jump. The fixes
were: enumerate the stray characters, require corroboration, keep the scope
verse-local.

**Volume is not evidence.** Every regression showed a *higher* number and read as
progress — 34,606 nukta "fixes" was the worst result of the night. Check output
against the print, not counts against the previous run.

## Licensing — BLOCKING

**Alkhair, Indore has not granted redistribution.** Unlike Junagarhi (public
domain), this text is somebody's property, so deploying is infringement, not
merely premature. The copyright page also reserves the footnote tafsir to the
publisher. Owner has the translator's permission and is pursuing Alkhair's.

Nukta restoration is a modification, so it must be checked against those terms when
they arrive — a no-modification clause would forbid it. See
`TRANSLATIONS-ROADMAP.md` and `al-quran-web/docs/ahsanul-kalam-pilot.md`.
