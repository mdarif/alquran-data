#!/usr/bin/env python3
"""Pilot fetcher for everyayah.com's per-ayah translation-audio sets (e.g. the
Sahih International / Ibrahim Walk English reading), matching this repo's
QuranEnc audio pilot (fetch_quranenc_audio.py) but for everyayah.com's simpler
layout: no manifest, just ``<SSSAAA>.mp3`` files at a fixed base URL, 001001
through 114006.

Usage:
    python3 pipeline/quranenc/fetch_everyayah_audio.py Sahih_Intnl_Ibrahim_Walk_192kbps sahih-international
"""
from __future__ import annotations

import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

USER_AGENT = "Mozilla/5.0 (compatible; alquran-data-pipeline/1.0)"
BASE = "https://everyayah.com/data/English"
OUT_ROOT = Path(__file__).resolve().parent.parent.parent / "sources" / "audio"

# (surah, ayah_count) for all 114 surahs, standard Uthmani ayah numbering.
AYAHS_PER_SURAH = [
    7, 286, 200, 176, 120, 165, 206, 75, 129, 109, 123, 111, 43, 52, 99, 128,
    111, 110, 98, 135, 112, 78, 118, 64, 77, 227, 93, 88, 69, 60, 34, 30, 73,
    54, 45, 83, 182, 88, 75, 85, 54, 53, 89, 59, 37, 35, 38, 29, 18, 45, 60,
    49, 62, 55, 78, 96, 29, 22, 24, 13, 14, 11, 11, 18, 12, 12, 30, 52, 52,
    44, 28, 28, 20, 56, 40, 31, 50, 40, 46, 42, 29, 19, 36, 25, 22, 17, 19,
    26, 30, 20, 15, 21, 11, 8, 8, 19, 5, 8, 8, 11, 11, 8, 3, 9, 5, 4, 7, 3,
    6, 3, 5, 4, 5, 6,
]


def dest_path(key: str, s: int, a: int) -> Path:
    return OUT_ROOT / key / f"{s:03d}{a:03d}.mp3"


def download_all(source_slug: str, out_key: str) -> None:
    out_dir = OUT_ROOT / out_key
    out_dir.mkdir(parents=True, exist_ok=True)
    total_bytes = 0
    total_files = 0
    missing: list[str] = []

    for s, count in enumerate(AYAHS_PER_SURAH, 1):
        for a in range(1, count + 1):
            dest = dest_path(out_key, s, a)
            if dest.exists():
                total_bytes += dest.stat().st_size
                total_files += 1
                continue
            url = f"{BASE}/{source_slug}/{s:03d}{a:03d}.mp3"
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = resp.read()
            except urllib.error.HTTPError as e:
                missing.append(f"{s}:{a} ({e.code})")
                continue
            dest.write_bytes(data)
            total_bytes += len(data)
            total_files += 1
            time.sleep(0.02)
        if s % 20 == 0 or s == 114:
            print(f"[everyayah] surah {s}/114, {total_files} files, "
                  f"{total_bytes / 1024 / 1024:.0f} MB so far")

    print(f"[everyayah] {out_key}: {total_files}/6236 files, "
          f"{total_bytes / 1024 / 1024:.0f} MB -> {out_dir}")
    if missing:
        print(f"[everyayah] WARNING: {len(missing)} missing verses: {missing[:10]}"
              + (" ..." if len(missing) > 10 else ""))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(f"Usage: {sys.argv[0]} <everyayah-source-slug> <output-key>")
    download_all(sys.argv[1], sys.argv[2])
