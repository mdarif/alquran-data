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
import re
import shutil
import sqlite3
import sys
import unicodedata
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

URDU_SPECIFIC_RE = re.compile(r"[ٹڈڑںےہھگپچژکگیۀۃ]")
LEADING_HEADING_RE = re.compile(r"^([^<\n]{3,120}:)(?=<)")

# --- KFGQPC Uthmanic Hafs placeholder characters ------------------------------
#
# The app renders anything classed `qpc-hafs` in KFGQPC Uthmanic Hafs
# (assets/fonts/UthmanicHafs1-Ver18.ttf). That font maps 170 codepoints -- all
# Arabic punctuation plus every Urdu/Persian-specific letter -- onto ONE dummy
# glyph: a dotted ring that reads as a solid bullet.
#
# The trap is that the font *claims* coverage for them in its cmap, so the text
# engine never falls back to another face the way it does for a genuinely
# missing glyph (`«`, `:`, `.` all fall back and render fine). So a `،` or a
# `ی` left inside a `qpc-hafs` region silently renders as that bullet in the
# reader instead of as the character the source wrote.
#
# The ranges below are derived from the shipped font: every codepoint whose glyph
# outline is identical to the one U+060C maps to. tests/test_build_tafsir.py
# re-derives them from the .ttf so this list cannot drift from the real font.
QPC_PLACEHOLDER_RANGES: tuple[tuple[int, int], ...] = (
    (0x0601, 0x0620),
    (0x063B, 0x063F),
    (0x0658, 0x065D),
    (0x065F, 0x065F),
    (0x066A, 0x066D),
    (0x066F, 0x066F),
    (0x0672, 0x06D5),
    (0x06DF, 0x06DF),
    (0x06E3, 0x06E3),
    (0x06EB, 0x06EB),
    (0x06EE, 0x06FF),
)
QPC_PLACEHOLDERS = frozenset(
    cp for start, end in QPC_PLACEHOLDER_RANGES for cp in range(start, end + 1)
)
# Letters in the set are Urdu/Persian orthography. Their presence means the
# region is not Qur'anic Arabic at all and must not be styled as such -- the
# surrounding Nastaliq/Naskh face renders them correctly as written.
QPC_PLACEHOLDER_LETTERS = frozenset(
    cp for cp in QPC_PLACEHOLDERS if unicodedata.category(chr(cp)) == "Lo"
)
# Combining marks cannot be moved out of a region (they would land on a dotted
# circle of their own) and the font has no outline for them, so they are dropped.
QPC_PLACEHOLDER_COMBINING = frozenset(
    cp for cp in QPC_PLACEHOLDERS if unicodedata.category(chr(cp)) == "Mn"
)
QPC_PLACEHOLDER_PUNCTUATION = (
    QPC_PLACEHOLDERS - QPC_PLACEHOLDER_LETTERS - QPC_PLACEHOLDER_COMBINING
)

# Block-level Arabic (`<p class="ar qpc-hafs">`, the English tafsir's hadith
# quotes) is rendered as a single run in a single font, so punctuation there
# cannot be re-scoped out of the QPC face -- only substituted. `؟` maps to a
# codepoint the font leaves to fallback so the question survives; pause marks are
# dropped, which is how the Mushaf itself sets Qur'anic text and precisely why
# KFGQPC ships no comma glyph. No Arabic letter is ever altered.
QPC_BLOCK_SUBSTITUTIONS = {
    "،": "",  # ARABIC COMMA
    "؛": "",  # ARABIC SEMICOLON
    "۔": "",  # ARABIC FULL STOP
    "؍": "",  # ARABIC DATE SEPARATOR
    "؞": "",  # ARABIC TRIPLE DOT PUNCTUATION MARK
    "؟": "?",  # ARABIC QUESTION MARK
    "٪": "%",  # ARABIC PERCENT SIGN
    "٫": ".",  # ARABIC DECIMAL SEPARATOR
    "٬": ",",  # ARABIC THOUSANDS SEPARATOR
    "٭": "*",  # ARABIC FIVE POINTED STAR
    # Extended Arabic-Indic digits -> Arabic-Indic digits, which the font draws.
    **{chr(0x06F0 + n): chr(0x0660 + n) for n in range(10)},
}

