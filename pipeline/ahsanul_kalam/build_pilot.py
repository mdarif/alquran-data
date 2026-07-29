#!/usr/bin/env python3
"""Build a few Ahsanul Kalam surahs as a web pilot — not a full ingestion.

Owner decision 2026-07-28: see a handful of Hindi chapters on `al-quran-web`
before committing to the whole 661-page corpus, quran.db, or R2. So this emits
per-surah JSON in the shape the site's existing Roman Urdu pilot already
consumes (`al-quran-web/docs/roman-urdu-pilot.md`): drop a file in, run the
site's export, no code changes.

Reads the line manifest produced by `extract_lines.py` and OCRs only the pages
the requested surahs occupy.

Two OCR passes, because tesseract's failure modes here are complementary:
  * `-l hin`      — Devanagari is near-exact, digits are wrong (1 -> । or |)
  * `-l eng+hin`  — digits are right, Devanagari degrades badly (रहम -> TA)
Text comes from the first, verse numbers from the second. Measured on AQ2 pages
1-9: al-Fatiha 1-7 exact and al-Baqarah 1-61 with one error, which the sequence
check below catches by itself.

Guards, since every failure mode here is silent — bad output reads as plausible
Hindi rather than crashing:
  * only 83px strips (the translation body) are read. The 72px footnote text and
    48px superscript markers are excluded, so footnote numbers can never be
    mistaken for verse numbers.
  * the verse sequence must be exactly 1..N with no gaps, and N must match the
    ayah count in quran.db. A surah that fails is refused, not published — the
    site's pilot is all-or-nothing per surah for the same reason.

NOT DONE HERE — nukta restoration. The owner's decision is to store the
fully-nuktaed form (lexical restoration via `alquran-roman-urdu`), but OCR drops
nuktas on क/ख/ग/ज/फ and the print itself is inconsistent, so the pilot text is
marked `beta-unverified` and carries `nuktas: unrestored`. Do not present it as
the final text, and do not use it as a lexicon witness.

Usage:
    python pipeline/ahsanul_kalam/build_pilot.py --surahs 1,112,113,114
"""
from __future__ import annotations

import argparse
import itertools
import json
import re
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
import sqlite3
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

BODY_PX = 83    # translation body
TITLE_PX = 103  # centred surah title, e.g. "सूरह इख्लास-112" — the boundary marker
VERSE_RE = re.compile(r"\((\d{1,3})\)")

# A verse-marker SLOT in the `hin` pass, whose digits are unreliable by design:
# "(1)" comes back as "(])", "(।)", "(|)" or bare "()". Matching only digits meant
# a line containing "(])" had one slot fewer than the digit pass reported, so the
# whole line was left unspliced and its verse vanished — this is what cost verse 1
# in a dozen surahs.
#
# So: any short parenthesised run that contains no Devanagari LETTER. The
# lookahead is what keeps the edition's bracketed glosses — (प्रशंसायें), (खुद),
# and the "(यह मक्की सूरत है…)" subtitle — from being mistaken for verse numbers
# and overwritten with digits.
SLOT_RE = re.compile(
    r"\((?![^)]*[ऄ-हा-्])(?:[^()]{0,4}|\d{1,3}[\]\[|!lI.,।:;'\"]{1,2})\)"
    r"|(?<=[\s।])\d{1,3}\)"
    r"|\(श\)")
