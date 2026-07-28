#!/usr/bin/env python3
"""Emit per-edition download artifacts + a catalogue, for hosting on R2.

    python pipeline/build_editions.py --db assets/quran.db --out dist/editions

Produces, for every translation edition in the built DB:

    dist/editions/<slug>.db.gz   one edition's text, self-contained, gzipped
    dist/editions/catalogue.json the manifest the app fetches

Artifacts ship **gzipped** because SQLite pages compress about 4:1 on this data
(Hindi: 3.2 MB → 612 KB), and download size is the whole point of the feature.
Do not rely on transport-level `Content-Encoding` instead: the app stores the
file it fetched, so the compression has to be part of the artifact rather than
of the connection.

Why editions ship as separate files at all: the app bundles `quran.db` and
re-seeds it from the asset whenever the version marker changes (see the app's
`db_seeder.dart`). Anything written INTO that file is destroyed on the next app
update, so a downloaded edition must be a separate artifact the app installs
into its own `editions.db`. → the edition-model ADR.

Two deliberate choices:

* **Artifacts are keyed and named by `slug`, never by row id.** Row ids come from
  `cur.lastrowid` in build_db.py and shift whenever `config/sources.yaml` is
  reordered, so a download URL built from an id would silently start pointing at
  a different edition.
* **Each artifact carries `surah` + `ayah`, not the global `ayah_id`.** The
  global id is stable today, but a downloaded file outlives the build that made
  it; addressing by (surah, ayah) means an edition installed months ago still
  lands on the right verse even if ids were ever renumbered. Costs a few KB.

The catalogue records a **sha256 of the downloaded (gzipped) file** and a second
one for the expanded DB. The app must verify the first before expanding and the
second before installing: a truncated download is otherwise indistinguishable
from a short edition, and it would render partial scripture with no error.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

EXPECTED_AYAHS = 6236

# The shape an edition artifact carries. Deliberately minimal and self-describing
# — the app reads it without needing this repo's full schema.
EDITION_SCHEMA = """
PRAGMA page_size = 1024;

CREATE TABLE edition (
    slug          TEXT PRIMARY KEY,
    type          TEXT NOT NULL,
    language_code TEXT NOT NULL,
    name          TEXT NOT NULL,
    native_name   TEXT,
    author        TEXT,
    direction     TEXT,
    sort_order    INTEGER NOT NULL DEFAULT 0,
    license       TEXT,
    source_url    TEXT,
    db_version    TEXT,
    built_at      TEXT
);

CREATE TABLE texts (
    surah INTEGER NOT NULL,
    ayah  INTEGER NOT NULL,
    text  TEXT NOT NULL,
    PRIMARY KEY (surah, ayah)
);
"""


def log(msg: str) -> None:
    print(f"[editions] {msg}")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_edition(conn: sqlite3.Connection, res: sqlite3.Row, out_dir: Path,
                  db_version: str, built_at: str) -> dict:
    """Write one <slug>.db and return its catalogue entry."""
    slug = res["slug"]
    if not slug:
        raise SystemExit(
            f"resource {res['id']} ('{res['name']}') has no slug — rebuild the DB "
            "with a schema_version >= 2 config."
        )

    rows = conn.execute(
        "SELECT a.surah_id, a.ayah_number, t.text_content"
        "  FROM translations t JOIN ayahs a ON a.id = t.ayah_id"
        " WHERE t.resource_id = ? ORDER BY a.surah_id, a.ayah_number",
        (res["id"],),
    ).fetchall()

    # A short edition is a real possibility (a partial source, a failed import),
    # and it is exactly the kind of thing that renders as blank verses rather
    # than as an error. Refuse to publish one.
    if len(rows) != EXPECTED_AYAHS:
        raise SystemExit(
            f"edition '{slug}' covers {len(rows)}/{EXPECTED_AYAHS} ayahs — refusing "
            "to publish a partial edition (it would render blank verses, not fail)."
        )

    path = out_dir / f"{slug}.db"
    if path.exists():
        path.unlink()
    ed = sqlite3.connect(path)
    try:
        ed.executescript(EDITION_SCHEMA)
        ed.execute(
            "INSERT INTO edition(slug,type,language_code,name,native_name,author,"
            "direction,sort_order,license,source_url,db_version,built_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                slug, res["type"], res["language_code"], res["name"],
                res["native_name"], res["author"], res["direction"],
                res["sort_order"], res["license"], res["source_url"],
                db_version, built_at,
            ),
        )
        ed.executemany("INSERT INTO texts(surah,ayah,text) VALUES (?,?,?)", rows)
        ed.commit()
        ed.execute("VACUUM")
    finally:
        ed.close()

    raw_size = path.stat().st_size
    raw_digest = sha256_of(path)

    # mtime=0 so a rebuild of unchanged data produces a byte-identical artifact —
    # otherwise the sha256 churns every run and the app re-downloads editions
    # whose text never changed.
    gz_path = path.with_suffix(".db.gz")
    with path.open("rb") as src, gzip.GzipFile(gz_path, "wb", compresslevel=9, mtime=0) as dst:
        shutil.copyfileobj(src, dst)
    path.unlink()  # the uncompressed .db is an intermediate, not an artifact

    size = gz_path.stat().st_size
    digest = sha256_of(gz_path)
    log(
        f"{slug}: {len(rows)} ayahs, {size/1024:.0f} KB gzipped "
        f"({raw_size/1024:.0f} KB raw, {size/raw_size:.0%}), sha256 {digest[:16]}…"
    )

    return {
        "slug": slug,
        "type": res["type"],
        "lang": res["language_code"],
        "name": res["name"],
        "nativeName": res["native_name"],
        "author": res["author"],
        "direction": res["direction"],
        "sortOrder": res["sort_order"],
        "license": res["license"],
        "sourceUrl": res["source_url"],
        "ayahCount": len(rows),
        "file": f"{slug}.db.gz",
        # What you download, and the hash to check it by.
        "bytes": size,
        "sha256": digest,
        # What you end up with on disk after expanding — checked again before
        # install, and what the Translations screen should show as the on-device
        # cost, since that is the space the reader actually gives up.
        "uncompressedBytes": raw_size,
        "uncompressedSha256": raw_digest,
        "dbVersion": db_version,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="assets/quran.db")
    ap.add_argument("--out", default="dist/editions")
    args = ap.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        sys.exit(f"db not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    meta = dict(conn.execute("SELECT key, value FROM db_meta").fetchall())
    if int(meta.get("schema_version", 1)) < 2:
        sys.exit(
            "db schema_version < 2 — it has no edition slugs. Rebuild with the "
            "current config/sources.yaml first."
        )
    db_version = meta.get("db_version", "0.0.0")
    built_at = meta.get("built_at", datetime.now(timezone.utc).isoformat())

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    resources = conn.execute(
        "SELECT * FROM resources WHERE type = 'translation'"
        " ORDER BY language_code, sort_order, id"
    ).fetchall()
    if not resources:
        sys.exit("no translation resources in the DB")

    entries = [build_edition(conn, r, out_dir, db_version, built_at) for r in resources]

    slugs = [e["slug"] for e in entries]
    if len(set(slugs)) != len(slugs):
        sys.exit(f"duplicate slugs in catalogue: {slugs}")

    catalogue = {
        "catalogueVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "dbVersion": db_version,
        "editions": entries,
    }
    (out_dir / "catalogue.json").write_text(
        json.dumps(catalogue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    total = sum(e["bytes"] for e in entries)
    log(f"catalogue.json: {len(entries)} editions, {total/1024:.0f} KB total -> {out_dir}")
    conn.close()


if __name__ == "__main__":
    main()
