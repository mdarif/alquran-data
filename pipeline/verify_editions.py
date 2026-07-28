#!/usr/bin/env python3
"""Verify the published editions exactly as the app does.

    python3 pipeline/verify_editions.py
    python3 pipeline/verify_editions.py --base https://staging.example/

Fetches the live catalogue, downloads every artifact, and checks:

  * the sha256 of the **transferred** (gzipped) bytes
  * the sha256 of the **expanded** SQLite file
  * the byte size the catalogue advertises
  * that the artifact declares the slug it is listed under
  * that it carries all 6236 verses
  * that the response carries **no `Content-Encoding`** header

That last one is easy to get wrong and fails in a confusing way: if the host
marks the artifact `Content-Encoding: gzip`, HTTP clients decompress it
transparently, the bytes the app hashes are no longer the bytes the catalogue
describes, and every install is rejected as corrupt.

Run after any publish. A silent CDN or header change here surfaces to readers as
"the download did not match its checksum", which looks like corruption rather
than like a misconfiguration.
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

DEFAULT_BASE = "https://editions.alquranreader.com/"
EXPECTED_AYAHS = 6236
# Cloudflare's bot rules reject some default library user agents (python-urllib
# gets a 403 here), so fetch with curl and a plain UA — closer to what the app
# actually sends anyway.
UA = "AlQuran-verify/1.0"


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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=DEFAULT_BASE)
    args = ap.parse_args()
    base = args.base if args.base.endswith("/") else args.base + "/"

    cat = json.loads(fetch(base + "catalogue.json"))
    editions = cat.get("editions", [])
    print(f"catalogue: {len(editions)} editions, dbVersion {cat.get('dbVersion')}\n")

    problems: list[str] = []
    for e in editions:
        url = base + e["file"]
        hdrs = headers(url)
        gz = fetch(url)
        raw = gzip.decompress(gz)

        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as fh:
            fh.write(raw)
            path = fh.name
        try:
            conn = sqlite3.connect(path)
            slug = conn.execute("SELECT slug FROM edition").fetchone()[0]
            n = conn.execute("SELECT COUNT(*) FROM texts").fetchone()[0]
            conn.close()
        finally:
            os.unlink(path)

        checks = {
            "gz-sha256": hashlib.sha256(gz).hexdigest() == e["sha256"],
            "raw-sha256": hashlib.sha256(raw).hexdigest()
            == e.get("uncompressedSha256", ""),
            "bytes": len(gz) == e.get("bytes"),
            "slug": slug == e["slug"],
            "verses": n == EXPECTED_AYAHS,
            "no-content-encoding": "content-encoding" not in hdrs,
        }
        bad = [k for k, ok in checks.items() if not ok]
        if bad:
            problems.append(f"{e['slug']}: {', '.join(bad)}")
        print(
            f"{'PASS' if not bad else 'FAIL'}  {e['slug']:<24} "
            f"{len(gz)/1024:>5.0f} KB" + (f"  BAD: {bad}" if bad else "")
        )

    print()
    if problems:
        for p in problems:
            print(f"FAIL: {p}")
        sys.exit(1)
    print("OK — every artifact matches its catalogue digest")


if __name__ == "__main__":
    main()