# Second alternative: the marker's OWN OPEN PAREN, not the digits, went missing.
# 79:39 printed as "। 39)" — tesseract dropped the "(" entirely, so even the
# widened first alternative never sees an opening bracket to anchor on, and the
# whole verse silently fused into its predecessor (same failure class as
# 2:237, confirmed against the source scan). Requiring the digits be preceded
# by whitespace or a danda is what keeps this from firing inside a normal
# gloss: "(निकट)" never leaves a bare digit run sitting after a space.
#
# Third alternative is a literal, not a class: 12:21's marker OCR'd as the bare
# consonant "(श)", with no digits at all, so nothing above can catch it —
# widening the Devanagari exclusion to "any single consonant" was tried and
# rejected, because "(न)" already appears a dozen times as GENUINE text across
# already-published surahs (11, 18, 21, 22, 49, 7, 8) and would have been
# swallowed as a false marker. "(श)" as an exact literal does not occur
# anywhere else in the corpus, so it costs only itself.
# Two alternatives, deliberately narrow. Up to three characters of anything
# non-Devanagari (covers "(2)", "()", "(।)" — the mangled markers), OR digits
# followed by one or two stray non-digits, which is how al-Baqarah's verse 221
# arrived: "(229])". At three characters flat that marker went unrecognised and the
# verse merged into its predecessor.
#
# The stray characters are enumerated, not left open. "digits plus any one or two
# non-digits" was tried and also regressed the corpus (to 99 surahs) — it admitted
# things that are not markers. Only the characters OCR actually confuses with
# marker punctuation are allowed.
#
# Simply allowing five characters of anything was tried first and regressed
# from 110 surahs to 101: non-markers started matching, every subsequent verse
# shifted, and the shortfall surfaced as verses missing in clumps ([43,44],
# [25,26,27]). Requiring a digit to lead the longer form is what keeps that out.
#
# The cap sits at 4, not 3: an image showing a plain, correctly-printed "(33)"
# still came back from tesseract as "(8338)" (4:33), which does not fit "3
# characters of anything" or "a digit run plus 1-2 stray chars" — it is 4
# straight digits, no stray characters at all. Confirmed against the source
# scan, not guessed. The lookahead still excludes Devanagari, so this cannot
# admit a real bracketed gloss; it only widens the room for glyph-level noise.

# Every surah opens with a parenthesised descriptor — "(यह मदनी सूरत है इसमें 73
# आयतें और 9 रूकू हैं)". It carries no verse marker, so when it belongs to the NEXT
# surah it lands after the current run's last marker and is absorbed into the final
# verse, dragging the following bismillah with it. Cutting at the last danda does
# not help: the bismillah ends in one, so the trim keeps the lot.
#
# The descriptor is unambiguous — anything from it onward belongs to the next
# surah, never to this verse. It also states the verse count, which is worth
# harvesting as the book's own check on quran.db some day.
SUBTITLE_RE = re.compile(r"\(\s*यह\s[^)]{0,80}?(?:सूरत|सूरह)\s[^)]{0,80}?\)")

# How far ahead a printed verse number may sit before it stops being read as
# "markers were missed just before this" and starts being read as a misread digit.
MAX_MARKER_GAP = 4


def log(msg: str) -> None:
    print(f"[ak-pilot] {msg}", flush=True)


def tess(img: Path, lang: str, psm: str = "7") -> str:
    out = subprocess.run(
        ["tesseract", str(img), "-", "-l", lang, "--psm", psm],
        capture_output=True, text=True,
    )
    return out.stdout.strip()


def load_manifest(src: Path) -> list[dict]:
    path = src / "lines.jsonl"
    if not path.exists():
        sys.exit(f"no manifest at {path} — run extract_lines.py first")
    return [json.loads(l) for l in path.open(encoding="utf-8")]


def in_reading_order(rows: list[dict]) -> list[dict]:
    """Every line of the corpus in reading order.

    Files sort AQ1..AQ6, then page, then down the page, then left to right. Paint
    order is useless across a page (it groups by text frame), so ordering is done
    from geometry.
    """
    return sorted(rows, key=lambda r: (r["file"], r["pdf_page"], -r["top"], r["x"]))


