#!/usr/bin/env python3
"""Extract the Ahsanul Kalam master PDFs into line-level images + a manifest.

The owner's master files (AQ1..AQ6, 661 pages) came out of Win2PDF, and their
text is neither a text layer nor a page scan: every *line* of type is a separate
lossless RGB image, wrapped in a PDF tiling **Pattern** and painted into a
rectangle. That is why `pdftotext` yields only folio numbers and `pdfimages`
reports no images at all — neither tool looks inside pattern resources.

This is much better than a page scan. Each line arrives:

  * pre-segmented (no layout analysis, no line-finding heuristics),
  * in paint order, which is reading order,
  * with its rectangle on the page, so streams can be told apart by geometry
    (the translation body vs. the numbered footnote block set in smaller type),
  * at a uniform ~297 DPI, FlateDecode — lossless, so no JPEG ringing around
    the nuktas, which is the failure mode that matters here (क़ misread as क is
    a plausible wrong word, not a visible error).

Output: one PNG per line under <out>/img/, plus <out>/lines.jsonl carrying the
geometry and ordering, ready for an OCR pass.

Usage:
    python pipeline/ahsanul_kalam/extract_lines.py \
        --pdf-dir "~/Dropbox/.../Hindi/Source Files" \
        --out sources/ahsanul-kalam
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

try:
    import pikepdf
except ImportError:  # pragma: no cover
    sys.exit("pikepdf is required: pip install pikepdf")

# `q /Pattern cs /pNNNN scn /a0 gs\n<x> <y> <w> <h> re f*` — one painted line.
# Height is negative in these files (the rect is given from its top edge).
PAINT_RE = re.compile(
    rb"/Pattern\s+cs\s*/(p\d+)\s+scn[^\n]*\n\s*"
    rb"(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+re\s+f\*",
    re.MULTILINE,
)

# The folio number is the one piece of real text on the page: a Tm placement
# followed by a TJ array of digits. Digits arrive kerned apart, hence the join.
FOLIO_RE = re.compile(rb"BT\s.*?\[(.*?)\]\s*TJ", re.DOTALL)
DIGIT_RE = re.compile(rb"\((\d)\)")


def folio_of(content: bytes) -> int | None:
    """The printed page number, or None if this page carries no folio."""
    m = FOLIO_RE.search(content)
    if not m:
        return None
    digits = b"".join(DIGIT_RE.findall(m.group(1)))
    return int(digits) if digits else None


def image_of_pattern(pat) -> tuple[object, bytes] | tuple[None, None]:
    """The single image XObject a line pattern wraps, if it has one."""
    xo = pat.Resources.get("/XObject") if "/Resources" in pat else None
    if not xo:
        return None, None
    for _, im in xo.items():
        return im, None
    return None, None


def extract(pdf_path: Path, out_dir: Path, manifest, stats: dict) -> None:
    pdf = pikepdf.open(pdf_path)
    stem = pdf_path.stem
    img_dir = out_dir / "img" / stem
    img_dir.mkdir(parents=True, exist_ok=True)

    for page_index, page in enumerate(pdf.pages):
        patterns = page.Resources.get("/Pattern")
        if not patterns:
            stats["pages_without_patterns"] += 1
            continue

        content = b"".join(bytes(s.read_bytes()) for s in _streams(page))
        folio = folio_of(content)

        # Paint order groups by *text frame*, not by position on the page: the
        # footnote block is painted before the body it annotates, and the running
        # header last. Within one frame it is reading order. So keep `order` (it
        # is the only reliable within-frame sequence) and separate the streams by
        # strip height, which the type sizes make unambiguous — roughly
        # 83px body / 72px footnote / 77px header at this DPI. Never sort the
        # whole page by y: that interleaves footnotes into the translation, and
        # the result reads as plausible Hindi instead of failing visibly.
        for order, m in enumerate(PAINT_RE.finditer(content)):
            name, x, y, w, h = m.group(1).decode(), *(float(g) for g in m.groups()[1:])
            pat = patterns.get(f"/{name}")
            if pat is None:
                stats["missing_pattern"] += 1
                continue
            im, _ = image_of_pattern(pat)
            if im is None:
                stats["pattern_without_image"] += 1
                continue

            pim = pikepdf.PdfImage(im)
            rel = f"{stem}/{page_index:04d}-{order:03d}.png"
            path = out_dir / "img" / rel
            with io.BytesIO() as buf:
                pim.as_pil_image().save(buf, format="PNG", optimize=True)
                path.write_bytes(buf.getvalue())

            scale = float(pat.Matrix[0]) if "/Matrix" in pat else None
            manifest.write(json.dumps({
                "file": stem,
                "pdf_page": page_index + 1,
                "folio": folio,
                "order": order,
                # Page coordinates in points, origin bottom-left. `top` is the
                # rect's upper edge (h is negative in these files).
                "x": round(x, 2),
                "top": round(y, 2),
                "width": round(w, 2),
                "height": round(abs(h), 2),
                "px_width": int(pim.width),
                "px_height": int(pim.height),
                "dpi": round(72 / scale) if scale else None,
                "img": rel,
            }, ensure_ascii=False) + "\n")
            stats["lines"] += 1

        stats["pages"] += 1
        if stats["pages"] % 25 == 0:
            print(f"[ahsanul-kalam] {stem}: {stats['pages']} pages, "
                  f"{stats['lines']} lines", flush=True)


def _streams(page):
    """A page's content stream(s), which may be an array."""
    c = page.get("/Contents")
    if c is None:
        return []
    return list(c) if isinstance(c, pikepdf.Array) else [c]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf-dir", required=True)
    ap.add_argument("--out", default="sources/ahsanul-kalam")
    ap.add_argument("--only", help="comma-separated stems, e.g. AQ2,AQ3")
    args = ap.parse_args()

    pdf_dir = Path(args.pdf_dir).expanduser()
    if not pdf_dir.is_dir():
        sys.exit(f"not a directory: {pdf_dir}")
    pdfs = sorted(pdf_dir.glob("*.pdf"))
    if args.only:
        wanted = {s.strip() for s in args.only.split(",")}
        pdfs = [p for p in pdfs if p.stem in wanted]
    if not pdfs:
        sys.exit(f"no PDFs found in {pdf_dir}")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stats = dict(pages=0, lines=0, pages_without_patterns=0,
                 missing_pattern=0, pattern_without_image=0)

    with (out_dir / "lines.jsonl").open("w", encoding="utf-8") as manifest:
        for p in pdfs:
            print(f"[ahsanul-kalam] {p.name}", flush=True)
            extract(p, out_dir, manifest, stats)

    print(f"[ahsanul-kalam] done: {stats['lines']} line images from "
          f"{stats['pages']} pages -> {out_dir}")
    for k in ("pages_without_patterns", "missing_pattern", "pattern_without_image"):
        if stats[k]:
            print(f"[ahsanul-kalam] note: {k} = {stats[k]}")


if __name__ == "__main__":
    main()
