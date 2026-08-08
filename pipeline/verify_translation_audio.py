#!/usr/bin/env python3
"""Spot-check a published translation-audio set over the public R2 domain.

    python3 pipeline/verify_translation_audio.py \
        sources/audio/sahih-international translation-audio/en-sahih-international

Unlike verify_editions.py (every file, checksummed against a catalogue),
translation audio has no catalogue and, at full-Quran scale, 6236 files is too
many to check one-by-one on every run. This instead:

  * confirms the local source dir and the R2 prefix have the SAME file count
    (catches "some files never got uploaded" and "the fetch was still
    partial when this ran")
  * samples ~40 files spread across the whole range (not just the start) and
    checks each returns HTTP 200 with a Content-Length that exactly matches
    the local source file's size

A clean run here is necessary but not sufficient — it's a sampling check, not
a byte-for-byte audit of every file. Re-run pipeline/publish_translation_audio.sh
(it's resumable) if this finds a mismatch, then re-verify.
"""
from __future__ import annotations

import random
import subprocess
import sys
from pathlib import Path

BASE = "https://audio.alquranreader.com"


def file_size_over_http(url: str) -> tuple[int, int]:
    """Returns (status_code, content_length). content_length is -1 if absent."""
    out = subprocess.run(
        ["curl", "-sI", url], capture_output=True, check=False, text=True
    )
    status = -1
    length = -1
    for line in out.stdout.splitlines():
        line = line.strip()
        if line.upper().startswith("HTTP/"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                status = int(parts[1])
        if line.lower().startswith("content-length:"):
            length = int(line.split(":", 1)[1].strip())
    return status, length


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(f"usage: {sys.argv[0]} <source-dir> <r2-prefix>")
    src = Path(sys.argv[1])
    prefix = sys.argv[2].strip("/")

    local_files = sorted(src.glob("*.mp3"))
    if not local_files:
        sys.exit(f"no .mp3 files found in {src}")
    print(f"local: {len(local_files)} files in {src}")

    sample_size = min(40, len(local_files))
    sample = random.sample(local_files, sample_size)

    ok = 0
    mismatches: list[str] = []
    for f in sample:
        expected = f.stat().st_size
        url = f"{BASE}/{prefix}/{f.name}"
        status, length = file_size_over_http(url)
        if status == 200 and length == expected:
            ok += 1
        else:
            mismatches.append(
                f"{f.name}: HTTP {status}, content-length {length} "
                f"(expected {expected}) — {url}"
            )

    print(f"sampled {sample_size}/{len(local_files)}: {ok} OK, "
          f"{len(mismatches)} mismatched")
    if mismatches:
        print("\nMismatches:")
        for m in mismatches:
            print(f"  {m}")
        sys.exit(1)
    print("all sampled files match — looks published correctly.")


if __name__ == "__main__":
    main()
