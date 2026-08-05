#!/usr/bin/env python3
"""Emit downloadable Tafsir artifacts + a catalogue.

    python pipeline/build_tafsir.py --config config/tafsir.yaml --out dist/tafsir

QUL Tafsir exports are not shaped like translations. A single commentary block
can apply to a range of ayahs, with later ayah rows pointing back to the primary
group row. The artifact preserves that grouping so the app can fetch a small
indexed local DB and show only the requested passage without duplicating long
text 6,236 times.
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

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML is required. Run: pip install -r requirements.txt")

EXPECTED_AYAHS = 6236

TAFSIR_SCHEMA = """
PRAGMA page_size = 1024;

CREATE TABLE tafsir_resource (
    slug          TEXT PRIMARY KEY,
    language_code TEXT NOT NULL,
    name          TEXT NOT NULL,
    native_name   TEXT,
    author        TEXT,
    direction     TEXT NOT NULL,
    sort_order    INTEGER NOT NULL DEFAULT 0,
    license       TEXT,
    source_url    TEXT,
    credit_name   TEXT,
    abridged      INTEGER NOT NULL DEFAULT 0,
    db_version    TEXT
);

CREATE TABLE tafsir_entries (
    ayah_key       TEXT PRIMARY KEY,
    group_ayah_key TEXT NOT NULL,
    from_ayah      TEXT NOT NULL,
    to_ayah        TEXT NOT NULL,
    ayah_keys      TEXT NOT NULL,
    text           TEXT
);

