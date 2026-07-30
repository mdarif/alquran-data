#!/usr/bin/env python3
"""Map each verse to its source line images, for image-based proofreading.

Pilot tool (2026-07-30): every other check in this project compares TEXT
against TEXT — a rare word against a common one (self-consistency), a Hindi
skeleton against Urdu (nukta restoration), a verse's length against another
translator's (length-outlier). None of them can catch a case where the OCR'd
text is plausible Hindi but simply isn't what's printed — found twice this
session (15:3's ग़फलत, the मुक़र्रर family) only because the owner checked an
actual page. This script is the first step toward doing that at scale: it
reuses build_pilot.py's own verse-splitting logic (same marker positions,
same body-strip filter) but returns the IMAGE PATHS for each verse instead of
discarding them once the text is extracted.

Usage:
    python pipeline/ahsanul_kalam/verse_images.py --surahs 15 --out /tmp/out.json
"""
from __future__ import annotations

import argparse
import itertools
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import build_pilot as bp  # noqa: E402


def parse_surahs(spec: str) -> list[int]:
    out = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--surahs", required=True, help="e.g. 15 or 2,15,114 or 1-5")
    ap.add_argument("--src", default="sources/ahsanul-kalam")
    ap.add_argument("--db", default="assets/quran.db")
    ap.add_argument("--out", required=True)
    ap.add_argument("--jobs", type=int, default=8)
    args = ap.parse_args()

    src = Path(args.src)
    wanted = set(parse_surahs(args.surahs))

    import sqlite3
    conn = sqlite3.connect(args.db)
    expected = dict(conn.execute(
        "SELECT surah_id, COUNT(*) FROM ayahs GROUP BY surah_id").fetchall())
    conn.close()

    rows = bp.load_manifest(src)
    stream = bp.in_reading_order(rows)
    titles = bp.title_index(rows, src, src / "surah-titles.json")
    starts = sorted(titles.values())

    # Exactly build_pilot.main()'s span logic: a surah runs from its own
    # title to whichever title comes next in the stream.
    spans: dict[int, tuple[int, int]] = {}
    for surah in wanted:
        start = titles.get(surah)
        if start is None:
            print(f"no title strip found for surah {surah} — skipped")
            continue
        later = [i for i in starts if i > start]
        spans[surah] = (start, later[0] if later else len(stream))

    result: dict[str, dict[str, list[str]]] = {}
    for s, (start, end) in spans.items():
        body = [r for r in stream[start:end] if r["px_height"] == bp.BODY_PX]
        images_needed = [r["img"] for r in body]
        ocr = bp.ocr_all(images_needed, src, args.jobs)

        groups = []
        for _, grp in itertools.groupby(
                body, key=lambda r: (r["file"], r["pdf_page"], r["top"])):
            groups.append(list(grp))

        chunks = []
        group_imgs = []
        for grp in groups:
            hin = " ".join(ocr[(r["img"], "hin")] for r in grp)
            chunks.append(hin)
            group_imgs.append([r["img"] for r in grp])

        text = " ".join(chunks)
        text = text.replace("|", "।").replace("॥", "।")
        # character offset -> which chunk index it belongs to
        offsets = []
        pos = 0
        for c in chunks:
            offsets.append((pos, pos + len(c)))
            pos += len(c) + 1  # +1 for the joining space

        slots = list(bp.SLOT_RE.finditer(text))
        parsed = []
        for m in slots:
            digits = re.sub(r"[^0-9]", "", m.group(0))
            parsed.append(int(digits) if digits else None)

        cursor = 0
        surah = s
        while cursor < len(slots) and surah in expected:
            want = expected[surah]
            verse_spans: dict[int, tuple[int, int]] = {}
            n = 0
            while cursor < len(slots) and n < want:
                expect = n + 1
                v = parsed[cursor]
                nxt_v = parsed[cursor + 1] if cursor + 1 < len(parsed) else None
                nxt2_v = parsed[cursor + 2] if cursor + 2 < len(parsed) else None
                confirmed = v is not None and nxt_v == v + 1 and nxt2_v == v + 2
                if confirmed and expect < v <= expect + bp.MAX_MARKER_GAP:
                    n = v
                else:
                    n = expect
                body_start = slots[cursor].end()
                nxt = slots[cursor + 1] if cursor + 1 < len(slots) else None
                body_end = nxt.start() if nxt else len(text)
                prev_start, prev_end = verse_spans.get(n, (body_start, body_start))
                verse_spans[n] = (min(prev_start, body_start), max(prev_end, body_end))
                cursor += 1
            if surah in wanted:
                vmap = {}
                for vn, (vs, ve) in verse_spans.items():
                    imgs = []
                    for gi, (gs, ge) in enumerate(offsets):
                        if gs < ve and ge > vs:
                            imgs.extend(group_imgs[gi])
                    # dedupe, keep order
                    seen = set()
                    ordered = []
                    for im in imgs:
                        if im not in seen:
                            seen.add(im)
                            ordered.append(im)
                    vmap[str(vn)] = ordered
                result[str(surah)] = vmap
            surah += 1

    Path(args.out).write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"wrote {args.out}: "
          f"{sum(len(v) for v in result.values())} verses across {len(result)} surah(s)")


if __name__ == "__main__":
    main()
