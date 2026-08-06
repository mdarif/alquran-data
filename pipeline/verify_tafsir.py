#!/usr/bin/env python3
"""Verify the published Tafsir artifacts exactly as the app does.

    python3 pipeline/verify_tafsir.py
    python3 pipeline/verify_tafsir.py --base https://staging.example/tafsir/

Checks the live Tafsir catalogue, every gzipped SQLite artifact, both checksums,
row coverage, declared slug, and the absence of Content-Encoding.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from pipeline.build_tafsir import QPC_REGION_RE, QPC_PLACEHOLDERS, TAG_RE  # noqa: E402

DEFAULT_BASE = "https://editions.alquranreader.com/tafsir/"
EXPECTED_AYAHS = 6236
UA = "AlQuran-tafsir-verify/1.0"


def fetch(url: str) -> bytes:
    out = subprocess.run(
        ["curl", "-sS", "--fail", "-A", UA, url],
        capture_output=True,
        check=False,
    )
    if out.returncode != 0:
        raise SystemExit(f"fetch failed: {url}\n{out.stderr.decode().strip()}")
    return out.stdout


def headers(url: str) -> dict[str, str]:
    out = subprocess.run(
        ["curl", "-sSI", "-A", UA, url], capture_output=True, check=False
    )
    hdrs = {}
    for line in out.stdout.decode(errors="replace").splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            hdrs[k.strip().lower()] = v.strip()
    return hdrs


def count_qpc_placeholder_rows(conn: sqlite3.Connection) -> int:
    """Rows where a `qpc-hafs` region still holds a KFGQPC placeholder char.

    Those render as a dotted-ring bullet in the reader instead of the character
    the source wrote. build_tafsir.normalize_tafsir_html should leave none.
    """
    rows = 0
    for (text,) in conn.execute(
        "SELECT text FROM tafsir_entries WHERE text IS NOT NULL"
    ):
        if any(
            ord(ch) in QPC_PLACEHOLDERS
            for match in QPC_REGION_RE.finditer(text)
            for ch in TAG_RE.sub("", match.group("body"))
        ):
            rows += 1
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=DEFAULT_BASE)
    args = ap.parse_args()
    base = args.base if args.base.endswith("/") else args.base + "/"

    cat = json.loads(fetch(base + "catalogue.json"))
    resources = cat.get("tafsir", [])
    print(
        f"catalogue: {len(resources)} tafsir resources, "
        f"dbVersion {cat.get('dbVersion')}\n"
    )

    problems: list[str] = []
    for resource in resources:
        url = base + resource["file"]
        hdrs = headers(url)
        gz = fetch(url)
        raw = gzip.decompress(gz)

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as fh:
            fh.write(raw)
            path = fh.name
        try:
            conn = sqlite3.connect(path)
            slug = conn.execute("SELECT slug FROM tafsir_resource").fetchone()[0]
            n = conn.execute("SELECT COUNT(*) FROM tafsir_entries").fetchone()[0]
            text_groups = conn.execute(
                "SELECT COUNT(*) FROM tafsir_entries "
                "WHERE text IS NOT NULL AND trim(text) != ''"
            ).fetchone()[0]
            placeholder_rows = count_qpc_placeholder_rows(conn)
            conn.close()
        finally:
            os.unlink(path)

        checks = {
            "gz-sha256": hashlib.sha256(gz).hexdigest() == resource["sha256"],
            "raw-sha256": hashlib.sha256(raw).hexdigest()
            == resource.get("uncompressedSha256", ""),
            "bytes": len(gz) == resource.get("bytes"),
            "slug": slug == resource["slug"],
            "ayahs": n == EXPECTED_AYAHS,
            "text-groups": text_groups == resource.get("textGroupCount"),
            "no-content-encoding": "content-encoding" not in hdrs,
            "no-qpc-placeholders": placeholder_rows == 0,
        }
        bad = [k for k, ok in checks.items() if not ok]
        if bad:
            problems.append(f"{resource['slug']}: {', '.join(bad)}")
        print(
            f"{'PASS' if not bad else 'FAIL'}  {resource['slug']:<28} "
            f"{len(gz)/1024:>6.0f} KB" + (f"  BAD: {bad}" if bad else "")
        )

    print()
    if problems:
        for p in problems:
            print(f"FAIL: {p}")
        sys.exit(1)
    print("OK - every Tafsir artifact matches its catalogue digest")


if __name__ == "__main__":
    main()
