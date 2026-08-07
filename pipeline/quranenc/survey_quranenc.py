#!/usr/bin/env python3
"""Read-only survey of QuranEnc.com's translation catalogue.

Calls QuranEnc's public `translations/list` API and prints every available
edition (language, translator/title, version, verse-database URL), flagging
which ones already appear in this repo's ``config/sources.yaml`` (by
language_code) so a human can pick genuinely new candidates.

This script makes NO changes to sources.yaml — it's step 1 of adding a new
translation: survey first, then hand-pick candidates for
``fetch_quranenc.py``.

Usage:
    python3 pipeline/quranenc/survey_quranenc.py [--lang en,fr,...]
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.request
from pathlib import Path

LIST_URL = "https://quranenc.com/api/v1/translations/list"
SOURCES_YAML = Path(__file__).resolve().parent.parent.parent / "config" / "sources.yaml"


USER_AGENT = "Mozilla/5.0 (compatible; alquran-data-pipeline/1.0)"


def fetch_list() -> list[dict]:
    print(f"[survey] GET {LIST_URL}")
    req = urllib.request.Request(LIST_URL, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))["translations"]


def existing_language_codes() -> set[str]:
    text = SOURCES_YAML.read_text(encoding="utf-8")
    return set(re.findall(r"language_code:\s*(\S+)", text))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", help="comma-separated ISO codes to filter to, e.g. en,fr,es")
    args = ap.parse_args()
    wanted = set(args.lang.split(",")) if args.lang else None

    editions = fetch_list()
    have = existing_language_codes()
    print(f"[survey] {len(editions)} editions on QuranEnc; "
          f"{len(have)} language_codes already present in sources.yaml\n")

    editions.sort(key=lambda e: (e["language_iso_code"], e["key"]))
    for e in editions:
        lang = e["language_iso_code"]
        if wanted and lang not in wanted:
            continue
        flag = "  (language already in sources.yaml)" if lang in have else "  *** NEW LANGUAGE ***"
        print(f"{lang:>4}  {e['key']:<28} v{e['version']:<10} {e['title']}{flag}")
        print(f"        sqlite: {e['database_uncompressed_url']}")

    print(
        "\n[survey] This is informational only. For each candidate you want to "
        "pursue, cross-check TRANSLATIONS-ROADMAP.md for prior creed/licensing "
        "notes before running fetch_quranenc.py."
    )


if __name__ == "__main__":
    main()