def align_titles(readings: list[int | None],
                 titles: list[tuple[int, str]]) -> dict[int, int]:
    """Assign title strips to surah numbers by monotone alignment.

    Titles appear in book order, so the mapping must be strictly increasing. What
    it must NOT be is greedy: a single title misread high — "GE अहजाब-85" for
    surah 33 — is a legal forward jump, and accepting it strands every surah
    between. Both greedy variants tried before this failed that way, one taking
    the raw reading and one preferring the successor.

    So score every (title, surah) pairing and take the best increasing assignment
    by DP: an exact digit match scores 2, a match after the systematic 5→3 repair
    scores 1, anything else 0. Titles may be skipped, since ~4 surahs have no
    103px title strip at all. One bad reading then costs only itself — the
    surrounding agreements outvote it.
    """
    n, m = len(readings), 114
    repaired = [None if r is None else int(str(r).replace("5", "3"))
                for r in readings]

    def score(i: int, surah: int) -> int:
        if readings[i] == surah:
            return 2
        if repaired[i] == surah:
            return 1
        # A TRUNCATED read. "सूरह तीन-95" came back as "सूरह तीन-9" — the last digit
        # dropped — and because 9 was already taken the title was discarded and
        # at-Tin refused, though the page prints its number perfectly plainly. Give
        # partial credit when one reading is a prefix of the other; ambiguity (9
        # could be 9, 90..99) is resolved by the surrounding exact matches and by
        # the assignment having to stay monotone.
        r = readings[i]
        if r is not None:
            a, b = str(r), str(surah)
            if a != b and (a.startswith(b) or b.startswith(a)):
                return 1
        return 0

    # dp[i][j] = best total score using titles i.. against surahs j..
    dp = [[0] * (m + 2) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m, 0, -1):
            skip_surah = dp[i][j + 1]
            take = score(i, j) + dp[i + 1][j + 1]
            skip_title = dp[i + 1][j]
            dp[i][j] = max(take, skip_surah, skip_title)

    index: dict[int, int] = {}
    unassigned: list[tuple[int, str]] = []
    i, j = 0, 1
    while i < n and j <= m:
        if dp[i][j] == score(i, j) + dp[i + 1][j + 1] and score(i, j) > 0:
            index[j] = titles[i][0]
            i += 1
            j += 1
        elif dp[i][j] == dp[i][j + 1]:
            j += 1
        else:
            unassigned.append(titles[i])
            i += 1

    # ELIMINATION. A strip whose number is unreadable is still pinned by its
    # neighbours: titles are strictly ordered, so the strips falling between two
    # assigned titles can only be the free numbers in that interval, in order.
    # "GE अहजाब-85" (al-Ahzab, 33) and "सूरह सबा-$4" (Saba, 34) are past rescuing by
    # digit similarity — but they sit consecutively between titles 32 and 35, and
    # two strips for two free numbers has exactly one ordered solution.
    #
    # Handling only the single-strip case was not enough: the unreadable titles
    # come in adjacent pairs, so each still saw two candidates and both were
    # refused.
    brackets: dict[tuple[int, int], list[tuple[int, str]]] = {}
    for pos, text in unassigned:
        before = max((n for n in index if index[n] < pos), default=0,
                     key=lambda n: index[n])
        after = min((n for n in index if index[n] > pos), default=115,
                    key=lambda n: index[n])
        brackets.setdefault((before, after), []).append((pos, text))
    for (before, after), strips in brackets.items():
        free = [n for n in range(before + 1, after) if n not in index]
        if len(free) == len(strips):
            for (pos, text), n in zip(sorted(strips), free):
                index[n] = pos
                log(f"  title {text!r} -> surah {n} by elimination "
                    f"(between {before} and {after})")
        else:
            for pos, text in strips:
                log(f"  unaligned title at stream {pos}: {text!r} — "
                    f"{len(strips)} strips for {len(free)} free numbers {free}, "
                    f"so refused")
    return index