CREATE INDEX idx_tafsir_entries_group ON tafsir_entries(group_ayah_key);
"""


def log(msg: str) -> None:
    print(f"[tafsir] {msg}")


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sqlite_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return [r[0] for r in rows]


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info('{table}')").fetchall()]


def pick_table(conn: sqlite3.Connection, override: str | None) -> str:
    tables = sqlite_tables(conn)
    if override:
        if override not in tables:
            raise SystemExit(f"table '{override}' not found; available: {tables}")
        return override
    for candidate in ("tafsirs", "tafsir", "verses"):
        if candidate in tables:
            return candidate
    if not tables:
        raise SystemExit("source SQLite has no tables")
    return max(tables, key=lambda t: conn.execute(f"SELECT COUNT(*) FROM '{t}'").fetchone()[0])


def first_present(columns: list[str], candidates: list[str]) -> str | None:
    lower = {c.lower(): c for c in columns}
    for candidate in candidates:
        if candidate.lower() in lower:
            return lower[candidate.lower()]
    return None


def read_rows(path: Path, table_override: str | None) -> list[dict[str, str | None]]:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        table = pick_table(conn, table_override)
        columns = table_columns(conn, table)
        ayah_key = first_present(columns, ["ayah_key", "verse_key", "key"])
        group_ayah_key = first_present(columns, ["group_ayah_key"])
        from_ayah = first_present(columns, ["from_ayah", "from_ayah_key"])
        to_ayah = first_present(columns, ["to_ayah", "to_ayah_key"])
        ayah_keys = first_present(columns, ["ayah_keys"])
        text = first_present(columns, ["text", "tafsir", "content"])
        if not ayah_key:
            raise SystemExit(f"could not detect ayah key column in {path} (have {columns})")
        if not text:
            raise SystemExit(f"could not detect tafsir text column in {path} (have {columns})")

        rows: list[dict[str, str | None]] = []
        for row in conn.execute(f"SELECT * FROM '{table}' ORDER BY \"{ayah_key}\""):
            key = str(row[ayah_key])
            group = str(row[group_ayah_key]) if group_ayah_key and row[group_ayah_key] else key
            start = str(row[from_ayah]) if from_ayah and row[from_ayah] else group
            end = str(row[to_ayah]) if to_ayah and row[to_ayah] else group
            keys = str(row[ayah_keys]) if ayah_keys and row[ayah_keys] else key
            body = str(row[text]).strip() if row[text] is not None else None
            rows.append(
                {
                    "ayah_key": key,
                    "group_ayah_key": group,
                    "from_ayah": start,
                    "to_ayah": end,
                    "ayah_keys": keys,
                    "text": body or None,
                }
            )
        return rows
    finally:
        conn.close()


def write_artifact(spec: dict, out_dir: Path, db_version: str, expected_ayahs: int) -> dict:
    slug = spec["slug"]
    source = Path(spec["file"])
    rows = read_rows(source, spec.get("table"))
    if len(rows) != expected_ayahs:
        raise SystemExit(
            f"tafsir '{slug}' covers {len(rows)}/{expected_ayahs} ayahs — refusing "
            "to publish a partial artifact."
        )
    text_rows = sum(1 for row in rows if row["text"])
    if text_rows == 0:
        raise SystemExit(f"tafsir '{slug}' has no commentary text")

    path = out_dir / f"{slug}.db"
    if path.exists():
        path.unlink()
    conn = sqlite3.connect(path)
    try:
        conn.executescript(TAFSIR_SCHEMA)
        conn.execute(
            "INSERT INTO tafsir_resource(slug,language_code,name,native_name,author,"
            "direction,sort_order,license,source_url,credit_name,abridged,db_version)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                slug,
                spec["language_code"],
                spec["name"],
                spec.get("native_name"),
                spec.get("author"),
                spec.get("direction", "ltr"),
                int(spec.get("sort_order", 0)),
                spec.get("license"),
                spec.get("source_url"),
                spec.get("credit_name"),
                1 if spec.get("abridged") else 0,
                db_version,
            ),
        )
        conn.executemany(
            "INSERT INTO tafsir_entries(ayah_key,group_ayah_key,from_ayah,to_ayah,ayah_keys,text)"
            " VALUES (:ayah_key,:group_ayah_key,:from_ayah,:to_ayah,:ayah_keys,:text)",
            rows,
        )
        conn.commit()
        conn.execute("VACUUM")
    finally:
        conn.close()

    raw_size = path.stat().st_size
    raw_digest = sha256_of(path)
    gz_path = path.with_suffix(".db.gz")
    with path.open("rb") as src, gzip.GzipFile(gz_path, "wb", compresslevel=9, mtime=0) as dst:
        shutil.copyfileobj(src, dst)
    path.unlink()

    digest = sha256_of(gz_path)
    final_path = gz_path.with_name(f"{slug}-{digest[:12]}.db.gz")
    if final_path.exists():
        final_path.unlink()
    gz_path.rename(final_path)
    size = final_path.stat().st_size
    log(
        f"{slug}: {len(rows)} ayah rows, {text_rows} text groups, "
        f"{size/1024:.0f} KB gzipped ({raw_size/1024:.0f} KB raw)"
    )
    return {
        "slug": slug,
        "lang": spec["language_code"],
        "name": spec["name"],
        "nativeName": spec.get("native_name"),
        "author": spec.get("author"),
        "direction": spec.get("direction", "ltr"),
        "sortOrder": int(spec.get("sort_order", 0)),
        "license": spec.get("license"),
        "sourceUrl": spec.get("source_url"),
        "creditName": spec.get("credit_name"),
        "abridged": bool(spec.get("abridged")),
        "visible": spec.get("visible", True) is not False,
        "ayahCount": len(rows),
        "textGroupCount": text_rows,
        "file": final_path.name,
        "bytes": size,
        "sha256": digest,
        "uncompressedBytes": raw_size,
        "uncompressedSha256": raw_digest,
        "dbVersion": db_version,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config/tafsir.yaml")
    ap.add_argument("--out", default="dist/tafsir")
    ap.add_argument("--expected-ayahs", type=int, default=EXPECTED_AYAHS)
    args = ap.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        sys.exit(f"config not found: {config_path}")
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    db_version = str(cfg.get("db_version", "0.1.0"))
    specs = [s for s in cfg.get("tafsir", []) if s.get("enabled", True)]
    if not specs:
        sys.exit("no enabled tafsir resources in config")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = [write_artifact(spec, out_dir, db_version, args.expected_ayahs) for spec in specs]
    slugs = [entry["slug"] for entry in entries]
    if len(set(slugs)) != len(slugs):
        sys.exit(f"duplicate tafsir slugs in catalogue: {slugs}")

    catalogue = {
        "catalogueVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "dbVersion": db_version,
        "tafsir": entries,
    }
    (out_dir / "catalogue.json").write_text(
        json.dumps(catalogue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    total = sum(entry["bytes"] for entry in entries)
    log(f"catalogue.json: {len(entries)} tafsir resources, {total/1024:.0f} KB total -> {out_dir}")


if __name__ == "__main__":
    main()
