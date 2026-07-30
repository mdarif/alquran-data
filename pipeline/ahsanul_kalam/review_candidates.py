#!/usr/bin/env python3
"""Find and track candidate OCR errors in the Ahsanul Kalam pilot, across
sessions, without re-scanning from scratch or re-litigating a word already
decided.

Why this exists: `verify_pilot.py`'s self-consistency check can find rare
words near a common near-twin, but CANNOT safely decide whether a candidate
is OCR damage or genuine Hindi grammar/vocabulary — matras carry gender,
number, and tense, so most candidates turn out to be legitimate distinct
words (गया/गयी, बंद/बाद, मूल/माल), not errors. That decision needs someone
(or something) that can read the verse and knows what it's supposed to mean.
Every fix in KNOWN_WORD_FIXES/KNOWN_VERSE_FIXES this project has was decided
that way, one at a time — this script is that same process, formalized:

  1. `scan`   — find candidates across every known suspicious-pattern class
               (matra-twins, stray Devanagari digits standing in for a
               letter, halant-fragments, stray punctuation mid-word) that
               have not already been reviewed or already fixed in
               verify_pilot.py, and print them with just enough verse
               context to judge — not the full verse (this is licensed
               translation text; keep excerpts short).
  2. `mark`   — record a decision (confirmed / rejected / ambiguous) so a
               future `scan` never re-surfaces it. This is the part a human
               or an LLM reading each candidate still has to do — nothing
               here decides FOR you, it just stops making you redo the
               bookkeeping.
  3. `export` — print ready-to-paste KNOWN_WORD_FIXES/KNOWN_VERSE_FIXES
               dict entries for everything marked "confirmed" that isn't in
               verify_pilot.py yet.
  4. `stats`  — counts by status and class.

State persists in `review_state.json` next to this script (tracked in git —
small, and losing it means re-deciding everything from scratch).

    python3 review_candidates.py scan --class matra-twin --limit 40
    python3 review_candidates.py mark शेतानों confirmed शैतानों --note "devils, matra slip"
    python3 review_candidates.py mark कोमों confirmed क़ौमों --surah 16 --ayah 63
    python3 review_candidates.py export
    python3 review_candidates.py stats
"""
from __future__ import annotations

import argparse
import collections
import glob
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
STATE_PATH = HERE / "review_state.json"
PILOT_DIR = HERE.parent.parent / "dist" / "pilot" / "ahsanul-kalam"

MATRAS = "़ािीुूेैोौंृ्"
PUNCT = "।॥ः"


def log(msg: str) -> None:
    print(f"[ak-review] {msg}", flush=True)


def tokens(text: str) -> list[str]:
    out = []
    for raw in re.split(r"\s+", text.strip()):
        core = "".join(ch for ch in raw if "ऀ" <= ch <= "ॿ" and ch not in PUNCT)
        if core:
            out.append(core)
    return out


def load_state() -> dict:
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    return {"reviewed": {}}