def title_index(rows: list[dict], src: Path, cache: Path) -> dict[int, int]:
    """Map surah number -> its index in the reading-order stream.

    Boundaries come from the centred title strips ("सूरह इख्लास-112"), not from
    the page header. Two reasons the header cannot do this job:
      * a page carries the surah at the left margin AND the juz at the right
        ("पारा - 2"), so reading the page's headers together yields the juz;
      * a single page routinely holds the end of one surah and the start of the
        next, so page granularity cannot separate them — surah 112 and 113 share
        a page, and 113 would be lost entirely.
    Only ~110 strips corpus-wide, so this is cheap; cached because it never changes.

    The number printed in the title is NOT trusted on its own. Tesseract misreads
    3 as 5 with total consistency here — 13→15, 23→25, 43→45, 63→65, 73→75, 83→85,
    93→95 — and a handful of titles garble entirely (सूरह सबा-$4). Trusting the
    digits mapped eleven surahs onto numbers already taken, which silently dropped
    them AND let the surah before each one swallow the following text.

    Titles are strictly ordered in the book, so ORDER is the reliable signal and
    the digits are only corroboration: walk them in stream order and accept a
    number only where it is greater than the last accepted one, trying the 5→3
    repair before giving up. A title that still doesn't fit is left unassigned, so
    its surah is refused rather than guessed at.
    """
    if cache.exists():
        return {int(k): v for k, v in json.loads(cache.read_text()).items()}

    log("indexing surah titles (cached after this)")
    stream = in_reading_order(rows)

    # AQ1 is front matter (the publisher's title page), not surah titles. And a
    # title is sometimes set as two strips on one baseline — 'सूरह तौबा' + '-9' —
    # so group by baseline first or they count as two surahs.
    strips = [(i, r) for i, r in enumerate(stream)
              if r["px_height"] == TITLE_PX and r["file"] != "AQ1"]
    titles = [(grp[0][0], " ".join(tess(src / "img" / r["img"], "eng+hin")
                                   for _, r in grp))
              for grp in (list(g) for _, g in itertools.groupby(
                  strips, key=lambda ir: (ir[1]["file"], ir[1]["pdf_page"],
                                          ir[1]["top"])))]

    readings: list[int | None] = []
    for _, text in titles:
        m = re.search(r"(\d{1,3})\s*$", text.replace("-", " ").strip())
        n = int(m.group(1)) if m else None
        readings.append(n if n and 1 <= n <= 114 else None)

    index = align_titles(readings, titles)

    cache.write_text(json.dumps(index, indent=0))
    log(f"indexed {len(index)}/114 surah titles from {len(titles)} title strips")
    return index


def ocr_all(images: list[str], src: Path, jobs: int) -> dict[tuple[str, str], str]:
    """OCR every (image, lang) pair up front, in parallel.

    tesseract is a subprocess and each strip is independent, so this is pure
    wall-clock win: a juz-sized span is thousands of invocations and serial
    execution makes coverage expansion impractical rather than merely slow.
    Threads, not processes — the work happens in the child process anyway.
    """
    pairs = [(img, lang) for img in images for lang in ("hin", "eng+hin")]
    results: dict[tuple[str, str], str] = {}
    done = 0
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {pool.submit(tess, src / "img" / img, lang): (img, lang)
                   for img, lang in pairs}
        for fut in as_completed(futures):
            results[futures[fut]] = fut.result()
            done += 1
            if done % 500 == 0:
                log(f"  ocr {done}/{len(pairs)}")
    return results