# Any tag carrying the `qpc-hafs` class, with its attributes and inner markup.
QPC_REGION_RE = re.compile(
    r'<(?P<tag>\w+)(?P<attrs>\b[^>]*\bclass="[^"]*\bqpc-hafs\b[^"]*"[^>]*)>'
    r"(?P<body>.*?)"
    r"</(?P=tag)>",
    re.IGNORECASE | re.DOTALL,
)
CLASS_ATTR_RE = re.compile(r'\s*class="([^"]*)"', re.IGNORECASE)
LANG_ATTR_RE = re.compile(r'\s*lang="[^"]*"', re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
# Presentation forms the font has no outline for at all (ﷲ, ﮨ, ...).
PRESENTATION_FORM_RE = re.compile(r"[ﭐ-﷿ﹰ-﻿]+")
INLINE_TAGS = frozenset({"span", "a", "b", "i", "em", "strong"})


def has_qpc_placeholders(text: str) -> bool:
    """True if `text` holds a character KFGQPC Hafs draws as its placeholder."""
    return any(ord(ch) in QPC_PLACEHOLDERS for ch in text)


def fold_presentation_forms(text: str) -> str:
    """Decompose Arabic presentation forms to letters the font can render."""
    return PRESENTATION_FORM_RE.sub(
        lambda m: unicodedata.normalize("NFKC", m.group(0)), text
    )


def drop_qpc_class(attrs: str) -> str:
    """Re-scope a region away from the Qur'anic face, tagging it as Urdu.

    Placeholder *letters* are Urdu/Persian orthography by definition, so the
    honest markup is `lang="ur"` -- which is also what the app keys its Nastaliq
    rendering off. The text itself is left byte-for-byte intact.
    """
    kept: list[str] = []

    def rewrite_class(match: re.Match[str]) -> str:
        kept.extend(
            name
            for name in match.group(1).split()
            if name.lower() not in {"qpc-hafs", "arabic", "ar"}
        )
        return ""

    attrs = CLASS_ATTR_RE.sub(rewrite_class, attrs)
    attrs = LANG_ATTR_RE.sub("", attrs).strip()
    if "ur" not in kept:
        kept.append("ur")
    prefix = f" {attrs}" if attrs else ""
    return f'{prefix} class="{" ".join(kept)}" lang="ur"'


def strip_placeholder_marks(body: str) -> str:
    return "".join(ch for ch in body if ord(ch) not in QPC_PLACEHOLDER_COMBINING)


def split_placeholder_punctuation(tag: str, attrs: str, body: str) -> str:
    """Move QPC-unrenderable punctuation outside an inline region.

    The character is preserved verbatim; only the styling boundary moves, so the
    surrounding body font draws it. The app already suppresses the space it
    otherwise inserts between inline pieces before `،`/`؟`, so the line reads
    exactly as before.
    """
    open_tag, close_tag = f"<{tag}{attrs}>", f"</{tag}>"
    parts: list[str] = []
    pending: list[str] = []

    def flush() -> None:
        if not pending:
            return
        chunk = "".join(pending)
        pending.clear()
        parts.append(f"{open_tag}{chunk}{close_tag}" if chunk.strip() else chunk)

    for ch in body:
        if ord(ch) in QPC_PLACEHOLDER_PUNCTUATION:
            flush()
            parts.append(ch)
        else:
            pending.append(ch)
    flush()
    return "".join(parts) if parts else f"{open_tag}{body}{close_tag}"


def substitute_placeholder_punctuation(body: str) -> str:
    return "".join(
        QPC_BLOCK_SUBSTITUTIONS.get(
            ch, "" if ord(ch) in QPC_PLACEHOLDER_PUNCTUATION else ch
        )
        for ch in body
    )


def normalize_qpc_region(match: re.Match[str]) -> str:
    tag = match.group("tag")
    attrs = match.group("attrs")
    body = fold_presentation_forms(match.group("body"))

    if any(ord(ch) in QPC_PLACEHOLDER_LETTERS for ch in TAG_RE.sub("", body)):
        # Not Qur'anic Arabic -- re-scope rather than rewrite a single letter.
        return f"<{tag}{drop_qpc_class(attrs)}>{body}</{tag}>"

    body = strip_placeholder_marks(body)
    if tag.lower() in INLINE_TAGS:
        return split_placeholder_punctuation(tag, attrs, body)
    return f"<{tag}{attrs}>{substitute_placeholder_punctuation(body)}</{tag}>"


def normalize_tafsir_html(text: str | None) -> str | None:
    """Make tafsir HTML safe for the reader's Qur'anic face.

    Guarantees that no character KFGQPC Hafs draws as its placeholder glyph
    survives inside a `qpc-hafs` region -- see QPC_PLACEHOLDER_RANGES.
    """
    if text is None:
        return None
    text = wrap_leading_urdu_heading(text)
    return QPC_REGION_RE.sub(normalize_qpc_region, text)


def wrap_leading_urdu_heading(text: str) -> str:
    def replace_heading(match: re.Match[str]) -> str:
        heading = match.group(1).strip()
        if not URDU_SPECIFIC_RE.search(heading):
            return match.group(0)
        return f'<h2 lang="ur" class="ur">{heading}</h2>'

    return LEADING_HEADING_RE.sub(replace_heading, text, count=1)


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
            body = normalize_tafsir_html(body)
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