def save_state(state: dict) -> None:
    STATE_PATH.write_text(
        json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")


def known_fixes() -> tuple[set[str], set[tuple[int, int]]]:
    """Words/verses verify_pilot.py already fixes, so scan never re-surfaces
    them. Imported, not re-implemented, so this can't drift out of sync."""
    sys.path.insert(0, str(HERE))
    import verify_pilot as vp
    words = set(vp.KNOWN_WORD_FIXES) | set(vp.KNOWN_WORD_FIXES.values())
    verses = set(vp.KNOWN_VERSE_FIXES)
    return words, verses


def load_corpus() -> dict[tuple[int, int], str]:
    if not PILOT_DIR.exists():
        sys.exit(f"no built pilot at {PILOT_DIR} — run build_pilot.py first")
    verses: dict[tuple[int, int], str] = {}
    for f in sorted(glob.glob(str(PILOT_DIR / "surah-*.json"))):
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        for num, text in d["ayahs"].items():
            verses[(d["surah"], int(num))] = text
    return verses


def context(text: str, word: str, width: int = 15) -> str:
    """A short window around the word, NOT the full verse — this is
    licensed translation text, and a scan/review pass only needs enough to
    judge one word, not to reproduce the verse."""
    i = text.find(word)
    if i < 0:
        return ""
    return text[max(0, i - width):i + len(word) + width]


# --- detectors --------------------------------------------------------------
# Each yields (word_or_key, cls, suggestion, locs) where word_or_key is a bare
# word for word-level candidates, or "surah:ayah" for verse-anchored ones
# whose fix depends on position, not just the string.

def detect_matra_twins(corpus: dict[tuple[int, int], str]):
    freq: collections.Counter = collections.Counter()
    locs: dict[str, list] = collections.defaultdict(list)
    for (s, a), text in corpus.items():
        for w in tokens(text):
            freq[w] += 1
            if len(locs[w]) < 3:
                locs[w].append((s, a, context(text, w)))
    vocab = set(freq)

    def twins(word: str) -> set[str]:
        hits = set()
        for i, ch in enumerate(word):
            if ch not in MATRAS:
                continue
            for cand_ch in MATRAS:
                if cand_ch == ch:
                    continue
                cand = word[:i] + cand_ch + word[i + 1:]
                if cand in vocab and cand != word:
                    hits.add(cand)
        return hits

    candidates = []
    for w, c in freq.items():
        if c > 6:
            continue
        for cand in twins(w):
            cc = freq[cand]
            if cc >= max(6, c * 3):
                candidates.append((w, "matra-twin", cand, cc / max(c, 1),
                                    locs[w]))
    candidates.sort(key=lambda t: -t[3])
    for w, cls, cand, _ratio, l in candidates:
        yield w, cls, cand, l


def detect_digit_glyphs(corpus: dict[tuple[int, int], str]):
    """A Devanagari digit (०-९) embedded inside a word, standing in for a
    misread letter — confirmed pattern for ६ (as ध) and ० (as े) so far."""
    pat = re.compile(r"[ऀ-ॿ]*[०-९][ऀ-ॿ]+|[ऀ-ॿ]+[०-९][ऀ-ॿ]*")
    for (s, a), text in corpus.items():
        for m in pat.finditer(text):
            w = m.group(0)
            if any(ch.isspace() for ch in w):
                continue
            yield w, "digit-glyph", None, [(s, a, context(text, w))]


def detect_halant_fragments(corpus: dict[tuple[int, int], str]):
    """A short token (<=3 chars) ending in a bare halant with nothing
    after it — often a truncated root (अज्→अज्र) or a nukta misread as a
    halant (हक्→हक़), per the confirmed cases already in verify_pilot.py."""
    for (s, a), text in corpus.items():
        for w in tokens(text):
            if len(w) <= 4 and w.endswith("्"):
                yield w, "halant-fragment", None, [(s, a, context(text, w))]


def detect_stray_punct(corpus: dict[tuple[int, int], str]):
    """Punctuation that has no business appearing mid-phrase — a semicolon
    or an apostrophe-like character sitting where a space or nothing
    should be (कर ; के, अंध् 'रों — both confirmed strip-boundary
    artifacts)."""
    pat = re.compile(r"[ऀ-ॿ]\s*[;\x27‘’]\s*[ऀ-ॿ]")
    for (s, a), text in corpus.items():
        for m in pat.finditer(text):
            span = text[max(0, m.start() - 8):m.end() + 8]
            yield span, "stray-punct", None, [(s, a, span)]


# 2026-07-30 — two detectors added after the मुक़र्रर incident: round 21
# normalized that word's six competing spellings by picking whichever was
# most FREQUENT in the corpus, which turned out to be exactly backwards —
# OCR was consistently dropping a doubled र, so the wrong spelling was also
# the common one. Frequency-vs-frequency comparison (matra-twin above)
# structurally cannot catch a failure mode that is itself systematic across
# most occurrences of a word. These two instead scan for a SPECIFIC known
# OCR failure signature, corpus-wide, independent of how common the result
# looks — closer to how मिक़ृदार/क़ृसमें/क़ृत्ल/क़ान/गरज़ were actually found
# and fixed this session.

# Genuine Sanskrit/Hindi words that legitimately carry ऋ — everything else
# with ऋ in this Perso-Arabic-loanword-heavy corpus is the spurious-vowel-
# insertion OCR artifact already confirmed for क़ृत्ल->क़त्ल, कान (न as
# क़ान), गरज (as ग़रज़), क़ृसमें->क़ुसमें, मिक़ृदार->मिक़दार. Extend this set
# by hand if a genuine new ऋ-word surfaces as a false positive — do not
# widen it to "any word ending in a common suffix" or similar, the same
# over-broad-rule mistake documented elsewhere in this file's history.
GENUINE_RI_WORDS = {
    "कृपा", "कृत", "कृति", "कृतज्ञ", "कृतघ्न", "दृष्टि", "दृश्य", "वृद्धि",
    "वृक्ष", "मृत", "मृत्यु", "ऋषि", "ऋण", "गृह", "हृदय", "पृथ्वी", "तृप्त",
    "स्मृति", "कृषि", "कृपया", "अमृत", "नृत्य", "गृहस्थ", "वृत्तांत",
}


def detect_spurious_ri(corpus: dict[tuple[int, int], str]):
    """A word containing ऋ that is not a known genuine Sanskrit ऋ-word —
    the corpus-wide version of the spurious-vowel-insertion pattern, found
    independent of how common the corrupted spelling itself is."""
    for (s, a), text in corpus.items():
        for w in tokens(text):
            if "ऋ" not in w:
                continue
            if w in GENUINE_RI_WORDS or any(g in w for g in GENUINE_RI_WORDS):
                continue
            yield w, "spurious-ri", w.replace("ऋ", ""), [(s, a, context(text, w))]


# Combining marks that have no place in standard Hindi/Urdu-loan Devanagari
# orthography for this corpus — Vedic accent marks (udatta ॑ U+0951, anudatta
# ॒ U+0952) that tesseract emits as noise at strip boundaries. Confirmed
# artifact class: हक़॒->हक़, तस्दीक॒->तस्दीक़, मुक़्र॑र (now मुक़र्रर), क़॒समें.
STRAY_MARKS = "॒॑"


def detect_stray_marks(corpus: dict[tuple[int, int], str]):
    """A word carrying a Vedic accent mark — never legitimate in this
    corpus's register, always OCR noise from a strip-boundary artifact."""
    for (s, a), text in corpus.items():
        for w in tokens(text):
            if any(m in w for m in STRAY_MARKS):
                cleaned = "".join(ch for ch in w if ch not in STRAY_MARKS)
                yield w, "stray-mark", cleaned, [(s, a, context(text, w))]


DETECTORS = {
    "matra-twin": detect_matra_twins,
    "digit-glyph": detect_digit_glyphs,
    "halant-fragment": detect_halant_fragments,
    "stray-punct": detect_stray_punct,
    "spurious-ri": detect_spurious_ri,
    "stray-mark": detect_stray_marks,
}


# --- commands ----------------------------------------------------------------

def cmd_scan(args: argparse.Namespace) -> None:
    corpus = load_corpus()
    fixed_words, fixed_verses = known_fixes()
    state = load_state()
    reviewed = state["reviewed"]

    classes = [args.cls] if args.cls else list(DETECTORS)
    seen: set[str] = set()
    shown = 0
    for cls in classes:
        for key, det_cls, suggestion, locs in DETECTORS[cls](corpus):
            if key in seen:
                continue
            seen.add(key)
            if key in fixed_words:
                continue
            if any((s, a) in fixed_verses for s, a, _ in locs):
                continue
            if key in reviewed:
                continue
            print(f"[{det_cls}] {key!r}"
                  + (f" -> {suggestion!r}" if suggestion else "")
                  + f"  ({len(locs)} loc(s))")
            for s, a, ctx in locs[:2]:
                print(f"    {s}:{a}  ...{ctx}...")
            shown += 1
            if shown >= args.limit:
                log(f"stopped at --limit {args.limit}; more may remain")
                return
    log(f"{shown} unreviewed candidate(s) shown")


def cmd_mark(args: argparse.Namespace) -> None:
    state = load_state()
    key = args.word
    entry = {"status": args.status}
    if args.correct:
        entry["correct"] = args.correct
    if args.note:
        entry["note"] = args.note
    if args.surah is not None and args.ayah is not None:
        entry["surah"] = args.surah
        entry["ayah"] = args.ayah
    state["reviewed"][key] = entry
    save_state(state)
    log(f"recorded: {key!r} -> {entry}")


def cmd_stats(args: argparse.Namespace) -> None:
    state = load_state()
    counts = collections.Counter(e["status"] for e in state["reviewed"].values())
    for status, n in counts.most_common():
        log(f"{status}: {n}")
    log(f"total reviewed: {len(state['reviewed'])}")


def cmd_export(args: argparse.Namespace) -> None:
    state = load_state()
    fixed_words, fixed_verses = known_fixes()
    print("# Paste into KNOWN_WORD_FIXES / KNOWN_VERSE_FIXES as appropriate.")
    print("# Every entry below is 'confirmed' in review_state.json but not")
    print("# yet present in verify_pilot.py.")
    for word, entry in sorted(state["reviewed"].items()):
        if entry.get("status") != "confirmed":
            continue
        if word in fixed_words:
            continue
        correct = entry.get("correct", "???")
        note = entry.get("note", "")
        if "surah" in entry and "ayah" in entry:
            if (entry["surah"], entry["ayah"]) in fixed_verses:
                continue
            print(f'    ({entry["surah"]}, {entry["ayah"]}): '
                  f'("{word}", "{correct}"),  # {note}')
        else:
            print(f'    "{word}": "{correct}",  # {note}')


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_scan = sub.add_parser("scan", help="show unreviewed candidates")
    p_scan.add_argument("--class", dest="cls", choices=DETECTORS)
    p_scan.add_argument("--limit", type=int, default=40)
    p_scan.set_defaults(func=cmd_scan)

    p_mark = sub.add_parser("mark", help="record a decision for a candidate")
    p_mark.add_argument("word")
    p_mark.add_argument("status", choices=["confirmed", "rejected", "ambiguous"])
    p_mark.add_argument("correct", nargs="?", default=None,
                         help="the correct spelling, if status is confirmed")
    p_mark.add_argument("--note", default=None)
    p_mark.add_argument("--surah", type=int, default=None,
                         help="set if this fix is verse-anchored, not a bare word")
    p_mark.add_argument("--ayah", type=int, default=None)
    p_mark.set_defaults(func=cmd_mark)

    p_stats = sub.add_parser("stats", help="counts by status")
    p_stats.set_defaults(func=cmd_stats)

    p_export = sub.add_parser("export", help="print confirmed-but-unapplied fixes")
    p_export.set_defaults(func=cmd_export)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