def read_surah(stream: list[dict], src: Path, start: int, end: int,
               ocr: dict[tuple[str, str], str], first_surah: int,
               expected: dict[int, int]) -> tuple[list[dict[int, str]], list[str]]:
    """Split the pre-OCR'd body lines in stream[start:end] into verses.

    Returns (runs, digit_readings) — the runs numbered by marker position, and the
    digit pass's readings for the caller to corroborate against.
    """
    body = [r for r in stream[start:end] if r["px_height"] == BODY_PX]
    chunks: list[str] = []
    readings: list[str] = []
    # One printed line is often several strips (the verse number is set as its
    # own strip), so regroup on the baseline within a page.
    for _, grp in itertools.groupby(
            body, key=lambda r: (r["file"], r["pdf_page"], r["top"])):
        grp = list(grp)
        hin = " ".join(ocr[(r["img"], "hin")] for r in grp)
        num = " ".join(ocr[(r["img"], "eng+hin")] for r in grp)

        # Record the digit pass's reading of each marker for LATER corroboration
        # only — never to place or number a verse. On the eng+hin pass Devanagari
        # glosses come back as Latin gibberish, so "(प्रतिकार)" becomes "(AeA)" and
        # "(अ.क.)" becomes "(AH)" — and since those contain no Devanagari letter,
        # the slot pattern matches them as if they were verse markers. Sometimes the
        # gibberish is even numeric: "(99)" appeared where verse 22 belongs. The two
        # passes then disagree about how many markers a line holds, and the
        # positional splice mis-numbers everything after the first disagreement.
        readings.extend(VERSE_RE.findall(num))
        chunks.append(hin)

    text = " ".join(chunks)
    # Tesseract reads the danda as a pipe often enough to matter, and it is a
    # sentence terminator here — the trailing-material trim below depends on it.
    text = text.replace("|", "।").replace("॥", "।")

    # NUMBER BY POSITION, NOT BY READING THE DIGITS.
    #
    # Verses run 1..N in order, so once the marker POSITIONS are known the numbers
    # follow from their sequence — no digit needs to be read correctly. Finding
    # positions is reliable (the Devanagari pass keeps glosses in Devanagari, so
    # SLOT_RE excludes them); reading three-digit numbers off 297 DPI print is not.
    # Every numbering failure so far came from trusting the digits: 22 read as 29,
    # 32 read as 82, garbled glosses counted as markers.
    #
    # Expected counts come from quran.db, and a span may hold several surahs
    # because ~11 have no printed title — so the slots are dealt out in order:
    # count(S) to surah S, then count(S+1) to the next, and so on. The digits are
    # kept only to CORROBORATE: caller compares them against the positional
    # assignment and refuses the surah if they disagree too often.
    slots = list(SLOT_RE.finditer(text))

    # Number by position, but ANCHOR on the digits the Devanagari pass itself gets
    # right — it renders plenty of them cleanly, "(286)" included.
    #
    # Pure position was not enough. When a marker is missed entirely, every verse
    # after it shifts up by one, and the shortfall surfaces as "missing verses
    # [284, 285, 286]" — the tail — even though the loss happened in the middle.
    # al-Baqarah found 283 markers for 286 verses while its text ran correctly to
    # the very last word of 2:286, so the diagnosis pointed at the wrong end of the
    # surah entirely.
    #
    # An anchor a few ahead of the running count means markers were missed just
    # before it: honour the anchor so everything after it stays aligned, and let the
    # merged verses be caught by the length check rather than dragging the whole
    # surah down.
    parsed: list[int | None] = []
    for m in slots:
        digits = re.sub(r"[^0-9]", "", m.group(0))
        parsed.append(int(digits) if digits else None)

    runs: list[dict[int, str]] = []
    cursor = 0
    surah = first_surah
    gaps = 0
    while cursor < len(slots) and surah in expected:
        want = expected[surah]
        verses: dict[int, str] = {}
        n = 0
        while cursor < len(slots) and n < want:
            expect = n + 1
            v = parsed[cursor]
            # A small forward jump is a missed marker; a big disagreement is a
            # misread digit and the position wins.
            # A forward jump is honoured only if the NEXT printed number confirms
            # it by continuing from there. Trusting a lone jump cost 11 surahs: a
            # verse number misread upward (43 read as 45) looked exactly like a
            # missed marker, so two good verses were skipped and reported missing,
            # in clumps like [43, 44] and [65, 66, 67].
            #
            # One confirming neighbour is not enough. 2:273's own marker misread
            # as "274" and the marker after it happened to read correctly as
            # "275" — so a single-step check confirmed a jump that was never
            # there, and 273 was skipped exactly like the 43-read-as-45 case
            # this guard exists for. Requiring the SECOND neighbour too
            # (v+2 == nxt2_v) catches this: a genuinely missed marker keeps
            # incrementing correctly for the rest of the surah, a lone misread
            # does not coincidentally line up two verses running.
            nxt_v = parsed[cursor + 1] if cursor + 1 < len(parsed) else None
            nxt2_v = parsed[cursor + 2] if cursor + 2 < len(parsed) else None
            confirmed = v is not None and nxt_v == v + 1 and nxt2_v == v + 2
            if confirmed and expect < v <= expect + MAX_MARKER_GAP:
                gaps += v - expect
                n = v
            else:
                n = expect
            body_start = slots[cursor].end()
            nxt = slots[cursor + 1] if cursor + 1 < len(slots) else None
            body_end = nxt.start() if nxt else len(text)
            piece = text[body_start:body_end].strip()
            verses[n] = (verses.get(n, "") + " " + piece).strip() if n in verses else piece
            cursor += 1
        runs.append(verses)
        surah += 1
    if gaps:
        log(f"  {gaps} marker(s) missed and re-anchored from the printed number")

    def tidy(s: str) -> str:
        s = s.replace("‍", "")   # OCR sprinkles ZWJ inside conjuncts (मक्‍की)
        s = re.sub(r"\s+([।,])", r"\1", s)  # strips join with a space before the danda
        return re.sub(r"\s+", " ", s).strip()

    cleaned = []
    for run in runs:
        out = {k: tidy(v) for k, v in run.items()}
        if out:
            # The last verse of a run absorbs whatever the page puts after it —
            # for al-Nas that was the index heading "फेहरिस्त मजामिने कुरआन",
            # appended to verse 6 where nothing would flag it. Verses end in a
            # danda, so anything trailing the final one is not part of the verse.
            last = max(out)
            # Cut the next surah's opening matter first, then trim to the final
            # danda. Order matters: the danda trim alone keeps everything, because
            # the trailing bismillah ends in a danda of its own.
            m = SUBTITLE_RE.search(out[last])
            if m:
                out[last] = out[last][:m.start()].strip()
            if "।" in out[last]:
                out[last] = out[last][:out[last].rfind("।") + 1].strip()
            cleaned.append(out)
    return cleaned, readings


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="sources/ahsanul-kalam")
    ap.add_argument("--db", default="assets/quran.db", help="for expected ayah counts")
    ap.add_argument("--out", default="dist/pilot/ahsanul-kalam")
    ap.add_argument("--surahs", default="1,112,113,114",
                    help="comma list, or a range like 78-114")
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--min-agreement", type=float, default=0.6,
                    help="fraction of the digit pass's readable verse numbers that "
                         "must match the positional numbering")
    args = ap.parse_args()

    if not shutil.which("tesseract"):
        sys.exit("tesseract not found — brew install tesseract tesseract-lang")

    src = Path(args.src)
    rows = load_manifest(src)
    wanted: list[int] = []
    for part in args.surahs.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = (int(x) for x in part.split("-", 1))
            wanted.extend(range(lo, hi + 1))
        else:
            wanted.append(int(part))

    conn = sqlite3.connect(args.db)
    expected = dict(conn.execute(
        "SELECT surah_id, COUNT(*) FROM ayahs GROUP BY surah_id").fetchall())
    conn.close()

    stream = in_reading_order(rows)
    titles = title_index(rows, src, src / "surah-titles.json")
    # A surah runs from its own title to whichever title comes next in the
    # stream — not to the end of the page, and not to the next *numbered* surah,
    # since a title may have been misread.
    starts = sorted(titles.values())

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    ok, refused = [], []

    # Work out every span first, then OCR the whole set in one parallel pass.
    spans: dict[int, tuple[int, int]] = {}
    for surah in wanted:
        start = titles.get(surah)
        if start is None:
            refused.append((surah, "no title strip found for this surah"))
            continue
        later = [i for i in starts if i > start]
        spans[surah] = (start, later[0] if later else len(stream))

    images = [r["img"] for s, e in spans.values()
              for r in stream[s:e] if r["px_height"] == BODY_PX]
    log(f"{len(spans)} surah(s), {len(images)} body lines, "
        f"{len(images) * 2} OCR calls on {args.jobs} threads")
    ocr = ocr_all(images, src, args.jobs)

    # A span may hold SEVERAL surahs, because ~11 have no title strip. Each run of
    # verse numbering in the span is one surah, taken in order from the anchor —
    # so a title-less surah is recovered from the numbering rather than lost, and
    # its text stops being appended onto its predecessor's.
    # offset 0 is the run that starts at the surah's OWN title; later offsets are
    # surahs recovered from this span's overrun because the book printed no title
    # for them.
    candidates: dict[int, tuple[int, dict[int, str]]] = {}
    candidates_readings: dict[int, list[str]] = {}
    for surah, (start, end) in spans.items():
        log(f"surah {surah}: lines {start}-{end} "
            f"({stream[start]['file']} p{stream[start]['pdf_page']})")
        runs, readings = read_surah(stream, src, start, end, ocr, surah, expected)
        if len(runs) > 1:
            log(f"  {len(runs)} numbering runs in this span — the book prints no "
                f"title for the surah(s) after {surah}")
        for offset, run in enumerate(runs):
            n = surah + offset
            candidates_readings.setdefault(n, readings if offset == 0 else [])
            # PREFER THE ANCHORED READING. Keeping whichever candidate appeared
            # first looked equivalent and was not: candidates are generated in
            # span order, so surah N's overrun produces the N+1 candidate BEFORE
            # surah N+1's own span does. Every surah following a split therefore
            # took its predecessor's leftover — often empty — and was refused with
            # "missing verses [1..N]" while its correct text was discarded as a
            # duplicate. That alone cost 20 surahs.
            prev = candidates.get(n)
            if prev is None or offset < prev[0]:
                candidates[n] = (offset, run)

    for surah in sorted(candidates):
        offset, verses = candidates[surah]
        if surah not in wanted:
            continue
        want = expected.get(surah)

        # Refuse anything that isn't exactly 1..N. A partial or misnumbered surah
        # would render as plausible Hindi with a verse quietly missing.
        problems = []
        if want is None:
            problems.append("surah not in quran.db")
        else:
            missing = [n for n in range(1, want + 1) if n not in verses]
            extra = [n for n in verses if n < 1 or n > want]
            if missing:
                problems.append(f"missing verses {missing}")
            if extra:
                problems.append(f"out-of-range verses {extra}")
            # CORROBORATION. Numbering comes from marker order, so a wrong number
            # can no longer be detected by a gap — the sequence is 1..N by
            # construction. What CAN go wrong is a missed or spurious marker,
            # which shifts every verse after it while still numbering perfectly.
            # The digit pass is an independent witness: it misreads individual
            # numbers, but it does not systematically agree with a shifted
            # sequence. Require most of its readable numbers to match.
            digits = [int(d) for d in candidates_readings.get(surah, [])
                      if d.isdigit()]
            in_range = [d for d in digits if 1 <= d <= want]
            if in_range:
                agree = sum(1 for d in in_range if d in verses)
                ratio = agree / len(in_range)
                if ratio < args.min_agreement:
                    problems.append(
                        f"digit pass corroborates only {ratio:.0%} of the "
                        f"positional numbering ({agree}/{len(in_range)})")
        if problems:
            refused.append((surah, "; ".join(problems)))
            log(f"  surah {surah} REFUSED: {'; '.join(problems)}")
            continue

        payload = {
            "surah": surah,
            "status": "beta-unverified",
            "nuktas": "unrestored",
            "source": ("Ahsanul Kalam — Hindi translation by Shaikh Muhammad Rais "
                       "Qureshi, publisher Alkhair, Indore. OCR of the publisher's "
                       "master PDF."),
            "note": ("PILOT / ILLUSTRATIVE. Machine OCR, not reviewed. Nuktas are "
                     "unrestored (क़/ज़/फ़ may appear without the dot). Known OCR "
                     "class that CHANGES MEANING: मैं ('I') read as में ('in') — "
                     "check every first-person verse. Licence from Alkhair, Indore "
                     "is NOT yet granted — do not publish beyond an internal "
                     "preview."),
            "ayahs": {str(n): verses[n] for n in range(1, want + 1)},
        }
        path = out_dir / f"surah-{surah:03d}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        ok.append(surah)
        log(f"  ok: {want} verses -> {path}")

    log(f"done: {len(ok)} surah(s) written {ok}")
    for surah, why in refused:
        log(f"refused surah {surah}: {why}")


if __name__ == "__main__":
    main()
