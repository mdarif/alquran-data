#!/usr/bin/env python3
"""Pilot fetcher for QuranEnc.com's per-ayah translation-audio (spoken
narration of a translation, distinct from Qur'an recitation audio).

QuranEnc publishes a `files.json` manifest per translation key at
``https://d.quranenc.com/data/audio/<key>/files.json`` listing every
``SSSAAA.mp3`` file, plus the mp3s themselves at the same base URL. This
script downloads the manifest, verifies completeness (6236/6236), then
downloads all mp3 files into ``sources/audio/<key>/`` for evaluation.

This is a PILOT/evaluation tool, not a publish pipeline — audio is roughly
1000x the size of a text edition (~5 GB per language vs a few hundred KB),
and this app has no translation-audio playback feature yet, so nothing here
wires into config/sources.yaml or the R2 publish scripts.

Usage:
    python3 pipeline/quranenc/fetch_quranenc_audio.py <quranenc-key>
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

USER_AGENT = "Mozilla/5.0 (compatible; alquran-data-pipeline/1.0)"
BASE = "https://d.quranenc.com/data/audio"
EXPECTED = 6236
OUT_ROOT = Path(__file__).resolve().parent.parent.parent / "sources" / "audio"


def fetch_manifest(key: str) -> dict:
    url = f"{BASE}/{key}/files.json"
    print(f"[audio] GET {url}")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def download_all(key: str, manifest: dict) -> None:
    if manifest["available"] != EXPECTED or manifest["total"] != EXPECTED:
        sys.exit(
            f"[audio] FATAL: {key} is incomplete on QuranEnc's side "
            f"({manifest['available']}/{manifest['total']} of {EXPECTED}) — "
            f"not a pipeline bug, don't retry."
        )

    out_dir = OUT_ROOT / key
    out_dir.mkdir(parents=True, exist_ok=True)
    base_url = manifest["base_url"]
    total_bytes = 0
    for i, fname in enumerate(manifest["files"], 1):
        dest = out_dir / fname
        if dest.exists():
            total_bytes += dest.stat().st_size
            continue
        req = urllib.request.Request(base_url + fname, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
        dest.write_bytes(data)
        total_bytes += len(data)
        if i % 500 == 0 or i == len(manifest["files"]):
            print(f"[audio]   {i}/{len(manifest['files'])} files, "
                  f"{total_bytes / 1024 / 1024:.0f} MB so far")
        time.sleep(0.02)  # be polite to the upstream host

    print(f"[audio] {key}: {len(manifest['files'])} files, "
          f"{total_bytes / 1024 / 1024:.0f} MB -> {out_dir}")


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(f"Usage: {sys.argv[0]} <quranenc-audio-key>")
    key = sys.argv[1]
    manifest = fetch_manifest(key)
    print(f"[audio] {key}: {manifest['available']}/{manifest['total']} available, "
          f"generated {manifest['generated']}")
    download_all(key, manifest)


if __name__ == "__main__":
    main()
