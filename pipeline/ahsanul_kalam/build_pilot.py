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
SLOT_RE = re.compile(r"\((?![^)]*[ऄ-हा-्])[^()]{0,3}\)")


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
    i, j = 0, 1
    while i < n and j <= m:
        if dp[i][j] == score(i, j) + dp[i + 1][j + 1] and score(i, j) > 0:
            index[j] = titles[i][0]
            i += 1
            j += 1
        elif dp[i][j] == dp[i][j + 1]:
            j += 1
        else:
            log(f"  unaligned title at stream {titles[i][0]}: {titles[i][1]!r} "
                f"— its surah will be refused")
            i += 1
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
               ocr: dict[tuple[str, str], str]) -> dict[int, str]:
    """Split the pre-OCR'd body lines in stream[start:end] into verses."""
    body = [r for r in stream[start:end] if r["px_height"] == BODY_PX]
    chunks: list[str] = []
    # One printed line is often several strips (the verse number is set as its
    # own strip), so regroup on the baseline within a page.
    for _, grp in itertools.groupby(
            body, key=lambda r: (r["file"], r["pdf_page"], r["top"])):
        grp = list(grp)
        hin = " ".join(ocr[(r["img"], "hin")] for r in grp)
        num = " ".join(ocr[(r["img"], "eng+hin")] for r in grp)

        # Splice the reliable digits into the reliable Devanagari. Both passes see
        # the same marker slots in the same order; the hin pass just renders some
        # of them badly — "(1)" comes back as "()" or "(।)". So collect the slots
        # POSITIONALLY and refill them left to right.
        #
        # Filling the well-formed markers first and the empty ones afterwards
        # (the obvious way) silently swaps verses: on al-Fatiha's opening line
        # `() अल्लाह… (2) तमाम`, the only intact marker is (2), which would take
        # the first digit — putting verse 1's text under 2 and vice versa. That
        # reads perfectly, which is exactly why it has to be done positionally.
        good = VERSE_RE.findall(num)
        slots = list(SLOT_RE.finditer(hin))
        if good and len(slots) == len(good):
            out, last = [], 0
            for slot, digit in zip(slots, good):
                out.append(hin[last:slot.start()])
                out.append(f"({digit})")
                last = slot.end()
            out.append(hin[last:])
            hin = "".join(out)
        elif good:
            # Slot count disagrees between passes — leave the hin text alone and
            # let the verse-sequence guard reject the surah rather than guess.
            pass
        chunks.append(hin)

    text = " ".join(chunks)
    # Tesseract reads the danda as a pipe often enough to matter, and it is a
    # sentence terminator here — the trailing-material trim below depends on it.
    text = text.replace("|", "।").replace("॥", "।")

    # Split into RUNS on a numbering restart. ~11 surahs have no title strip, so
    # the previous surah's span runs straight through them; with duplicate numbers
    # merged into one dict, Surah Yusuf's verses were appended onto Hud's — 11:96
    # carried Yusuf's shirt-on-the-face verse — and the 1..123 check passed
    # because every number was present. A number that fails to advance is a surah
    # boundary the book simply didn't print a title for.
    parts = VERSE_RE.split(text)
    # parts = [pre, num, body, num, body, ...]
    marks = [(int(n), b) for n, b in zip(parts[1::2], parts[2::2])]

    runs: list[dict[int, str]] = []
    current: dict[int, str] = {}
    highest = 0
    i = 0
    while i < len(marks):
        n, body = marks[i]
        if n <= highest:
            # A number that fails to advance is either a new surah the book gave
            # no title, or a single misread digit. Distinguish them by LOOK-AHEAD:
            # a real boundary begins a sustained ascending run.
            #
            # Splitting only on a restart at 1 was not enough. Where the next
            # surah's verse 1 is itself misread — ad-Dukhan into al-Jathiyah — the
            # numbers merely repeat, so no restart is ever seen and the second
            # surah is appended verse-by-verse onto the first. 44:5 carried 45:5.
            ahead = [m[0] for m in marks[i:i + 4]]
            boundary = len(ahead) >= 3 and all(b == a + 1 for a, b
                                               in zip(ahead, ahead[1:]))
            if boundary:
                runs.append(current)
                current, highest = {}, 0
            else:
                # Misread digit mid-surah: keep the text with the verse in
                # progress rather than inventing one out of sequence.
                if highest:
                    current[highest] = (current[highest] + " " + body).strip()
                i += 1
                continue
        current[n] = ((current.get(n, "") + " " + body).strip()
                      if n in current else body.strip())
        highest = max(highest, n)
        i += 1
    runs.append(current)

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
            if "।" in out[last]:
                out[last] = out[last][:out[last].rfind("।") + 1].strip()
            cleaned.append(out)
    return cleaned


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="sources/ahsanul-kalam")
    ap.add_argument("--db", default="assets/quran.db", help="for expected ayah counts")
    ap.add_argument("--out", default="dist/pilot/ahsanul-kalam")
    ap.add_argument("--surahs", default="1,112,113,114",
                    help="comma list, or a range like 78-114")
    ap.add_argument("--jobs", type=int, default=8)
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
    for surah, (start, end) in spans.items():
        log(f"surah {surah}: lines {start}-{end} "
            f"({stream[start]['file']} p{stream[start]['pdf_page']})")
        runs = read_surah(stream, src, start, end, ocr)
        if len(runs) > 1:
            log(f"  {len(runs)} numbering runs in this span — the book prints no "
                f"title for the surah(s) after {surah}")
        for offset, run in enumerate(runs):
            n = surah + offset
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
