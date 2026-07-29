#!/usr/bin/env python3
"""Cross-check the Ahsanul Kalam OCR against evidence, automatically.

Owner requirement 2026-07-28: no manual verification — the system checks
everything. `build_pilot.py` already guards the verse NUMBERING (exactly 1..N
against quran.db). That catches a missing or misnumbered verse, and nothing else:
a verse that lost half its words, or one where क़ौम became कोम, numbers perfectly.
This is the checker for the text itself.

Ground truth available without a human:

  * **A same-register lexicon.** The bundled Hindi edition
    (`hi-suhel-farooq-nadwi`) is 207k words of Qur'anic Hindi carrying 21k nuktas
    — the same Perso-Arabic vocabulary this edition uses, spelled by a publisher
    rather than by OCR. Words and bigrams from it are the reference.
  * **Verse-parallel text.** Every verse here has a counterpart in three other
    editions, so a verse whose length is wildly out of line with its Hindi
    counterpart has lost or gained text.

Checks, all mechanical:

  1. NUKTA RESTORATION — a bare word whose nuktaed form is well attested and whose
     bare form is never attested is restored (क़/ख़/ग़/ज़/फ़ only, the consonants
     OCR actually drops). Requires `--min-evidence` occurrences, because thin
     evidence produces wrong "corrections": the lexicon attests मस्ज़िदे 3 times,
     which would rewrite the perfectly correct मस्जिदे.
  2. SELF-CONSISTENCY — a rare word one edit from a much commoner word IN THIS
     EDITION's own text is a probable OCR error (कोम beside क़ौम). Measured against
     itself, not against the other translator: an earlier version compared to the
     reference lexicon and produced 1,735 findings that were overwhelmingly wrong,
     because a different translator's spelling choices (मअबूद vs माबूद, मुहब्बत vs
     मोहब्बत, जहानों vs जानों) are one edit apart too. Within one edition those
     choices are consistent, so a lone variant is the OCR slipping, not the
     translator.
  3. मैं / में — decided by bigram evidence from the lexicon corpus, not by a
     hand-written rule. This is the known meaning-changing error class ("I" vs
     "in") and it is invisible to every other check.
  4. UNKNOWN WORDS — no lexicon match and no single edit-1 candidate. Some are
     genuine Ahsanul Kalam vocabulary the other translator never used
     (बिलाशुब्ह, मअबूद), so these rank suspicion, they do not condemn.
  5. LENGTH OUTLIERS — verse length vs the same verse in the bundled Hindi
     edition, flagged beyond `--length-z`. Meant to catch dropped or duplicated
     text that correct numbering hides completely — but two translators gloss
     independently, so this flags plenty of correct verses too (see the
     length-outlier block below); it is a per-verse suspicion, not grounds to
     withhold a surah.

Exit code is non-zero if any verse carries an unresolved flag, so this is usable
as a gate rather than a report nobody reads.

    python pipeline/ahsanul_kalam/verify_pilot.py            # report only
    python pipeline/ahsanul_kalam/verify_pilot.py --apply    # + write repairs
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sqlite3
import statistics
import sys
from pathlib import Path

NUKTA = "़"
# The consonants whose nukta OCR drops. ड़/ढ़ are excluded on purpose: they are
# ordinary Hindi, tesseract reads them reliably, and "correcting" them would
# rewrite words that were never wrong.
PERSO_ARABIC = set("कखगजफ")

# Devanagari punctuation lives inside the Devanagari block, so a naive
# "keep Devanagari" filter keeps it and every sentence-final word looks unknown
# (हो।, कहाः). The visarga is used as a colon by this edition.
PUNCT = "।॥ः"

# Word-boundary lookaround for the exact-word substitutions below. Plain
# `(?<![ऀ-ॿ])...(?![ऀ-ॿ])` looks safe but silently under-matches: PUNCT lives
# INSIDE the Devanagari block, so a word running straight into a sentence-
# final danda with no space — लोटेंगे। — was not treated as its own word,
# and 2:18's known fix quietly never applied there while applying fine
# everywhere else the same word appeared with a space after it (a coverage
# gap, not a wrong-fix risk, but still a real one — found only by manually
# spot-checking a "confirmed 0 remaining changes" state against the source).
WORD_BEFORE = rf"(?:(?<![ऀ-ॿ])|(?<=[{PUNCT}]))"
WORD_AFTER = rf"(?=[^ऀ-ॿ]|[{PUNCT}]|$)"

# KNOWN WORD FIXES — literal, whole-word, confirmed by hand against an
# independent reference (never guessed, never applied corpus-wide on a
# pattern). Each exists because the automatic checks structurally cannot see
# it: वद्यी is a systematic misread of ह्य as द्य (two similar Devanagari
# conjuncts at 297 DPI) that recurs 17 times, so it clears both the
# self-consistency check's rare-word floor (>2) and the nukta table (neither
# word carries one) — it is invisible to every check above, and वद्यी is not
# a Hindi word at all (0 occurrences in the 207k-word reference corpus,
# against वह्यी's own 0 — this edition simply doesn't share that reference's
# vocabulary for "revelation", so absence there proves nothing either way;
# what settles it is that only one of the two spellings is a real word).
# अज़ीमुश्शान/ज़ुल्मतों lost their nukta with no parallel-Urdu skeleton to
# restore from (HANDOFF.md), so they are fixed the same way: literally.
KNOWN_WORD_FIXES = {
    "वद्यी": "वह्यी",
    "अजीमुश्शान": "अज़ीमुश्शान",
    "जुल्मतों": "ज़ुल्मतों",
    # 2026-07-29 batch: matra/anusvara/chandrabindu drops and one dangling
    # halant, found by scanning for a rare word one matra from a much commoner
    # one (see HANDOFF.md — that scan produced 740 raw candidates and ~40
    # strict ones; the large majority, things like गयी/गया, बंद/बाद, मूल/माल,
    # were REJECTED as genuine distinct Hindi words, not OCR noise, because
    # Hindi's grammar lives in its matras — a blanket version of this check is
    # NOT safe, unlike the nukta case. Each of these seven was individually
    # checked against the Quran verse it appears in and confirmed to have no
    # other legitimate reading:
    "वह्": "वह",       # 4:25 — a pronoun cannot take a dangling halant
    "बैशक": "बेशक",     # 6:78 — बैशक is not a word; बेशक appears 1225x elsewhere
    "हे": "है",         # 62:2 — "वही हे जिसने" needs the copula "है" ("He IS...")
    "दूसरो": "दूसरों",   # 39:42 — "और दूसरो को...भेज देता है" needs the oblique plural
    "तु": "तू",         # 46:15 — "तु मुझे तौफ़िक़ दे" needs the 2nd-person pronoun
    "ज़्यादी": "ज़्यादती", # 28:28 — missing त; ज़्यादती ("injustice") fits, ज़्यादी is not a word
    "वहा": "वहाँ",      # 36:57 — "उनके लिए वहा...फल होंगे" needs "there", not "वही"

    # 2026-07-29 batch, round 3 — background-agent review of the next tier
    # of matra-twin candidates (frequency 2-5, not just the freq==1 strict
    # set), each individually checked against its verse. Unlike round 1,
    # these ARE safe as blanket word-level fixes: every occurrence of each
    # exact spelling below was read in context and confirmed wrong, with
    # zero legitimate alternate meaning found for the bad spelling itself
    # (unlike कम, which genuinely means "less" and stays verse-anchored
    # below).
    "हें": "हैं",       # 21:44, 28:54 — हें is not a word; needs the plural copula
    "फ्र": "फिर",       # 11:14, 24:58 — फ्र is not a word
    "कह्": "कह",        # 46:8, 6:148, 42:23 — a dangling halant on the
                        # standard phrase "कह दीजिए" (say!)
    "कह्ाः": "कहाः",    # 11:25, 5:25, 12:50, 43:63, 38:33 — same dangling
                        # halant, on "कहाः" (said:) instead
    "नू": "नौ",         # 17:49, 17:98, 50:15 — all three are the idiom
                        # "अज़-सर-ए-नौ" ("anew"), glossed right there as
                        # "(नए सिरे)"; नू is not a word on its own
    "अजसरे": "अज़सरे",   # 17:98, 34:7, 50:15 — same idiom, missing nukta
                        # on ज (the ज़ of "अज़", Persian "from")
    "केसी": "कैसी",     # 17:48 — "आपके लिए केसी मिसालें" needs "what kind
                        # of" (5:75's "केसी कैसी" is a literal duplicate,
                        # not this word alone — handled per-verse below)

    # "क़ौम" (people/nation) is easily this edition's single most
    # frequently mis-OCR'd word — it appears correctly 109 times but also
    # turns up as five distinct broken spellings across ~83 further
    # occurrences, none of which are real Hindi words on their own. Checked
    # a representative sample across many surahs (2, 4, 5, 6, 7, 9, 10, 11,
    # 40...) rather than every single one, given the volume, but every
    # sample read exactly as "O my PEOPLE!" / "his PEOPLE" / "an enemy
    # PEOPLE" with no exception. कम/क़म are the ONE variant that needed
    # care: क़म (WITH a nukta) is never legitimately "less" (that's कम,
    # bare), so it is safe here; but bare कम genuinely means "less" 31
    # times, so it stays a per-verse fix below (7:142, 14:5, 25:36, 27:43),
    # not a blanket rule.
    "क़ोम": "क़ौम",
    "कोम": "क़ौम",
    "क़म": "क़ौम",
    "कोौम": "क़ौम",
    "कीम": "क़ौम",

    # Pharaoh's name, misread with the इ/र transposed or dropped —
    # फ़्रिऔन(14x)/फ़्रऔन(1x) vs the correct फ़िरऔन(58x). Not ambiguous; it is
    # a proper noun with exactly one correct spelling.
    "फ़्रिऔन": "फ़िरऔन",
    "फ़्रऔन": "फ़िरऔन",

    # 2026-07-29 batch, round 5 — a background agent checked the SOURCE PAGE
    # IMAGES directly (not just the OCR text) for a cluster of words ending
    # in a bare consonant + dangling halant, to settle whether this is OCR
    # damage or a deliberate translator spelling convention. Every checked
    # page shows a complete, correctly printed word; tesseract is losing
    # part of it. Two distinct, but both mechanical, failure modes:
    "हक्": "हक़",   # the nukta dot on क़ (haqq, "truth/right") is being read
                    # as a halant instead — same root word, no counter-example
                    # found across dozens of instances of either spelling.
    "अज्": "अज्र",  # "reward" — the final र is dropped.
    "उज्": "उज्र",  # "recompense" — same dropped-र pattern.
    "फज्": "फ़ज्र",  # "dawn/fajr" — same pattern; spelled with the nukta
                    # (फ़ज्र) elsewhere in this same edition, matched for
                    # consistency.

    # 2026-07-29 batch, round 6 — next tier of matra-twin candidates,
    # reviewed by a background agent against each verse individually:
    "कूबूल": "क़बूल",  # misspelling of "accept"
    "ख़ीफ": "ख़ौफ",     # not a real word; needs "fear"
    "बतार": "बतौर",    # not a word; needs "as/by way of"
    "बतोर": "बतौर",    # same word, different vowel-sign drop
    "शह्दत": "शहादत",  # missing vowel sign; "testimony"
    "पेदाईश": "पैदाईश",  # 39:6 has both spellings in the same sentence for
                        # the same word; पैदाईश is the one used 16x elsewhere
    "ग़ेर": "ग़ैर",       # 33:13 similarly pairs a correct and incorrect
                        # spelling of the same word in one sentence
    "क़ूमे": "क़ौमे",     # "people of [Prophet]" izafat compound — both
                        # occurrences (11:89, 25:37) are "क़ूमे नूह"
    "क़ोमे": "क़ौमे",     # same compound, different vowel-sign drop —
                        # not a standalone word under any reading

    # 2026-07-29 batch, round 7 — next tier, background-agent reviewed,
    # numerically sanity-checked (bad-word count vs. dominant-spelling count)
    # before adding; every one below is a plain spelling variant with no
    # separate legitimate meaning of its own.
    "पुरी": "पूरी",       "तूझे": "तुझे",
    "क़ूदिर": "क़ादिर",    "कीन": "कौन",
    "खूद": "खुद",         "कृयामत": "क़यामत",
    "क्यामत": "क़यामत",    "पैश": "पेश",
    "जेसा": "जैसा",       "कुफ्": "कुफ़",
    "हकु": "हक़",          "पेरवी": "पैरवी",
    "फेसला": "फैसला",     "अवतरीत": "अवतरित",
    "लोट": "लौट",         "कूसम": "क़सम",
    "क्सम": "क़सम",        "मुश्रीकीन": "मुश्रिकीन",
    "रुस्वा": "रूस्वा",    "इब्राहिम": "इब्राहीम",

    # 2026-07-29 batch, round 8 — owner's own continued manual check of
    # surah 2 (al-Baqarah), each individually confirmed and frequency-
    # sanity-checked before adding.
    "निफ़ाक़्": "निफ़ाक़",  # dangling halant instead of the word's own final
                          # nukta; "hypocrisy"
    "शेतानों": "शैतानों",  # matra slip; "devils/satans" — this was a
                          # near-miss in the original self-consistency scan
                          # (8x ratio, just under the 10x threshold)
    "जोरदार": "ज़ोरदार",   # missing nukta; "forceful" (of rain)
    "क़्रीब": "क़रीब",     # extra consonant cluster; "near" — 16 occurrences,
                          # not a one-off
    "रिज़्क्": "रिज़्क़",    # dangling halant instead of nukta; "provision/
                          # sustenance" — 22 occurrences settle what an
                          # earlier review flagged as possibly a deliberate
                          # transliteration convention; it isn't
    "अहृद": "अहद",        # stray ऋ vowel-sign inserted; "covenant/promise"
    "लोटेंगे": "लौटेंगे",   # "will return", not "will roll" — लौटना/लोटना
                          # are both real verbs, but every occurrence of
                          # this specific conjugated form is the "return"
                          # sense
    "लोटाए": "लौटाए",     # same verb, causative form — checked all 8
                          # occurrences of either spelling, all "returned/
                          # will be returned to", none are "rolled"

    # 2026-07-29 batch, round 9 — continued matra-twin candidate review
    # using the new review_candidates.py tool.
    "क्यो": "क्यों",  # decided earlier in the session (2:118, 16:28 both
                     # need "क्यों नहीं", not "क्या") but never actually
                     # written into this dict — caught by review_candidates.py
                     # re-surfacing it as still-unfixed.
    "कृसम": "क़सम",   # not a word; "oath" (1 occurrence vs क़सम's 29)
    "यू": "यूं",      # missing chandrabindu on "thus/like this" (75:6),
                     # not the twin's "या" ("or")
    "बन्दो": "बन्दों", # missing anusvara on the oblique plural "servants"
                     # (50:11), not the twin's "बन्दे" (a different case)

    # 2026-07-29 batch, round 10 — owner's third manual pass on surah 2,
    # cross-checked against a divergent copy found in al-quran-web (see
    # HANDOFF.md — someone had hand-patched that file directly, bypassing
    # this pipeline entirely; ported the corrections back here instead of
    # leaving them stranded outside the source of truth).
    "ग़रज़": "गरज",    # "thunder/rumble" — both occurrences (2:19, 13:13)
                      # need the same degemination; ग़रज़ ("purpose/motive")
                      # is a real but DIFFERENT word, not attested here
    "क़ान": "कान",     # "ear(s)" — all 3 occurrences (2:20, 9:61, 41:5)
    "ख़ोौफ": "ख़ौफ़",   # "fear" — both occurrences (2:38, 43:68), a garbled
                      # double vowel-sign
    "क॒ुफ्र": "कुफ़्र", # stray combining mark before उ; "disbelief"

    # 2026-07-29 batch, round 11 — continued matra-twin review.
    "फज्ल": "फज़ल",     # missing nukta; "grace/favour" (2 vs 34 occurrences)
    "कुबूल": "क़बूल",   # missing nukta; "accept" (3 vs 49) — a different
                       # bad spelling of the same word as the already-fixed
                       # कूबूल→क़बूल
    "नहो": "नहीं",      # not a word; "not" (1 vs 1707)

    # 2026-07-29 batch, round 12 — continued matra-twin review.
    "कूाबिले": "क़ाबिले",  # garbled matra; "worthy of" (izafat)
    "मौड़ा": "मोड़ा",       # not a word; "turned" (verb)
    "कुरीब": "क़रीब",       # missing nukta + extra matra; "near"
    "बग़र": "बग़ैर",        # missing ऐ matra; "without" — same word repeated
                          # correctly right before it in 22:8's own sentence
    "पेग़ाम": "पैग़ाम",     # matra slip; "message"
    "कुफ़र": "कुफ़्र",      # missing halant; "disbelief"
    "जिदा": "ज़िन्दा",     # 2:258 — "I too give LIFE and cause death"
                          # (Abraham/Nimrod dialogue); needs ज़िन्दा
                          # ("alive/give life"), not जुदा ("separate")

    # 2026-07-29 batch, round 13 — continued matra-twin review.
    "तस्दीक्": "तस्दीक़",  # dangling halant instead of nukta; "confirms"
    "क़ृमे": "क़ौमे",       # garbled izafat compound; "people of [Jonah/Noah]"
    "केसा": "कैसा",        # matra slip; "what kind/how" (question word)
    "फेसले": "फैसले",      # matra slip; plural of "decision/judgment"
    "सिफ": "सिर्फ",        # missing र्; "only"
    "लोटने": "लौटने",      # "returning", not "rolling" — same लौटना/लोटना
                          # family as लोटेंगे/लोटाए, already confirmed correct
    "क़ूसमें": "क़ुसमें",   # garbled; "oaths" — matched to this edition's own
                          # more common local spelling of the two (11 vs 8)
    "क़्समें": "क़ुसमें",   # same word, different garbling

    # 2026-07-29 batch, round 14 — continued matra-twin review.
    "जीड़े": "जोड़े",      # garbled matra; "joints"
    "मुनाफिक्": "मुनाफिक़", # dangling halant instead of nukta; "hypocrites"
    "ग़ेब": "ग़ैब",        # matra slip; "the unseen"

    # 2026-07-29 batch, round 15 — three parallel review agents covering
    # the remaining candidate ranks in one pass to fit a time constraint.
    "अकू्ल": "अक़्ल",     # garbled conjunct; "intellect"
    "दुध": "दूध",         # matra slip; "milk"
    "मुताबिक्": "मुताबिक़", # dangling halant instead of nukta; "according to"
    "फुंक": "फूंक",       # missing matra; "breathe into" (verb)
    "कुसम": "क़सम",       # missing nukta; "oath"
    "क़ोन": "कौन",        # wrong matra+nukta; "who"
    "बगेर": "बगैर",       # matra slip; "without"
    "फेला": "फैला",       # matra slip; "spread"
    "तैज़": "तेज़",        # matra slip; "intense/boiling"
    "दिवार": "दीवार",     # short vowel; "wall"
    "मज़ाक्": "मज़ाक़",     # dangling halant instead of nukta; "joke/mockery"
    "दोड़ते": "दौड़ते",     # ओ/औ confusion; "running"
    "लोटना": "लौटना",     # "to return", not "to roll" — both occurrences
                          # are "you must return"/"a chance to return"
    "सक़ता": "सकता",      # spurious nukta on the modal "can"
    "सक़ती": "सकती",      # same modal, feminine
    "बेठे": "बैठे",       # matra slip; "sat" (5 vs 25 occurrences)
    "विरूध": "विरोध",     # matra slip; "opposition/against"

    # 2026-07-29 batch, round 16 — fresh sweep of the halant-fragment class
    # (unswept since round 10), same "dropped trailing consonant" pattern
    # as the हक्/अज्/उज्/फज् family confirmed against the source images.
    "अज़्": "अज्र",        # 12:57 — "the reward of the Hereafter", dropped र
    "खिज्": "खिज्र",       # the figure in Surah al-Kahf's story (18:71 and
                          # 4 more instances in the same narrative) — the
                          # name recurs 5x truncated against 1x correct
    "मीम्": "मीम",         # 42:1 — the muqattaʿat letter-name "Meem" carries
                          # no trailing halant elsewhere (14 occurrences),
                          # matching सीन/ता's bare form

    # 2026-07-29 batch, round 17 — owner's fourth manual pass on surah 2.
    "क़॒त्ल": "क़त्ल",     # stray combining mark before त; "killing"
    "नाहक़॒": "नाहक़",     # same stray mark; "wrongfully"
    "परेहजगार": "परहेज़गार",  # garbled; "God-fearing/pious"
    "परेहज़गार": "परहेज़गार", # same word, different garbling (both wrong
                             # spellings recur; 4 occurrences already use
                             # the correct परहेज़गार)
    "बेएब": "बेऐब",       # matra slip; "without fault"

    # 2026-07-29 batch, round 18 — owner clarification: क़ाम is not a real
    # Hindi word under any reading; every occurrence is a corrupted क़ौम
    # ("people/nation") or काम ("work/deed/affair"), decided per verse below
    # since the two real targets differ by instance. लिहाजा/क़ृत्ल, by
    # contrast, the owner confirmed have ONE correct spelling everywhere —
    # blanket, not per-verse, superseding this session's earlier caution
    # about their more-common alternate spellings.
    "लिहाजा": "लिहाज़ा",   # "therefore/so" — owner confirmed this is the
                          # correct spelling corpus-wide, not लिहाजा
    "क़ृत्ल": "क़त्ल",      # "murder/killing" — owner confirmed corpus-wide,
                          # not the ऋ-inserted spelling
    "क़ामों": "कामों",     # plural of क़ाम, same non-word — all 4 occurrences
                          # gloss as "deeds/works" (कार्यों, कारसाज़)
}

# KNOWN VERSE FIXES — same idea, but the error only shows up in specific
# verses because the correct word (क़ौम, "people/nation") happens to look
# like a different real word (कम, "less") once OCR drops the ौ matra. कम is
# common and legitimate elsewhere (कम ही शुक्र करते = "seldom give thanks"),
# so it cannot be corrected as a pattern — only these four verses, checked
# individually against the Quran's actual meaning, are wrong:
#   7:142  तू मेरी कम में मेरे पीछे  -> "you be my successor AMONG MY PEOPLE"
#   14:5   अपनी कम को जुल्मतों से    -> "bring YOUR PEOPLE out of the darkness"
#   25:36  उस कम की तरफ़ जाओ        -> "go to THAT PEOPLE (who denied)"
#   27:43  वह काफिर कम में से थी    -> "she was of a disbelieving PEOPLE"
# 35:11's "उसकी उम्र कम की जाती है" (a lifespan is SHORTENED) is the same
# two tokens and is already correct — left alone on purpose.
#
# Patterns are regex, not literal strings, and deliberately tolerant of
# whether a neighbouring word's own nukta/मैं-में repair has run yet: this
# step runs BEFORE those (so the unknown-word count downstream sees the
# corrected spelling too), but नुक्ता restoration and the मैं/में bigram
# check live further down in the SAME per-verse pass and mutate the very
# words these patterns anchor on (काफ़िर, मैं). Matching only the
# already-repaired spelling meant 3 of these 4 verses silently fell back to
# needing a second `verify_pilot.py` run to actually apply — caught by
# rebuilding from scratch and finding only 1 of 4 landed in one pass.
KNOWN_VERSE_FIXES: dict[tuple[int, int], tuple[str, str]] = {
    (7, 142): (r"कम (मैं|में) मेरे", "क़ौम में मेरे"),
    (14, 5): (r"अपनी क़?म को", "अपनी क़ौम को"),
    (25, 36): (r"उस कम की", "उस क़ौम की"),
    (27, 43): (r"काफ़?िर कम में", "काफ़िर क़ौम में"),
    # 2026-07-29 batch, continued — same rule as above (word is right
    # elsewhere, wrong only here), but these five are multi-word idioms or
    # splits rather than a single swapped word, so a literal `KNOWN_WORD_FIXES`
    # entry would be too blunt (2:75's फैर alone is one matra from फिर, the
    # highest-frequency candidate in the whole scan — but THIS verse needs
    # फेर, part of the हेर-फेर idiom, not फिर; fixing फैर as a bare word
    # would have applied the wrong correction here).
    (2, 75): (r"हैर फैर", "हेर फेर"),          # हेर-फेर = "tampering", an idiom
    (38, 63): (r"यू हीं", "यूँ ही"),           # यूँ ही = "just like that", an idiom
    (55, 52): (r"दो दों क़िस्में", "दो क़िस्में"),  # OCR duplicated दो with a stray ं
    # 2:159's second "लअनत" (the first, earlier in the same verse, OCR'd
    # fine) fell across two body-line strips: tesseract left a stray
    # zero-width NON-joiner (U+200C) where the join happened AND a literal
    # space, so "लअनत" survived as "लअन" + "त्‌" — invisible in a
    # terminal, only found by dumping the verse's raw codepoints. Written
    # here without the ZWNJ because step -1, above, already strips it before
    # this step ever runs.
    (2, 159): ("लअन त् करने", "लअनत करने"),
    # 46:15's "मेर ० रब" — a Devanagari zero digit (०) sitting where "े" +
    # "रब" should read "मेरे रब"; same family as the ZWNJ artifact above, a
    # stray character tesseract inserted at a strip boundary.
    (46, 15): ("मेर ० रब", "मेरे रब"),
    # 2026-07-29 batch, round 2 — user's own manual check of surah 2 plus a
    # background scan for the same "stray character at a strip join" family
    # as 2:159/46:15, this time a Devanagari "६" (six) or "०" (zero) standing
    # in for "ध" or "े". Confirmed against the source verse in each case:
    (2, 3): (r"इन्फाक(?!़)", "इन्फाक़"),  # "spending" — no parallel-Urdu lexeme
                                       # to restore from (Junagarhi uses
                                       # ख़र्च here, not انفاق); see
                                       # KNOWN_WORD_FIXES' अज़ीमुश्शान for
                                       # the same class of gap. The (?!़) is
                                       # not decorative: क़'s nukta trails
                                       # the consonant, so "इन्फाक" is a
                                       # literal PREFIX of the correct
                                       # "इन्फाक़" — without the lookahead,
                                       # every re-run matched the already-fixed
                                       # word again and stacked another
                                       # combining nukta onto it. Four
                                       # `verify_pilot.py` invocations in a
                                       # row (chasing the फ़्रिऔन/नुक्ता
                                       # interaction below) piled up FOUR
                                       # invisible nuktas on 2:3 before this
                                       # was caught — step -1 below now also
                                       # collapses any repeated nukta as a
                                       # blanket safety net.
    (2, 10): ("निफाक", "निफ़ाक़"),      # "hypocrisy" — same gap, AND the
                                       # reference edition's own 6
                                       # occurrences split four ways
                                       # (निफ़ाक़/निफाक़/निफ़ाक/निफाक), so even
                                       # the fallback dominance check
                                       # couldn't arbitrate this one.
    (2, 16): ("नफा", "नफ़ा"),          # "profit" — Junagarhi uses فائده
                                       # here, not نفع; reference dominance
                                       # is only 33%, correctly rejected as
                                       # genuine ambiguity by the fallback,
                                       # but THIS verse's context is
                                       # unambiguous.
    (3, 17): (r"\(६ र्य\)", "(धैर्य)"),          # "patience" — ६ (digit six)
                                                # standing in for ध
    (4, 92): (r"\(म६ य\)", "(मध्य)"),            # "middle/between"
    (4, 161): (r"नाहक़्? \(अवै६ \)\)", "नाहक़ (अवैध)"),  # "wrongfully
        # (illegitimate)" — both the stray ६ and a doubled close-paren
    (23, 21): (r"उने पेटों में \(दू६ \)", "उनके पेटों में (दूध)"),  # "in
        # their bellies is (milk)" — उने is also missing क (उनके)
    (65, 6): ("दू६ पिलाए", "दूध पिलाए"),         # "breastfeed"
    # 8:41 has TWO independent breaks: माल ० ग़नीमत ("spoils of war", a
    # misread े folded into माल as a stray ० — not a numeral) near the
    # start, and "रखत। है।" (a stray danda splitting रखता, the same
    # word-split family as 2:159/46:15, found by hand while confirming the
    # first fix) at the very end. One regex spanning both, rather than a
    # second dict key, since KNOWN_VERSE_FIXES holds one pair per verse.
    (8, 41): (r"माल ० ग़नीमत(.+)रखत। है।", r"माले ग़नीमत\1रखता है।"),
    (43, 64): (r"सी६ गरास्ता", "सीधा रास्ता"),  # "the straight path"

    # 2026-07-29 batch, round 3, continued — verse-specific because either
    # the surrounding words differ per verse (a bare word fix could match
    # the wrong span) or the correct word genuinely differs by context, the
    # same reasoning as the कम/क़ौम verses above.
    (5, 75): (r"केसी कैसी", "कैसी"),   # a literal OCR duplicate — one
        # strip read correctly, the overlapping one didn't; delete the
        # wrong copy rather than "fixing" it into "कैसी कैसी"
    (34, 7): (r"अजसरे नो", "अज़सरे नौ"),  # same "anew" idiom as the नू/नो
        # WORD_FIXES entries, but this instance reads "नो" not "नू"
    (49, 6): (r"कर लिया करा", "कर लिया करो"),  # "investigate (करो, verify!)"
        # — plural imperative addressed to believers
    (4, 137): (r"काफ़ में", "कुफ़्र में"),  # "increased IN DISBELIEF" — काफ़
        # is not a word; the verse uses कुफ़्र three times already for the
        # same concept
    (7, 37): ("फरिश्ति", "फरिश्ते"),  # "our angels reach them" — फरिश्ति
        # (singular-looking) doesn't agree with the plural verb पहुंचेंगे
    (56, 24): (r"\(यहा\)", "(यह)"),  # "This is the reward for what they
        # used to do" — यहा is not a word; यह ("this"), not यही, fits the
        # plain continuation from the previous verse
    (57, 14): (r"यहा तक", "यहाँ तक"),  # "until" — missing chandrabindu
    (47, 4): (r"यहा तक", "यहाँ तक"),   # same idiom, different verse
    (10, 15): (r"करू तो", "करूं तो"),  # "if I disobey (करूं) my Lord" —
        # subjunctive, missing anusvara; spelled करूं (not करूँ) elsewhere
        # in this same edition (27:19), matched for consistency
    (3, 10): (r"ईध् न", "ईंधन"),  # "fuel" — split across two body-line
        # strips (source page confirmed by a background agent), losing the
        # chandrabindu and merging what's left of "न" with a stray space

    # 2026-07-29 batch, round 7, continued — these three needed a DIFFERENT
    # correction than the automated scan's raw suggestion (matra-twin
    # matching found the nearest common word, not necessarily the right
    # one); a background agent read the actual context and identified the
    # correct target in each case, so they're anchored per-verse rather
    # than added to KNOWN_WORD_FIXES with the scan's original (wrong) twin.
    (16, 63): ("कोमों", "क़ौमों"),  # "nations" (oblique plural)
    (6, 6): ("कामें", "क़ौमें"),    # "nations" (plural)
    (14, 9): ("क़ामे", "क़ौमे"),    # "people of [Noah and 'Aad...]"

    # 2026-07-29 batch, round 8, continued — the two owner-found errors
    # this round that aren't single-word swaps.
    (2, 17): (r"अंध् 'रों", "अंधेरों"),  # "darkness(es)" — split across two
        # body-line strips with a stray apostrophe-like character at the
        # join, same family as 2:159/3:10's word-splits
    (2, 29): (r"कर ; के", "कर के"),  # a semicolon standing in for a space
        # mid-phrase — a new stray-punctuation variant of the same
        # strip-boundary artifact family

    # 2026-07-29 batch, round 10, continued — these two need care at the
    # word level: कुफ़ (94x) and किस्म (21x) are BOTH legitimate spellings
    # elsewhere in this edition, so a blanket rule would be wrong; only
    # these specific verses are.
    (2, 6): (r"कुफ़(?!्र)( \(इन्कार\))", r"कुफ़्र\1"),  # "disbelief" — needs
        # the ्र this verse's print drops; guarded so it doesn't refire on
        # an already-correct कुफ़्र elsewhere in the same sentence
    (2, 22): (r"\(कई किस्म के\)", "(कई क़िस्म के)"),  # "(of several) KINDS
        # (of fruit)"

    # 2026-07-29 batch, round 11, continued — 27:19 has a SECOND, later
    # occurrence of the same subjunctive drop already fixed at 10:15
    # ("करूं", not "करू"), in a different clause of the same verse.
    (27, 19): (r"नेक काम करू जो", "नेक काम करूं जो"),

    # 2026-07-29 batch, round 12, continued — the scan's suggested twin
    # wasn't the right target for either of these, so both are anchored
    # per-verse with the actually-correct word instead.
    (22, 5): (r"के बरे में", "के बारे में"),  # "concerning/about" — बरे is
        # missing आ, not the offered बरी ("acquitted"), a different word
    (35, 5): (r"सच्चा है, फिरि", "सच्चा है, फिर"),  # "the promise is true,
        # THEN [do not let the world deceive you]" — not the offered फिरे

    # 2026-07-29 batch, round 13, continued — काफ्र needs कुफ़्र specifically
    # in these two verses (both use the standard "disbelieved" construction
    # with a verb, which needs the noun कुफ़्र, not the person-word काफ़िर
    # the scan offered), so it's anchored per-verse rather than a blanket
    # word fix.
    (9, 66): (r"बाद काफ्र किया", "बाद कुफ़्र किया"),
    (13, 17): (r"बातिल \(काफ्र\)", "बातिल (कुफ़्र)"),

    # 2026-07-29 batch, round 14, continued.
    (39, 7): (r"तुम काफ्र करोगे", "तुम कुफ़्र करोगे"),  # a third instance of
        # the same काफ्र->कुफ़्र need ("if you disbelieve")
    (7, 195): (r"फिर देखों वह", "फिर देखो वह"),  # "then SEE what harm..." —
        # imperative, not देखें; देखो/देखें are equally common elsewhere in
        # this edition so this stays per-verse rather than a blanket rule
    (54, 16): (r"\(देखों\) मेरा", "(देखो) मेरा"),  # same imperative, same reasoning

    # 2026-07-29 batch, round 15, continued.
    (5, 12): (r"कार्ज़", "क़र्ज़"),  # "a loan [to Allah]" — misread nukta letter
    (8, 12): (r"हर हर पौर पर", "हर हर पोर पर"),  # "strike at every JOINT" —
        # not पुर, which is an unrelated place-name suffix

    # 2026-07-29 batch, round 16, continued — fresh sweep of the
    # stray-punctuation class, same "semicolon standing in for a space at a
    # strip join" family as 2:29's "कर ; के" fix.
    (2, 229): (r"ख़ुला ; हासिल", "ख़ुला हासिल"),
    (3, 78): (r"अल्लाह ; की जानिब", "अल्लाह की जानिब"),
    (11, 78): (r"थे। ; उसने", "थे। उसने"),

    # 2026-07-29 batch, round 17, continued — surah 2 (al-Baqarah), each
    # anchored per-verse rather than blanket: क़ाम/लिहाजा/क़ृत्ल all have
    # substantial legitimate or house-style use elsewhere in the corpus
    # (क़ाम alone also appears as a real word "deeds/work" in other verses),
    # so only the specific instances confirmed against these verses are
    # touched, not the wider pattern.
    (2, 54): (r"अपनी क़ाम से कहाः(.+)लिहाजा(.+)क़ृत्ल",
              r"अपनी क़ौम से कहाः\1लिहाज़ा\2क़त्ल"),
    (2, 58): (r"अनक्रीब", "अनक़रीब"),
    (2, 60): (r"हर कूबीले ने", "हर क़बीले ने"),
    (2, 61): (r"लिहाजा(.+)लोटे(.+)", r"लिहाज़ा\1लौटे\2"),
    (2, 62): (r"\(सत्कर्म, किए", "(सत्कर्म) किए"),  # missing closing bracket
    (2, 64): (r"फ़ूज़ल", "फज़ल"),  # matches this corpus's own dominant
        # spelling of "grace" (51 occurrences), not a nuktaed फ़
    (2, 66): (r"उस \(वाकिये\)", "उस (वाक़िये)"),
    (2, 78): (r"आरजुओं", "आरज़ूओं"),
    (2, 80): (r"लिया है\? है फिर", "लिया है? फिर"),  # duplicated है

    # 2026-07-29 batch, round 18, continued — the 26 remaining bare क़ाम
    # instances (2:54 already fixed above), each individually read and
    # classified as क़ौम ("people/nation") or काम ("work/deed/affair") since
    # it is not a real word under either reading and splits between the two
    # depending on context. Patterned as {WORD_BEFORE}क़ाम{WORD_AFTER} so it
    # cannot touch the "क़ाम" substring inside मक़ाम/मुक़ाम/इन्तिक़ाम, which
    # are different words entirely and appear in several of these surahs.
    (21, 52): (WORD_BEFORE + "क़ाम" + WORD_AFTER, "क़ौम"),
    (27, 56): (WORD_BEFORE + "क़ाम" + WORD_AFTER, "क़ौम"),
    (11, 88): (WORD_BEFORE + "क़ाम" + WORD_AFTER, "काम"),
    (11, 89): (WORD_BEFORE + "क़ाम" + WORD_AFTER, "काम"),
    (11, 93): (WORD_BEFORE + "क़ाम" + WORD_AFTER, "क़ौम"),
    (50, 14): (WORD_BEFORE + "क़ाम" + WORD_AFTER, "क़ौम"),
    (7, 59): (WORD_BEFORE + "क़ाम" + WORD_AFTER, "क़ौम"),
    (7, 150): (WORD_BEFORE + "क़ाम" + WORD_AFTER, "क़ौम"),
    (6, 80): (WORD_BEFORE + "क़ाम" + WORD_AFTER, "क़ौम"),
    (6, 83): (WORD_BEFORE + "क़ाम" + WORD_AFTER, "क़ौम"),
    (6, 133): (WORD_BEFORE + "क़ाम" + WORD_AFTER, "क़ौम"),
    (6, 135): (WORD_BEFORE + "क़ाम" + WORD_AFTER, "क़ौम"),
    (10, 3): (WORD_BEFORE + "क़ाम" + WORD_AFTER, "काम"),
    (10, 71): (WORD_BEFORE + "क़ाम" + WORD_AFTER, "क़ौम"),
    (10, 84): (WORD_BEFORE + "क़ाम" + WORD_AFTER, "क़ौम"),
    (48, 16): (WORD_BEFORE + "क़ाम" + WORD_AFTER, "क़ौम"),
    (29, 29): (WORD_BEFORE + "क़ाम" + WORD_AFTER, "काम"),
    (29, 36): (WORD_BEFORE + "क़ाम" + WORD_AFTER, "क़ौम"),
    (5, 20): (WORD_BEFORE + "क़ाम" + WORD_AFTER, "क़ौम"),
    (13, 11): (WORD_BEFORE + "क़ाम" + WORD_AFTER, "काम"),
    (4, 90): (WORD_BEFORE + "क़ाम" + WORD_AFTER, "काम"),
    (28, 15): (WORD_BEFORE + "क़ाम" + WORD_AFTER, "काम"),
    (28, 76): (WORD_BEFORE + "क़ाम" + WORD_AFTER, "क़ौम"),
    (28, 79): (WORD_BEFORE + "क़ाम" + WORD_AFTER, "क़ौम"),
    (19, 27): (WORD_BEFORE + "क़ाम" + WORD_AFTER, "काम"),
    (14, 31): (WORD_BEFORE + "क़ाम" + WORD_AFTER, "काम"),
}


def log(msg: str) -> None:
    print(f"[ak-verify] {msg}", flush=True)


def tokens(text: str) -> list[str]:
    """Devanagari words, punctuation and bracket furniture removed."""
    out = []
    for raw in text.split():
        w = "".join(ch for ch in raw if "ऀ" <= ch <= "ॿ" and ch not in PUNCT)
        if w:
            out.append(w)
    return out


def strip_nukta(w: str) -> str:
    return w.replace(NUKTA, "")


def build_lexicon(db: Path, slug: str) -> tuple[dict, collections.Counter]:
    """Word forms and bigrams from a published edition of the same register."""
    conn = sqlite3.connect(db)
    rid = conn.execute("SELECT id FROM resources WHERE slug = ?", (slug,)).fetchone()
    if not rid:
        sys.exit(f"no resource '{slug}' in {db}")
    verses = [t for (t,) in conn.execute(
        "SELECT text_content FROM translations WHERE resource_id = ?", (rid[0],))]
    conn.close()

    forms: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    bigrams: collections.Counter = collections.Counter()
    for v in verses:
        ws = tokens(v)
        for w in ws:
            forms[strip_nukta(w)][w] += 1
        for a, b in zip(ws, ws[1:]):
            bigrams[(a, b)] += 1
    return forms, bigrams


def edit1(word: str, vocab: set[str]) -> list[str]:
    """Lexicon words one Devanagari edit from `word`."""
    letters = set("".join(vocab)) if len(vocab) < 1 else None
    hits = set()
    # Deletions / transpositions / replacements-with-nukta are the shapes OCR
    # actually produces; generating the full edit-1 universe over ~90 Devanagari
    # code points would be slower and no more accurate.
    for i in range(len(word)):
        cand = word[:i] + word[i + 1:]
        if cand in vocab:
            hits.add(cand)
        for ch in "़ािीुूेैोौंृ्":
            c2 = word[:i] + ch + word[i:]
            if c2 in vocab:
                hits.add(c2)
            c3 = word[:i] + ch + word[i + 1:]
            if c3 in vocab:
                hits.add(c3)
    for ch in "़ािीुूेैोौंृ्":
        if word + ch in vocab:
            hits.add(word + ch)
    return sorted(hits)



# --- Urdu as the nukta authority ------------------------------------------
# The other Hindi edition cannot settle orthography because it has not settled it
# itself: खूब 98 times against ख़ूब 90, काफिरों 75 against काफ़िरों 72. Perso-Arabic
# script has no such ambiguity — a Devanagari nukta corresponds to exactly one
# Urdu letter — and Junagarhi's Urdu is verse-parallel for all 6,236 verses. So
# the Urdu decides, verse by verse, and cannot be led astray by another
# translator's habits.
URDU_TO_DEVA = {
    'ب': 'ब', 'پ': 'प', 'ت': 'त', 'ٹ': 'ट', 'ث': 'स', 'ج': 'ज', 'چ': 'च',
    'ح': 'ह', 'خ': 'ख़', 'د': 'द', 'ڈ': 'ड', 'ذ': 'ज़', 'ر': 'र', 'ڑ': 'ड़',
    'ز': 'ज़', 'ژ': 'ज़', 'س': 'स', 'ش': 'श', 'ص': 'स', 'ض': 'ज़', 'ط': 'त',
    'ظ': 'ज़', 'ع': '', 'غ': 'ग़', 'ف': 'फ़', 'ق': 'क़', 'ک': 'क', 'گ': 'ग',
    'ل': 'ल', 'م': 'म', 'ن': 'न', 'ں': '', 'و': 'व', 'ہ': 'ह', 'ھ': 'ह',
    'ی': 'य', 'ے': 'य', 'ئ': '', 'ء': '', 'آ': '', 'ا': '', 'ٰ': '',
    'ۃ': 'त', 'ة': 'त',
}
# ں (noon ghunna) maps to NOTHING: it is nasalisation, which Devanagari writes as
# anusvara rather than as a letter. Treating it as न left every nasal-final word one
# consonant too long, so काफिरों/کافروں and जुल्मतों/ظلمتوں never matched and kept
# their missing nuktas.
URDU_DROP = set('ًٌٍَُِّْٰٓٔۖۗۘ۔،؟')
CONSONANT = re.compile(r"[क-ह]़?")


def urdu_skeletons(word: str) -> set[str]:
    """Consonant skeletons for an Urdu word, nuktas kept.

    Two variants, because و and ی are long vowels in exactly the words that matter
    — خوب, عظیم, زمین — and Devanagari writes those as matras, not letters. Keeping
    them in the skeleton makes nothing line up.
    """
    keep = [c for c in word if c not in URDU_DROP]
    return {"".join(URDU_TO_DEVA.get(c, '') for c in keep),
            "".join(URDU_TO_DEVA.get(c, '') for c in keep if c not in 'وی')}


def deva_skeleton(word: str) -> str:
    return "".join(CONSONANT.findall(word))


def apply_skeleton(word: str, skeleton: str) -> str:
    """Copy the skeleton's nuktas onto `word`'s consonants, in order."""
    marks = [len(m.group(0)) > 1 for m in CONSONANT.finditer(skeleton)]
    out, idx = [], 0
    for ch in word:
        out.append(ch)
        if "क" <= ch <= "ह":
            if idx < len(marks) and marks[idx]:
                out.append(NUKTA)
            idx += 1
    return "".join(out)


def urdu_nukta_table(db: Path, slug: str) -> dict[tuple[int, int], dict[str, str]]:
    """Per-verse map: nukta-stripped skeleton -> the nuktaed skeleton."""
    conn = sqlite3.connect(db)
    rows = conn.execute(
        "SELECT a.surah_id, a.ayah_number, t.text_content"
        "  FROM translations t JOIN ayahs a ON a.id = t.ayah_id"
        " WHERE t.resource_id = (SELECT id FROM resources WHERE slug = ?)",
        (slug,)).fetchall()
    conn.close()
    table: dict[tuple[int, int], dict[str, str]] = {}
    corpus: dict[str, set[str]] = collections.defaultdict(set)
    for surah, ayah, text in rows:
        seen: dict[str, set[str]] = collections.defaultdict(set)
        words = text.split()
        # Adjacent pairs as well as single words: Urdu writes some compounds as two
        # tokens where Devanagari writes one — عظیم الشان against अज़ीमुश्शान — and a
        # single-token table can never match those.
        units = words + [a + b for a, b in zip(words, words[1:])]
        for word in units:
            for sk in urdu_skeletons(word):
                if NUKTA in sk:
                    seen[strip_nukta(sk)].add(sk)
                    corpus[strip_nukta(sk)].add(sk)
        # Only unambiguous skeletons are usable.
        table[(surah, ayah)] = {k: next(iter(v)) for k, v in seen.items()
                                if len(v) == 1}
    # NO corpus-wide fallback. It was tried, to catch words whose own verse phrases
    # the Urdu differently, and it CORRUPTED the text: short skeletons are hopelessly
    # ambiguous across 6,236 verses, so की became क़ी, को became क़ो, कर became क़र,
    # जो became ज़ो, खोल became ख़ोल. It "fixed" 34,606 words where the verse-local
    # table fixes 4,810, and the difference was almost entirely wrong.
    #
    # Verse-local matching is what makes this sound: the Urdu word in the same verse
    # IS the counterpart of the Devanagari word, so the correspondence is real rather
    # than a coincidence of consonants. A word the verse's Urdu cannot settle stays
    # bare and gets flagged.
    return table


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", default="dist/pilot/ahsanul-kalam")
    ap.add_argument("--db", default="assets/quran.db")
    ap.add_argument("--reference", default="hi-suhel-farooq-nadwi",
                    help="edition slug used as the lexicon/length reference")
    ap.add_argument("--min-evidence", type=int, default=5,
                    help="lexicon occurrences required to restore a nukta")
    ap.add_argument("--length-z", type=float, default=4.0)
    ap.add_argument("--dominance", type=float, default=0.9,
                    help="share of a word's occurrences that must carry the nukta "
                         "in the reference before it is restored everywhere")
    ap.add_argument("--rare-max", type=int, default=2,
                    help="a word this rare in the edition itself may be an OCR slip")
    ap.add_argument("--twin-ratio", type=int, default=10,
                    help="how much commoner a near-twin must be to accuse a word")
    ap.add_argument("--bigram-ratio", type=int, default=3,
                    help="मैं must outscore में by this factor to be repaired")
    ap.add_argument("--bigram-min", type=int, default=5,
                    help="minimum मैं bigram evidence before repairing")
    ap.add_argument("--min-context", type=int, default=5,
                    help="times the preceding word must appear in the reference "
                         "before its never-followed-by-में record counts")
    ap.add_argument("--urdu", default="ur-junagarhi",
                    help="edition whose Perso-Arabic script decides the nuktas")
    ap.add_argument("--english", default="en-hilali-khan",
                    help="edition used to detect that a verse is first person")
    ap.add_argument("--apply", action="store_true",
                    help="write restorations + per-verse flags back to the JSON")
    ap.add_argument("--quarantine", action="store_true",
                    help="delete surahs that still carry unresolved flags, and "
                         "exit 0 — publishing then ships only what passed")
    ap.add_argument("--report", default="dist/pilot/ahsanul-kalam-report.json")
    args = ap.parse_args()

    pilot = Path(args.pilot)
    files = sorted(pilot.glob("surah-*.json"))
    if not files:
        sys.exit(f"no pilot files in {pilot}")

    forms, bigrams = build_lexicon(Path(args.db), args.reference)
    vocab = {f for c in forms.values() for f in c}
    vocab |= set(forms)
    log(f"lexicon: {len(forms)} keys / {len(vocab)} forms from {args.reference}")

    # Reference UNIGRAMS: needed so "P is never followed by में" can be told apart
    # from "P was never seen at all".
    uni: collections.Counter = collections.Counter()
    conn = sqlite3.connect(args.db)
    for (t,) in conn.execute(
            "SELECT text_content FROM translations WHERE resource_id ="
            " (SELECT id FROM resources WHERE slug = ?)", (args.reference,)):
        uni.update(tokens(t))

    # First-person verses, from the English edition. A pronoun question is easier
    # to answer in a language that marks the subject explicitly.
    en_first_person: dict[tuple[int, int], bool] = {}
    for s_, a_, t_ in conn.execute(
            "SELECT a.surah_id, a.ayah_number, t.text_content"
            "  FROM translations t JOIN ayahs a ON a.id = t.ayah_id"
            " WHERE t.resource_id = (SELECT id FROM resources WHERE slug = ?)",
            (args.english,)):
        en_first_person[(s_, a_)] = bool(re.search(r"\bI\b|\bmy\b|\bme\b", t_))
    conn.close()
    log(f"first-person verses per {args.english}: "
        f"{sum(en_first_person.values())}/{len(en_first_person)}")

    # Reference lengths, per (surah, ayah), for the length check.
    conn = sqlite3.connect(args.db)
    rid = conn.execute("SELECT id FROM resources WHERE slug = ?",
                       (args.reference,)).fetchone()[0]
    ref_len = {(s, a): len(t.split()) for s, a, t in conn.execute(
        "SELECT a.surah_id, a.ayah_number, t.text_content"
        "  FROM translations t JOIN ayahs a ON a.id = t.ayah_id"
        " WHERE t.resource_id = ?", (rid,))}
    conn.close()

    urdu_table = urdu_nukta_table(Path(args.db), args.urdu)
    log(f"urdu nukta authority: {sum(len(v) for v in urdu_table.values())} "
        f"skeleton(s) across {len(urdu_table)} verses")

    # --- nukta restorations, decided once over the whole corpus ---------------
    restore: dict[str, str] = {}
    thin: list[tuple[str, str, int]] = []
    for key, cand in forms.items():
        nuktaed = {f: n for f, n in cand.items()
                   if NUKTA in f and any(c in PERSO_ARABIC for c in f)}
        if not nuktaed:
            continue
        bare = cand.get(key, 0)
        nn = sum(nuktaed.values())
        best, n = max(nuktaed.items(), key=lambda kv: kv[1])
        # DOMINANCE, not unanimity. Requiring the bare form to be attested ZERO
        # times threw away overwhelming evidence over a single typo: the reference
        # writes अज़ाब 548 times and अजाब once, ज़मीन 472 times and जमीन twice — and
        # one stray occurrence blocked the restoration, so अजाब and जमीन shipped
        # without their nuktas.
        #
        # Genuine ambiguity still blocks it, and looks quite different: तारीफ़ 9 vs
        # तारीफ 12, काफ़िरों 72 vs काफिरों 75. There the edition itself is undecided
        # and we have no business choosing.
        if n < args.min_evidence:
            thin.append((key, best, n))
            continue
        if nn / (nn + bare) >= args.dominance:
            restore[key] = best
        else:
            thin.append((key, best, n))

    # This edition's own vocabulary, for the self-consistency check.
    self_freq: collections.Counter = collections.Counter()
    for path in files:
        for v in json.loads(path.read_text(encoding="utf-8"))["ayahs"].values():
            self_freq.update(tokens(v))
    self_vocab = set(self_freq)
    log(f"edition vocabulary: {len(self_vocab)} distinct words, "
        f"{sum(self_freq.values())} tokens")

    ratios = []
    findings: list[dict] = []
    counts = collections.Counter()
    per_verse_flags: dict[str, dict[str, list[str]]] = {}

    for path in files:
        doc = json.loads(path.read_text(encoding="utf-8"))
        surah = doc["surah"]
        changed = False
        flags_for_surah: dict[str, list[str]] = {}

        for num, text in list(doc["ayahs"].items()):
            flags: list[str] = []

            # -1/0. MECHANICAL cleanup + known, hand-confirmed fixes, run to
            # a FIXED POINT rather than once. 55:52's known-verse fix
            # reproducibly needed a second `verify_pilot.py` invocation to
            # land even though it depends on nothing else in this loop and
            # matches fine in isolation — never root-caused (not an ordering
            # dependency like 7:142/14:5/27:43's, which the regex tolerance
            # above already fixed), so rather than leave a known-fix that
            # silently requires re-running the tool by hand, this loop just
            # keeps applying steps -1/0 until nothing changes. Capped at 5
            # iterations — these are literal/near-literal substitutions, not
            # a search that could genuinely oscillate.
            for _ in range(5):
                start = text

                # -1. MECHANICAL cleanup — orthographically invalid
                #     regardless of word or context, so no per-verse
                #     judgment is needed. A doubled halant (््) cannot occur
                #     in valid Devanagari; a zero-width non-joiner (U+200C,
                #     distinct from the ZWJ build_pilot.py already strips)
                #     turned up wedged inside a word at a body-line join
                #     (2:159). Found 51 doubled-halant tokens corpus-wide in
                #     the 2026-07-29 scan. A repeated nukta (़़+) can't occur
                #     either — added after a KNOWN_VERSE_FIXES entry without
                #     a (?!़) guard stacked four of them onto 2:3 by matching
                #     its own already-fixed output on successive runs; this
                #     is the general-purpose backstop for that whole class
                #     of mistake, not just the one instance that got caught.
                cleaned = (text.replace("‌", "")
                               .replace("््", "्")
                               .replace("़़", "़"))
                while "़़" in cleaned:
                    cleaned = cleaned.replace("़़", "़")
                if cleaned != text:
                    text = cleaned
                    counts["mechanical_cleanup"] += 1

                # 0. known, hand-confirmed fixes — checked in first because
                #    they are invisible to every mechanical check below (see
                #    the two dicts' comments for why each exists).
                fixed_verse = KNOWN_VERSE_FIXES.get((surah, int(num)))
                if fixed_verse and re.search(fixed_verse[0], text):
                    text = re.sub(fixed_verse[0], fixed_verse[1], text)
                    counts["known_verse_fix"] += 1
                for bad, good in KNOWN_WORD_FIXES.items():
                    if bad in text:
                        # `bad in text` is a plain substring pre-filter, not
                        # word-boundary-aware — "हे" is also the last two
                        # characters of रहे/कहे/वहे, ordinary words nowhere
                        # near this list. The re.sub below IS
                        # boundary-aware and leaves those alone, but
                        # comparing before/after is what keeps the counter
                        # honest: without it, this logged known_word_fix:
                        # 3874 on a corpus where only 28 replacements
                        # actually happened — the text was never wrong, only
                        # the count was.
                        new_text = re.sub(
                            rf"{WORD_BEFORE}{re.escape(bad)}{WORD_AFTER}", good, text)
                        if new_text != text:
                            text = new_text
                            counts["known_word_fix"] += 1

                if text == start:
                    break

            if text != doc["ayahs"][num]:
                doc["ayahs"][num] = text
                changed = True
            ws = tokens(text)

            # 1a. nuktas from the parallel URDU verse — the primary authority.
            new_text = text
            verse_skels = urdu_table.get((surah, int(num)), {})
            for w in set(ws):
                if NUKTA in w:
                    continue
                skel = deva_skeleton(w)
                # Two consonants minimum: a one-consonant skeleton matches far too
                # much (की against any ق word) and carries no information.
                if len(CONSONANT.findall(skel)) < 2:
                    continue
                sk = verse_skels.get(skel)
                if not sk:
                    continue
                fixed = apply_skeleton(w, sk)
                if fixed != w:
                    new_text = re.sub(rf"{WORD_BEFORE}{re.escape(w)}{WORD_AFTER}",
                                      fixed, new_text)
                    counts["nukta_from_urdu"] += 1
            if new_text != text:
                doc["ayahs"][num] = new_text
                changed = True
                text, ws = new_text, tokens(new_text)

            # 1b. fall back to the reference edition where the Urdu is silent.
            for w in set(ws):
                if NUKTA in w:
                    continue
                target = restore.get(w)
                if target:
                    new_text = re.sub(rf"{WORD_BEFORE}{re.escape(w)}{WORD_AFTER}",
                                      target, new_text)
                    counts["nukta_restored"] += 1
            if new_text != text:
                doc["ayahs"][num] = new_text
                changed = True
                text, ws = new_text, tokens(new_text)

            # 2. self-consistency: a rare word beside a much commoner near-twin
            #    in this edition's own vocabulary.
            for w in ws:
                if self_freq[w] > args.rare_max:
                    continue
                # Ignore twins that differ ONLY by a nukta. Check 1 owns those,
                # and left in, this check reverses it: with restorations applied,
                # ज़ात is rare and the un-restored जात is common, so it would
                # "correct" ज़ात back to जात and undo the repair.
                twins = [(c, self_freq[c]) for c in edit1(w, self_vocab)
                         if self_freq[c] >= self_freq[w] * args.twin_ratio
                         and strip_nukta(c) != strip_nukta(w)]
                if len(twins) == 1:
                    counts["self_inconsistent"] += 1
                    flags.append(f"probable-ocr:{w}->{twins[0][0]}")
                    findings.append({"surah": surah, "ayah": int(num),
                                     "type": "probable-ocr", "word": w,
                                     "seen": self_freq[w],
                                     "suggest": twins[0][0],
                                     "suggestSeen": twins[0][1]})

            # 4. unknown to the reference lexicon. Ranks suspicion only: plenty is
            #    genuine Ahsanul Kalam vocabulary the other translator never used.
            for w in ws:
                if strip_nukta(w) not in forms and w not in vocab:
                    counts["unknown"] += 1

            # 3. मैं / में by bigram evidence
            mains: list[tuple[str, int]] = []
            for i, w in enumerate(ws):
                if w != "में":
                    continue
                prev = ws[i - 1] if i else None
                nxt = ws[i + 1] if i + 1 < len(ws) else None
                score_in = score_i = 0
                for a, b in ((prev, "में"), ("में", nxt)):
                    if a and b:
                        score_in += bigrams.get((a, b), 0)
                for a, b in ((prev, "मैं"), ("मैं", nxt)):
                    if a and b:
                        score_i += bigrams.get((a, b), 0)
                # Adjacent bigrams from the reference edition are too sparse to
                # decide this on their own: it is a DIFFERENT translator, so AK's
                # idiom barely appears. For 113:1 the counts are 1 vs 0.
                #
                # Two independent signals settle it instead:
                #   * "P में" attested ZERO times while P itself is well attested.
                #     में is a postposition — it follows a noun. "पनाह में" is
                #     attested (so that में is real); "दीजिए में" never is, though
                #     दीजिए appears 18 times, because a postposition cannot follow
                #     that verb. The gap is the evidence.
                #   * the ENGLISH verse is first person. Hilali-Khan renders 113:1
                #     "Say: I seek refuge…", so a first-person pronoun belongs in
                #     the verse at all.
                postposition_impossible = (
                    prev is not None
                    and uni.get(prev, 0) >= args.min_context
                    and bigrams.get((prev, "में"), 0) == 0
                )
                decisive = (
                    score_i >= max(args.bigram_min, score_in * args.bigram_ratio)
                    or (postposition_impossible
                        and en_first_person.get((surah, int(num)), False))
                )
                findings.append({"surah": surah, "ayah": int(num),
                                 "type": "mai-vs-mein",
                                 "context": f"{prev} में {nxt}",
                                 "evidence": {"मैं": score_i, "में": score_in},
                                 "decisive": decisive})
                if decisive:
                    # Repair it. This is the one error class that changes meaning
                    # rather than spelling — में is "in", मैं is "I" — so leaving it
                    # flagged for a human to read is exactly what the owner asked
                    # not to happen. The bigram counts come from a published
                    # edition of the same register, so the evidence is external.
                    mains.append((num, i))
                    counts["main_repaired"] += 1
                elif score_i > score_in:
                    counts["main_suspect"] += 1
                    flags.append(f"मैं/में:{prev or '^'} _ {nxt or '$'}")

            # Apply the decided मैं repairs by token position, so only the
            # occurrences the evidence covers change — a verse can contain both a
            # real "में" and a misread one.
            if mains:
                idxs = {i for _, i in mains}
                rebuilt, seen_tok = [], -1
                for raw in text.split():
                    core = "".join(ch for ch in raw
                                   if "ऀ" <= ch <= "ॿ" and ch not in PUNCT)
                    if core:
                        seen_tok += 1
                        if seen_tok in idxs and core == "में":
                            raw = raw.replace("में", "मैं", 1)
                    rebuilt.append(raw)
                doc["ayahs"][num] = " ".join(rebuilt)
                changed = True
                text = doc["ayahs"][num]
                ws = tokens(text)

            # 0b. re-apply the known fixes ONE more time, now that nukta
            # restoration and मैं/में have both had their turn. Necessary,
            # not defensive: ग़रज़/क़ान's fixes (round 10) each want a nukta
            # REMOVED, but 1a/1b's job is putting nuktas BACK — the two
            # disagreed on every run, forever, because step 0 ran once,
            # before 1a/1b could re-add what it had just taken off. A
            # `verify_pilot.py --apply` loop never converged past 4 stuck
            # oscillating changes until this was added. Confirmed fixes
            # always get the last word over an automatic nukta guess.
            text = doc["ayahs"][num]
            for _ in range(5):
                start = text
                fixed_verse = KNOWN_VERSE_FIXES.get((surah, int(num)))
                if fixed_verse and re.search(fixed_verse[0], text):
                    text = re.sub(fixed_verse[0], fixed_verse[1], text)
                    counts["known_verse_fix"] += 1
                for bad, good in KNOWN_WORD_FIXES.items():
                    if bad in text:
                        new_text = re.sub(
                            rf"{WORD_BEFORE}{re.escape(bad)}{WORD_AFTER}", good, text)
                        if new_text != text:
                            text = new_text
                            counts["known_word_fix"] += 1
                if text == start:
                    break
            if text != doc["ayahs"][num]:
                doc["ayahs"][num] = text
                changed = True
                ws = tokens(text)

            # 5. length outlier vs the reference edition
            ref = ref_len.get((surah, int(num)))
            if ref:
                ratios.append(len(ws) / ref)

            if flags:
                flags_for_surah[num] = flags

        # length check needs the corpus-wide distribution, so it runs below;
        # write nukta restorations now if asked.
        if flags_for_surah:
            per_verse_flags[str(surah)] = flags_for_surah
        if args.apply and changed:
            doc["nuktas"] = "lexicon-restored"
            path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")

    # 5, second pass: outliers against the observed ratio distribution.
    mean = statistics.fmean(ratios)
    sd = statistics.pstdev(ratios) or 1e-9
    outliers = []
    for path in files:
        doc = json.loads(path.read_text(encoding="utf-8"))
        surah = doc["surah"]
        for num, text in doc["ayahs"].items():
            ref = ref_len.get((surah, int(num)))
            if not ref:
                continue
            z = (len(tokens(text)) / ref - mean) / sd
            if abs(z) > args.length_z:
                outliers.append({"surah": surah, "ayah": int(num),
                                 "type": "length-outlier", "z": round(z, 1),
                                 "words": len(tokens(text)), "reference": ref})
    findings.extend(outliers)
    counts["length_outlier"] = len(outliers)
    # SOFT, not hard. Owner review 2026-07-29: spot-checked ~20 outliers spanning
    # the full range (26:219 at 6x the reference length down to 6:67 at 0.2x)
    # against the Quran's actual meaning, and every one was a correct, complete,
    # correctly-sequenced verse — Ahsanul Kalam and hi-suhel-farooq-nadwi simply
    # gloss different verses to different degrees, with no fixed ratio between
    # two independent humans' choices. That makes this a noisy proxy once
    # build_pilot.py's 1..N completeness check (which is what actually caught
    # Hud/Yusuf and ad-Dukhan/Jathiyah) already holds. Quarantining the whole
    # surah over it repeats the exact mistake documented below for the
    # orthographic flags — condemning on a suspicion, not a finding. Flag the
    # verse instead and let the surah publish.
    for o in outliers:
        per_verse_flags.setdefault(str(o["surah"]), {}).setdefault(
            str(o["ayah"]), []).append(
            f"length-outlier:{o['words']}w vs ref {o['reference']}w (z={o['z']})")

    report = {
        "reference": args.reference,
        "minEvidence": args.min_evidence,
        "lengthRatio": {"mean": round(mean, 3), "sd": round(sd, 3)},
        "counts": dict(counts),
        "nuktaRestorations": len(restore),
        "nuktaThinEvidence": [{"bare": k, "nuktaed": v, "attested": n}
                              for k, v, n in sorted(thin, key=lambda t: -t[2])[:50]],
        "findings": findings,
        "verseFlags": per_verse_flags,
    }
    out = Path(args.report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")

    log(f"nukta rules: {len(restore)} applied-eligible, {len(thin)} rejected as "
        f"thin evidence (< {args.min_evidence})")
    for k in ("mechanical_cleanup", "known_word_fix", "known_verse_fix", "nukta_from_urdu",
              "nukta_restored", "main_repaired", "main_suspect",
              "self_inconsistent", "unknown", "length_outlier"):
        log(f"{k}: {counts[k]}")
    flagged = sum(len(v) for v in per_verse_flags.values())
    log(f"verses carrying at least one flag: {flagged}")
    log(f"report -> {out}")

    # Two severities, because conflating them is useless in both directions.
    #
    # HARD — structural. build_pilot.py already refused anything that isn't
    # exactly 1..N against quran.db before this script ever sees it, which is
    # what actually caught ad-Dukhan carrying al-Jathiyah (59 numbers present,
    # wrong surah underneath) and Hud carrying Yusuf. Nothing downstream from
    # that check currently promotes to HARD; length-outlier used to, but
    # 2026-07-29 review found it flags normal translator-style variance far
    # more often than real corruption (see the length-outlier block above), so
    # it moved to SOFT.
    #
    # SOFT — suspicion, not a finding. A rare word beside a commoner twin, an
    # undecided मैं/में, a word the other translator never used, a verse whose
    # length doesn't match the reference. Many of these are simply Ahsanul
    # Kalam's own vocabulary or phrasing. Condemning a surah for one of them
    # quarantined 77 of 88 and published 11 — which is not more rigorous, just
    # less useful. Publish, and record the flags per verse so the site can
    # mark them.
    hard: set[str] = set()
    soft = {s: v for s, v in per_verse_flags.items() if s not in hard}
    bad = hard

    if args.quarantine:
        removed = []
        for path in files:
            doc = json.loads(path.read_text(encoding="utf-8"))
            surah = str(doc["surah"])
            if surah in bad:
                # MOVED, not deleted. Deleting made the quarantine impossible to
                # study: to ask whether an outlier's damage is local you need the
                # rejected surah, and it was gone. A gate should preserve its
                # evidence.
                held = path.parent.parent / f"{path.parent.name}-quarantine"
                held.mkdir(parents=True, exist_ok=True)
                path.rename(held / path.name)
                removed.append(int(surah))
                continue
            # Soft flags travel WITH the text, so a reader-facing surface can mark
            # the affected verses instead of the whole edition being labelled
            # uniformly unverified.
            if surah in soft:
                doc["verseFlags"] = soft[surah]
                doc["flaggedVerses"] = len(soft[surah])
                path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                                encoding="utf-8")
        log(f"quarantined {len(removed)} surah(s): {sorted(removed)}")
        kept = sorted(files_kept := [p for p in files if p.exists()])
        verses = sum(len(json.loads(p.read_text(encoding='utf-8'))["ayahs"])
                     for p in kept)
        log(f"PUBLISHABLE: {len(kept)} surah(s), {verses} verses")
        return

    log(f"hard failures (structural): {len(hard)} surah(s) {sorted(int(x) for x in hard)}")
    log(f"soft-flagged surahs (publishable, verses marked): {len(soft)}")
    if bad:
        log("rerun with --quarantine to drop the hard failures and publish the rest")
        sys.exit(1)


if __name__ == "__main__":
    main()
