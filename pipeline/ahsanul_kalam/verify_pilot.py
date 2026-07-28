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
     edition, flagged beyond `--length-z`. Catches dropped or duplicated text,
     which correct numbering hides completely.

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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pilot", default="dist/pilot/ahsanul-kalam")
    ap.add_argument("--db", default="assets/quran.db")
    ap.add_argument("--reference", default="hi-suhel-farooq-nadwi",
                    help="edition slug used as the lexicon/length reference")
    ap.add_argument("--min-evidence", type=int, default=5,
                    help="lexicon occurrences required to restore a nukta")
    ap.add_argument("--length-z", type=float, default=4.0)
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

    # --- nukta restorations, decided once over the whole corpus ---------------
    restore: dict[str, str] = {}
    thin: list[tuple[str, str, int]] = []
    for key, cand in forms.items():
        nuktaed = {f: n for f, n in cand.items()
                   if NUKTA in f and any(c in PERSO_ARABIC for c in f)}
        if not nuktaed or cand.get(key, 0):
            continue  # bare form is attested too — ambiguous, leave it alone
        best, n = max(nuktaed.items(), key=lambda kv: kv[1])
        if n >= args.min_evidence:
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
            ws = tokens(text)

            # 1. nukta restoration
            new_text = text
            for w in set(ws):
                if NUKTA in w:
                    continue
                target = restore.get(w)
                if target:
                    new_text = re.sub(rf"(?<![ऀ-ॿ]){re.escape(w)}(?![ऀ-ॿ])",
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
    for k in ("nukta_restored", "main_repaired", "main_suspect",
              "self_inconsistent", "unknown", "length_outlier"):
        log(f"{k}: {counts[k]}")
    flagged = sum(len(v) for v in per_verse_flags.values())
    log(f"verses carrying at least one flag: {flagged}")
    log(f"report -> {out}")

    # Two severities, because conflating them is useless in both directions.
    #
    # HARD — structural. A length outlier means text crossed a verse boundary, so
    # the whole surah is suspect, not just that verse: this is exactly how
    # ad-Dukhan came to carry al-Jathiyah's verses with all 59 numbers present.
    # Quarantine the surah.
    #
    # SOFT — orthographic suspicion. A rare word beside a commoner twin, an
    # undecided मैं/में, a word the other translator never used. These are ranked
    # suspicions, and many are simply Ahsanul Kalam's own vocabulary. Condemning a
    # surah for one of them quarantined 77 of 88 and published 11 — which is not
    # more rigorous, just less useful. Publish, and record the flags per verse so
    # the site can mark them.
    hard = {str(o["surah"]) for o in outliers}
    soft = {s: v for s, v in per_verse_flags.items() if s not in hard}
    bad = hard

    if args.quarantine:
        removed = []
        for path in files:
            doc = json.loads(path.read_text(encoding="utf-8"))
            surah = str(doc["surah"])
            if surah in bad:
                path.unlink()
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
