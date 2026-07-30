# Ahsanul Kalam ingestion — handoff

Read this instead of replaying the session that produced it. Written 2026-07-29,
updated same day three times: after fixing the 4 surahs `build_pilot.py`
couldn't produce at all; after finding the length-outlier quarantine gate
itself was the problem for the other 30; after a much larger word/verse-level
accuracy pass (part 4 below) triggered by the owner's own manual spot-check of
surah 2, which also caught a real self-corrupting bug in `verify_pilot.py`
before it shipped.

## What this is

Turning the **Ahsanul Kalam** Hindi translation (Shaikh Muhammad Rais Qureshi,
publisher **Alkhair, Indore**) from the publisher's master PDFs into per-surah JSON
for `al-quran-web`. Owner obtained the PDFs from the translator directly.

Source: `~/Library/CloudStorage/Dropbox/Private/Islam/Quran/Hindi/Source Files/`
— `AQ1`–`AQ6`, 661 letter-portrait pages, **Hindi only, no facing Arabic**.

## Current state (2026-07-29)

| | |
|---|---|
| Surahs built | **114** of 114 |
| Surahs published (passed the gate) | **114** of 114 — **6,236** verses, all of them |
| Verses published | **6,236** |
| Live on the web | `al-quran-web` branch `feat/edition-model`, commit `55af50f` (not yet re-exported with this session's fixes) |
| Pipeline commits | `alquran-data` `b03d3b9`, `25f873e`, `ad3d000` (+ this session's `build_pilot.py`/`verify_pilot.py` changes, not yet committed) |

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

* **Fixed (this session, part 1): the 4 surahs that were missing entirely** — 2,
  4, 12, 79. Each turned out to be a marker OCR mangled past `SLOT_RE`'s
  recognition, confirmed one at a time against the source scans (never
  guessed):
    * **4:33** — a clean, correctly-printed "(33)" came back as "(8338)", 4
      digits with no stray characters, one character over the old 3-char cap.
      Cap widened to 4 — still excludes anything containing Devanagari, so it
      cannot swallow a real gloss.
    * **79:39** — the marker's *open paren* was dropped entirely ("। 39)" not
      "(39)"), invisible to any digit-based alternative. Added a second
      `SLOT_RE` alternative for a digit run + `)` preceded by whitespace/danda.
    * **2:273** — the marker itself misread by one digit (273→274) and the
      *next* marker happened to read correctly, so the old single-neighbour
      "jump confirmed" check was fooled exactly the way the 43-read-as-45 case
      it was built for. Confirmation now requires **two** consecutive
      agreeing neighbours, not one.
    * **12:21** (Yusuf — the surah with no printed title strip at all) — marker
      OCR'd as the bare consonant "(श)", no digits, indistinguishable from a
      real gloss by pattern. Widening the Devanagari exclusion generally was
      rejected: "(न)" already appears as genuine text in a dozen
      already-published surahs (7, 8, 11, 18, 21, 22, 49) and would have been
      swallowed. Added a literal, one-off exception for the exact string
      "(श)", confirmed to occur nowhere else in the corpus.
  All four in `build_pilot.py`.

* **Fixed (this session, part 2): the length-outlier gate was demoting
  correct surahs, not catching corrupt ones.** Once part 1 landed, 33 surahs
  (the original 30 plus 2, 4, 79) were quarantined for having a verse whose
  word count deviated too far (z > 4) from the same verse in the bundled
  reference Hindi edition (`hi-suhel-farooq-nadwi`). Spot-checked ~20 of the
  50 flagged verses against the Quran's actual meaning, spanning the full
  range — 26:219 at 6x the reference's length down to 6:67 at 0.2x — and
  **every one was a correct, complete, correctly-sequenced verse** (20:1
  "ताहा" flagged as "too short" is literally the two disjointed letters
  Ta-Ha; 6:71 flagged as "too long" is genuinely one of the longer ayahs in
  the Quran). The two translators gloss independently verse-by-verse with no
  fixed ratio between them, so comparing against one specific other human's
  wording is a noisy proxy — especially on short verses, where one extra
  gloss word swings the ratio hugely. `build_pilot.py`'s own 1..N
  completeness check is what actually caught the two historical real
  corruptions (ad-Dukhan/al-Jathiyah, Hud/Yusuf) and still runs before this.
  **Owner decision 2026-07-29: demoted length-outlier from a HARD
  (whole-surah quarantine) signal to SOFT** (`verify_pilot.py`) — it now
  rides along as a per-verse `verseFlags` entry like the other orthographic
  suspicions, and the surah publishes. Net effect: **all 114 surahs, all
  6,236 verses, now pass the gate** (was 80 published / 3,344 verses at the
  start of this session). 1,216 verses still carry at least one soft flag
  for a reader-facing surface to mark — that count did not go down, only the
  quarantine did.

  **Not yet done:** commit `build_pilot.py` + `verify_pilot.py`, re-run
  `publish_pilot.sh` to push this to `al-quran-web` (still on the old
  80-surah / commit `55af50f` export).

* **Fixed (this session, part 3): the word-level errors named above.** Added
  two small, explicit dictionaries to `verify_pilot.py` — `KNOWN_WORD_FIXES`
  (corpus-wide, whole-word) and `KNOWN_VERSE_FIXES` (anchored to a specific
  `(surah, ayah)`, for a real word that's wrong only in context):
    * `वद्यी` → `वह्यी` (17 occurrences) — a systematic misread of the ह्य/द्य
      conjuncts, invisible to the self-consistency check because both
      spellings clear its rare-word floor (>2 occurrences). वद्यी is not a
      Hindi word at all; वह्यी ("revelation") plainly is.
    * `अजीमुश्शान` → `अज़ीमुश्शान`, `जुल्मतों` → `ज़ुल्मतों` — the two words
      flagged above as permanently nukta-bare (no parallel-Urdu skeleton to
      restore from). Fixed literally instead: both are well-known
      Arabic-loanword spellings, confirmed by hand.
    * `कम` → `क़ौम` in exactly **4** verses (7:142, 14:5, 25:36, 27:43),
      checked one at a time against the Quran's actual meaning ("my
      PEOPLE", "that PEOPLE who denied", "a disbelieving PEOPLE"). Left as a
      per-verse fix, not a pattern: `कम` ("less") is common and correct
      everywhere else (`कम ही शुक्र करते` = "seldom give thanks"), including
      one verse (35:11, `उसकी उम्र कम की जाती है` = "his life is
      SHORTENED") that has the exact same two adjacent tokens and is already
      right — a corpus-wide `कम`→`क़ौम` rule would have broken it, so this
      is anchored to chapter:verse instead of the word.
  Re-ran `verify_pilot.py --apply --quarantine` against the real
  `dist/pilot/` output: 21 word-fixes + 4 verse-fixes applied, still **114
  surahs / 6,236 verses published, 0 quarantined**.

* **Fixed (this session, part 4): a much larger word/verse-level pass,**
  triggered by the owner manually spot-checking surah 2 and finding several
  more errors invisible to every automated check. Used three background
  agents in parallel (never editing files themselves, only reporting
  findings for hand-verification) to scan for more of the same:
    * **The single biggest error class corpus-wide: क़ौम ("people/nation")**,
      the word Prophets address their people with ("ऐ मेरी क़ौम!" — "O my
      people!"), appears correctly 109 times but also as five broken
      spellings across **~90 further occurrences** — क़ोम, कोम, क़म, कोौम,
      कीम — none of which are real Hindi words on their own. Checked a
      representative sample across many surahs, not all ~90 individually
      given the volume, with zero counter-examples found. कम (bare, no
      nukta) is the one exception that stays verse-anchored, not blanket:
      it's genuinely the real word "less" 31 other times.
    * **Pharaoh's name** — फ़्रिऔन/फ़्रऔन (transposed or dropped letters) vs
      the correct फ़िरऔन (58x elsewhere). One correct spelling for a proper
      noun; safe as a blanket fix.
    * **A cluster of dangling-halant/missing-chandrabindu/missing-anusvara
      words** confirmed individually against their verses: हें→हैं, फ्र→फिर,
      कह्→कह, कह्ाः→कहाः, नू→नौ, अजसरे→अज़सरे, केसी→कैसी (except 5:75,
      handled separately as a literal OCR duplicate "केसी कैसी"→"कैसी", not
      a word swap).
    * **More stray strip-boundary characters** (same family as 2:159/46:15
      from part 3) found by a background scan: a Devanagari "६" (six)
      standing in for "ध" at 3:17, 4:92, 4:161, 23:21, 43:64, 65:6; a stray
      "०" at 8:41 (which also had a second, independent word-split —
      "रखत। है।" for "रखता है।" — found by hand while confirming the first).
    * **Nukta-restoration gaps investigated properly** (a background agent
      traced the exact mechanism): इन्फाक़, निफ़ाक़, नफ़ा fail to restore
      because Junagarhi's parallel Urdu uses a *different root word* for the
      same concept in those specific verses (ख़र्च instead of انفاق, etc.),
      so there is no cognate to copy a nukta-skeleton from — not a code bug,
      a structural limit of verse-local matching. Fixed as three more
      `KNOWN_VERSE_FIXES` entries instead.
    * **A dozen more matra-confusion verses**, hand-verified against actual
      Quran meaning by a background agent going through the next tier of
      candidates below the strict threshold from part 3 (word appears 2-5
      times, not just once): क्यो→क्यों (16:28, 2:118), करू→करूं (10:15,
      matching this edition's own spelling elsewhere), करा→करो (49:6),
      काफ़→कुफ़्र (4:137), फरिश्ति→फरिश्ते (7:37), यहा→यह (56:24) or →यहाँ
      (57:14, 47:4, context-dependent, same word needing different fixes in
      different verses).
    * **A serious bug this batch caused and then caught before publishing**:
      one `KNOWN_VERSE_FIXES` entry (2:3's इन्फाक़ fix) had no guard against
      matching its OWN already-correct output — क़'s nukta trails the
      consonant, so "इन्फाक" is a literal prefix of the correct "इन्फाक़",
      and every re-run of `verify_pilot.py` (needed anyway, to let fixes
      that only surface after nukta-restoration converge — see below) matched
      it again and stacked another invisible combining nukta on top. Four
      runs stacked four nuktas onto 2:3 before this was noticed. Fixed with
      a `(?!़)` negative lookahead on that one entry, **plus** a corpus-wide
      backstop added to the mechanical-cleanup step that collapses any
      repeated nukta or halant, so the same mistake can't silently repeat
      itself in a future entry. Verified after the fix: exactly one nukta on
      2:3, and a full-corpus scan for doubled nukta/halant anywhere returns
      zero hits.
    * **verify_pilot.py needs multiple runs to fully converge, not one** —
      confirmed as a real, reproducible property (not just the 2:3 bug):
      some `KNOWN_*_FIXES` entries only become applicable *after* nukta
      restoration runs later in the same per-verse pass (which the
      fixed-point loop added in part 3 does not cover, since it only wraps
      steps -1/0). Running `verify_pilot.py --apply --quarantine` 3-4 times
      in a row on a fresh build is what actually reaches a stable state
      (confirmed: run 3 and run 4 both report zero changes). `publish_pilot.sh`
      does **not** currently loop this — a real gap, noted below.
  Final state after this part, confirmed against the real `dist/pilot/`
  output run to convergence: **114 surahs / 6,236 verses published, 0
  quarantined**, zero doubled nukta/halant anywhere in the corpus.

* **~9,900 "unknown" words** rank suspicion only, unchanged this session.
  Most are genuine Ahsanul Kalam vocabulary the other translator never used
  (`बिलाशुब्ह`, `मअबूद`) — closing this further needs per-word manual
  linguistic review, not more automation; the corpus-wide nukta fallback
  already tried and rejected once (34,606 false "fixes", see below) is the
  cautionary tale for why a blanket pass over this list would be reckless.
  A background-agent pass reviewed the next ~60 matra-confusion candidates
  and folded the confirmed ones into part 4 above; roughly 630 candidates
  remain unreviewed (saved nowhere permanent — regenerate with the script in
  that agent's method if resuming this).

* **`publish_pilot.sh` doesn't loop `verify_pilot.py` to convergence.** It
  calls it once. Given the multi-run convergence property above, a future
  session should either make `publish_pilot.sh` call it 3-4 times (simple,
  matches how this session actually validated it) or fix the deeper
  ordering issue properly (make the fixed-point loop also cover nukta
  restoration and मैं/में repair, not just steps -1/0). Not done this
  session — ran it by hand instead.

## Part 5 (later the same day, rounds 15–18) — for the next session

**Start here tomorrow:**
```bash
cd ~/code/alquran-data && source .venv/bin/activate
python3 pipeline/ahsanul_kalam/review_candidates.py stats
python3 pipeline/ahsanul_kalam/review_candidates.py scan --class matra-twin --limit 40
```
`review_candidates.py` (new this session) + `review_state.json` (its persistent
memory, 400+ decisions recorded) exist so this never restarts from zero. Same
`build → verify (3-4x to convergence) → sanity-scan → publish_pilot.sh` cycle
as parts 1-4; if `build_pilot.py` hasn't changed, skip straight to `verify`.

* **Every matra-twin candidate this method can detect has been reviewed**
  (all ~619 ranked candidates as of round 15, using 3 parallel background
  agents to cover the whole list in one pass instead of piecemeal batches —
  cheap because each agent only reads and reports, the actual file edits and
  rebuild/verify/publish stayed serialized). Digit-glyph, halant-fragment,
  and stray-punctuation classes also got a fresh sweep in round 16 (6 more
  fixes: अज़्→अज्र, खिज्→खिज्र, मीम्→मीम, and three semicolon-for-space
  artifacts). **`review_candidates.py scan` on any class should come back
  near-empty right now** — if it doesn't, the corpus changed (a rebuild ran)
  and there's fresh signal to review.

* **A second real bug found and fixed: nukta-restoration can fight a
  confirmed fix forever, not just oscillate a few times.** ग़रज़→गरज and
  क़ान→कान (round 10) never converge to a literal 0 — nukta restoration
  re-adds what the fix just removed on every single `verify_pilot.py`
  invocation, since it has no "exception list" and doesn't know a human
  already decided the bare form is correct. **This is a stable, harmless
  baseline** (confirmed: the final text is correct after every run, checked
  directly against the corpus, not inferred from the counter) — expect
  `known_word_fix` to plateau at a small non-zero number (4, then 6, then
  10 as more such words were added) instead of reaching 0. Don't chase it
  further; verify actual text correctness instead of the count.

* **Owner-caught bug: a fix without a `(?!़)` guard matched its own
  already-correct output.** 2:3's इन्फाक़ fix had no lookahead, so it matched
  the literal prefix of its own corrected form and stacked a duplicate nukta
  on every re-run — four `verify_pilot.py` invocations stacked four
  invisible nuktas before this was noticed. Fixed with the lookahead **and**
  a corpus-wide backstop: step -1 now collapses any repeated nukta or halant
  as a general safety net, not just this one instance. **Any new
  `KNOWN_VERSE_FIXES`/`KNOWN_WORD_FIXES` entry must be checked for this**
  before being added — `re.search(pattern, replacement)` should return
  nothing.

* **Owner-caught bug: word-boundary regex silently skipped sentence-final
  words.** `(?<![ऀ-ॿ])word(?![ऀ-ॿ])` treats the danda (।) as a Devanagari
  letter (it lives inside the same Unicode block), so `word।` with no space
  never matched — 2:18's लौटेंगे fix silently failed to apply for exactly
  this reason. Fixed with new shared `WORD_BEFORE`/`WORD_AFTER` patterns
  (also used in the pre-existing nukta-restoration code, not just this
  session's fixes) that treat danda/visarga as valid word boundaries. **Use
  `WORD_BEFORE`/`WORD_AFTER` for any new word-boundary-sensitive regex** —
  don't hand-roll the old inline pattern again.

* **A live desync between `alquran-data` and `al-quran-web` was found and
  fixed once, watch for it recurring.** `al-quran-web/data/ahsanul-kalam/surah-002.json`
  was hand-edited directly at some point, bypassing the pipeline entirely —
  caught because only that one file had a different mtime than everything
  else from the last `publish_pilot.sh` run. Ported the corrections back
  into `verify_pilot.py` so they're reproducible, but **the next
  `publish_pilot.sh` run overwrites `al-quran-web`'s data files wholesale**
  (`rm -f surah-*.json; cp`), so any future direct edit there will be
  silently lost the next time this pipeline runs. Fixes belong in
  `alquran-data`, not `al-quran-web`.

* **क़ाम is not a Hindi word under either reading — decide per verse.**
  Owner found it recurring with two different intended meanings: क़ौम
  ("people/nation") in vocative/narrative "his people" contexts, काम
  ("work/deed/affair") in idiom or direct-object contexts. All 27 bare
  occurrences plus 4 plural (`क़ामों`→`कामों`, all glossed as "deeds/works"
  and therefore safe as one blanket fix) were individually read and fixed —
  see `KNOWN_VERSE_FIXES` round 18. **Lesson for any future word like this**:
  check whether a "obviously one typo" word actually splits between two real
  targets before doing anything blanket. लिहाजा→लिहाज़ा and क़ृत्ल→क़त्ल, by
  contrast, the owner confirmed have exactly one correct spelling
  corpus-wide (superseding this session's own earlier, more cautious call
  that treated the ऋ-insertion pattern as deliberate house style) — fixed
  as blanket word-level rules instead.

* **Current totals**: 122 word-level fixes, 84 verse-specific fixes, 400+
  reviewed candidates recorded in `review_state.json`. 114/114 surahs,
  6,236/6,236 verses published, 0 quarantined, zero doubled-diacritic
  stacking anywhere — all reconfirmed after round 18.

* **Owner's own standing offer, worth remembering**: they know Hindi well
  and will resolve anything flagged as uncertain quickly. When a fix is
  lower-confidence (context is genuinely ambiguous, a gloss reads oddly),
  **say so explicitly rather than silently picking the more-likely reading**
  — e.g. 13:11's क़ाम→काम this session was flagged this way.

* **Still open, honestly**: the ~9,900 "unknown" words are unreviewed (most
  are probably genuine vocabulary, not verified word-by-word); a few messy
  multi-variant Perso-Arabic transliteration families (मुक़र्रर has ~12
  competing spellings, नाहक़, झूठे/झुठे) were explicitly flagged by reviewing
  agents as needing a dedicated normalization pass, not one-off fixes — do
  not attempt piecemeal; no independent native-speaker end-to-end read has
  happened, everything verified so far was checked against known Quranic
  meaning by an LLM (me, or a background agent), which is a real check but
  not the same thing.

* **Uncommitted right now**: `build_pilot.py`, `verify_pilot.py`,
  `HANDOFF.md`, `review_candidates.py`, `review_state.json` in
  `alquran-data`; 114 `data/ahsanul-kalam/*.json` files in `al-quran-web`.
  Owner has not yet said how to scope the two commits (likely: only these
  files, leaving each repo's other pre-existing uncommitted work — noted
  below — untouched).

* **Not mine, don't touch**: `alquran-data` also shows `ATTRIBUTION.md`,
  `pipeline/build_db.py`, `pipeline/schema.sql` modified and
  `config/hijri_anchors.yaml` untracked — presumably the owner's own
  licensing/other work, done outside this session. `al-quran-web` also has
  `ReaderToolbar.astro`, `global.css`, `reader.spec.ts`, `export-quran.mjs`,
  `site.ts` modified — same, not from this session.

* **Owner's plan going forward**: ship this Hindi edition as **experimental**
  (lowers the bar — labeled unverified, not a claim of completeness), then
  move to `alquran-roman-urdu` next, which has its own
  `docs/NEXT-SESSION.md` to read first. That project's rules are stricter in
  a specific way worth remembering: **no model (including this one) may
  decide a vowel** for that lexicon — every entry needs a named human
  reviewer. Don't try to replicate this session's approach there.

## Part 6 (2026-07-30) — review_state.json's ambiguous queue cleared to zero

**Start here next, in order of what's actually left (see bottom of this
section):**

* **All 25 candidates ambiguous as of Part 5 are now resolved** — 20 checked
  against actual verse meaning and inline translator glosses (अन्ध् गपन→
  अंधापन at 41:44, काफ़र→कुफ़्र at 36:64/9:37, सेन→"से न" word-merge at
  16:120, ज़री→ज़र्रा at 99:7-8, etc.), plus साली→"क़हत-साली" and फिला→
  फ़ितना confirmed directly by the owner after I flagged my initial guesses
  (फलाह) as wrong on inspection — the owner corrected both to फ़ितना, cross-
  checking against the translator's own gloss "(आज़माईश)" = "trial" at 60:5,
  which फलाह ("success") cannot mean.

* **The 88 previously-unreviewed matra-twin candidates from
  `review_candidates.py` are now all reviewed** — split across 3 parallel
  background agents (each reading the FULL verse text from
  `dist/pilot/ahsanul-kalam/surah-NNN.json`, not just the scan's truncated
  excerpt), then hand-verified by re-fetching every "CONFIRMED" verse myself
  before applying. ~80% were REJECTED as legitimate Hindi grammar (matras
  carry gender/number/case/tense — this has been true every round). 17 real
  fixes landed (झूठें→झूठे, लोटा→लौटा, फ़रिश्तो→फ़रिश्तों, फिल्ने→फ़ितने,
  बरहकु→बरहक़, the पूर→पुर/पूरा split, etc.). `review_candidates.py scan` on
  every one of its four classes (matra-twin, digit-glyph, halant-fragment,
  stray-punct) now returns **zero unreviewed candidates**.

* **A real, confirmable subset of the मैं/में ("I" vs "in") suspicions was
  found and fixed, not just flagged.** `verify_pilot.py`'s own bigram check
  already auto-repairs the DECISIVE cases and leaves the rest as a soft
  `main_suspect` flag — 32 of those flagged verses (मैं-evidence exceeding
  में-evidence, but below the auto-repair threshold) were read individually
  against full verse text. 22 were real errors — nearly all the pattern
  "बस/बिलाशुब्ह/ऐ...! + में + तो...हूँ", where में cannot grammatically
  follow an adverb or vocative address, so it has to be मैं. 9 were correctly
  left alone: genuine locative में where a preceding NOUN takes the
  postposition and तो starts an unrelated next clause (2:61 "शहर में, तो...",
  9:40 "दो में दूसरा", etc. — a real, confirmed grammatical difference from
  the error pattern, not a coin flip). `main_suspect` count: 32 → 9, all 9
  now verified-correct rather than merely unexamined.

* **Three multi-spelling "normalization family" issues Part 5 explicitly
  deferred are now resolved**, each checked properly rather than guessed:
  - **मुक़र्रर** ("fixed/appointed") had 6 competing OCR spellings across 51
    occurrences. Counted exactly (word-boundary, not overlapping substrings):
    मुक़्रर is dominant at 27 vs the next-highest's 8, and every non-dominant
    occurrence's actual grammatical construction (predicate "है/था", modifies
    a masculine noun, or sits before a gender-carrying participle "किए हुए")
    confirmed all four bare-form variants are the same invariant word, not a
    grammatical distinction — merged into मुक़्रर. The ा-ending form
    (मुक़्ररा/मुकुर्ररा, which directly modifies feminine nouns like मुद्दत
    with no supporting participle) was kept separate and merged to its own
    dominant spelling — a real agreement pattern, not noise.
  - **क़ृसमें/क़ृसमों** ("oaths") — the corpus itself has TWO legitimate
    camps (क़ुसमें/क़ुसमों, 16 occurrences; क़समें/क़समों, 9 occurrences)
    with no dominant form, left untouched. Only the clearly-spurious ऋ-
    insertion variant was fixed, and 9:12 settles which camp it belongs to:
    it has BOTH क़ृसमों and क़ुसमों in the same sentence referring to the
    same oaths.
  - **इस्हाक़ू** (Isaac) — a one-off long-ऊ spelling; इस्हाक़ु is this
    edition's own dominant spelling (6 vs 1), fixed to match.

* **`publish_pilot.sh` now loops `verify_pilot.py` to convergence
  automatically** (up to 4 passes, stopping when two consecutive runs
  produce identical output) instead of calling it once — closing the gap
  Part 4/5 both flagged and worked around by hand. Tested against the real
  `dist/pilot/` output: converges after 2 passes.

* **Current totals**: 144 word-level fixes (`KNOWN_WORD_FIXES`), 128
  verse-specific fixes (`KNOWN_VERSE_FIXES`), 493 candidates recorded in
  `review_state.json` (428 rejected, 61 resolved, 4 confirmed-pending-
  export, **0 ambiguous** — first time this count has been zero). 114/114
  surahs, 6,236/6,236 verses published, 0 quarantined, zero doubled-
  diacritic stacking, republished to `al-quran-web` and confirmed byte-
  identical to `dist/pilot/ahsanul-kalam/`.

* **What's genuinely left, in order of tractability**:
  1. The `confirmed: 4` in `review_candidates.py stats` is stale bookkeeping,
     not outstanding work — `review_candidates.py export` prints nothing,
     meaning all 4 are already reflected in `verify_pilot.py`.
  2. `self_inconsistent: 788` and `unknown: 11602` (soft flags, don't block
     publish) — every review-candidates.py detector that can isolate real
     errors from this pile now returns zero unreviewed, so what's left is
     the pile itself: mostly genuine Ahsanul Kalam vocabulary the reference
     edition doesn't share (per every prior round's finding). There is no
     known safe automated way to make further progress here without
     repeating the corpus-wide-fallback mistake (34,606 false "fixes",
     see below) — it needs either a new detector class nobody has designed
     yet, or slow manual/native-speaker review with no shortcut.
  3. `length_outlier: 50` — already owner-demoted to soft-flag (Part 2);
     not a to-do.
  4. Still uncommitted in both repos as of this writing — the owner has
     been holding commits deliberately across several rounds this session,
     reviewing incrementally rather than after each round.

## Hard-won lesson

Four attempts regressed the corpus (110 → 101 → 99 → 110) and each time the cause
was **widening a rule instead of making its exception specific**. The marker width
was loosened twice; the missed-marker anchor trusted a lone forward jump. The fixes
were: enumerate the stray characters, require corroboration, keep the scope
verse-local.

**Volume is not evidence.** Every regression showed a *higher* number and read as
progress — 34,606 nukta "fixes" was the worst result of the night. Check output
against the print, not counts against the previous run.

## Licensing

**Owner reports this is now resolved (2026-07-29)** — no longer blocking.
Previously: Alkhair, Indore had not granted redistribution, so deploying was
infringement, not merely premature (the copyright page also reserves the
footnote tafsir to the publisher). The `ATTRIBUTION.md`/licensing terms this
implies aren't detailed here since that update happened outside this
session — check `ATTRIBUTION.md` (shown as modified, uncommitted, in `git
status` as of this writing) for the current, authoritative terms before
treating this edition as clear to ship.

Nukta restoration is a modification, so it must be checked against those terms when
they arrive — a no-modification clause would forbid it. See
`TRANSLATIONS-ROADMAP.md` and `al-quran-web/docs/ahsanul-kalam-pilot.md`.
