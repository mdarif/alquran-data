#!/usr/bin/env python3
"""
Al Quran — data compilation pipeline.

Reads QUL (Quranic Universal Library) source files declared in a YAML config,
introspects each one (so it tolerates minor column-name differences between
packages), and compiles a single bundled SQLite seed database that matches the
app schema in pipeline/schema.sql (PRD v1.1.1, Section 5.1).

Design goals (from the PRD):
  * Edge-heavy / offline-first: output is one self-contained .db file.
  * Verified sources: SHA-256 of every input is recorded in db_meta (Risk #1).
  * No guessing: each source's columns are auto-detected, with optional
    explicit overrides in the config.

Usage:
    python pipeline/build_db.py --config config/sources.yaml

Nothing here downloads from the network. You download the chosen resources from
https://qul.tarteel.ai yourself and point the config at the local files.
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    sys.exit("PyYAML is required. Run: pip install -r requirements.txt")


# --------------------------------------------------------------------------- #
# Small utilities
# --------------------------------------------------------------------------- #

def log(msg: str) -> None:
    print(f"[build] {msg}", flush=True)


def normalize_english_name(name: str) -> str:
    """Tidy a transliterated surah name from upstream metadata.

    The Persian/Urdu ezafe connector is always lowercase — "Aal-e-Imran", never
    "Aal-E-Imran". Upstream sources sometimes title-case it; fix that here so the
    app never shows a capital "E" mid-phrase.
    """
    return re.sub(r"(?<=-)E(?=-)", "e", name)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def first_present(columns: list[str], candidates: list[str]) -> str | None:
    """Return the first candidate column name that exists (case-insensitive)."""
    lower = {c.lower(): c for c in columns}
    for cand in candidates:
        if cand.lower() in lower:
            return lower[cand.lower()]
    return None


def sqlite_tables(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return [r[0] for r in rows]


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info('{table}')").fetchall()]


def table_rowcount(conn: sqlite3.Connection, table: str) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM '{table}'").fetchone()[0]


def pick_data_table(conn: sqlite3.Connection, override: str | None) -> str:
    """Choose the table holding the rows we care about (largest if not overridden)."""
    tables = sqlite_tables(conn)
    if override:
        if override not in tables:
            raise ValueError(f"table '{override}' not found; available: {tables}")
        return override
    if not tables:
        raise ValueError("source SQLite has no tables")
    return max(tables, key=lambda t: table_rowcount(conn, t))


# --------------------------------------------------------------------------- #
# Source readers — each returns plain Python structures keyed by surah/ayah
# --------------------------------------------------------------------------- #

def read_surahs(spec: dict) -> dict[int, dict]:
    """Read surah metadata: id, name_arabic, name_english, revelation_place, total_ayahs."""
    path = Path(spec["file"])
    cols = spec.get("columns", {})
    conn = sqlite3.connect(path)
    try:
        table = pick_data_table(conn, spec.get("table"))
        c = table_columns(conn, table)
        col_id = cols.get("id") or first_present(c, ["id", "surah", "sura", "number", "chapter_id", "chapter"])
        col_ar = cols.get("name_arabic") or first_present(c, ["name_arabic", "arabic_name", "name_ar", "arabic", "name"])
        col_en = cols.get("name_english") or first_present(c, ["name_simple", "name_english", "transliteration", "english_name", "name_en"])
        col_rev = cols.get("revelation_place") or first_present(c, ["revelation_place", "place", "type", "revelation"])
        col_cnt = cols.get("total_ayahs") or first_present(c, ["verses_count", "total_ayahs", "ayahs", "ayah_count", "verses"])
        if not (col_id and col_ar and col_en):
            raise ValueError(f"surah source columns not detected in {path} (have {c})")
        colnames = [r[0] for r in conn.execute(f"SELECT * FROM '{table}' LIMIT 0").description]
        out: dict[int, dict] = {}
        for row in conn.execute(f"SELECT * FROM '{table}'"):
            d = dict(zip(colnames, row))
            sid = int(d[col_id])
            out[sid] = {
                "id": sid,
                "name_arabic": str(d[col_ar]).strip(),
                "name_english": normalize_english_name(str(d[col_en]).strip()),
                "revelation_place": (str(d[col_rev]).strip().lower() if col_rev and d[col_rev] is not None else None),
                "total_ayahs": int(d[col_cnt]) if col_cnt and d[col_cnt] is not None else None,
            }
        return out
    finally:
        conn.close()


def _detect_ayah_text_source(conn: sqlite3.Connection, table: str, cols: dict):
    """Return ('ayah', surah_col, ayah_col, text_col) or ('words', ...)."""
    c = table_columns(conn, table)
    word_index = first_present(c, ["word_index", "position"])
    word_text = first_present(c, ["text", "text_uthmani", "word", "qpc_uthmani_hafs"])
    surah_col = cols.get("surah") or first_present(c, ["surah", "sura", "chapter", "surah_number"])
    ayah_col = cols.get("ayah") or first_present(c, ["ayah", "verse", "ayah_number", "verse_number"])
    # word-by-word script export: has word_index and (surah,ayah) -> aggregate
    if word_index and surah_col and ayah_col and word_text:
        return ("words", surah_col, ayah_col, word_text, word_index)
    text_col = cols.get("text") or first_present(
        c, ["text", "text_uthmani", "text_imlaei", "ayah_text", "verse_text", "translation"]
    )
    if surah_col and ayah_col and text_col:
        return ("ayah", surah_col, ayah_col, text_col, None)
    # Some exports use a single "verse_key" like "2:255"
    key_col = first_present(c, ["verse_key", "ayah_key", "key"])
    if key_col and text_col:
        return ("keyed", key_col, None, text_col, None)
    raise ValueError(f"could not detect text columns in table '{table}' (have {c})")


def read_ayah_text(spec: dict) -> dict[tuple[int, int], str]:
    """Read ayah-level Arabic (or any per-ayah text) keyed by (surah, ayah)."""
    path = Path(spec["file"])
    cols = spec.get("columns", {})
    conn = sqlite3.connect(path)
    try:
        table = pick_data_table(conn, spec.get("table"))
        kind, a, b, text_col, word_index = _detect_ayah_text_source(conn, table, cols)
        out: dict[tuple[int, int], str] = {}
        colnames = [d[0] for d in conn.execute(f"SELECT * FROM '{table}' LIMIT 0").description]

        if kind == "ayah":
            for row in conn.execute(f"SELECT * FROM '{table}'"):
                d = dict(zip(colnames, row))
                if d[text_col] is None:
                    continue
                out[(int(d[a]), int(d[b]))] = str(d[text_col])

        elif kind == "keyed":
            for row in conn.execute(f"SELECT * FROM '{table}'"):
                d = dict(zip(colnames, row))
                if d[text_col] is None:
                    continue
                s, ay = str(d[a]).split(":")
                out[(int(s), int(ay))] = str(d[text_col])

        else:  # words -> aggregate into ayah text, ordered by word_index
            buckets: dict[tuple[int, int], list[tuple[int, str]]] = {}
            for row in conn.execute(f"SELECT * FROM '{table}'"):
                d = dict(zip(colnames, row))
                if d[text_col] is None:
                    continue
                key = (int(d[a]), int(d[b]))
                buckets.setdefault(key, []).append((int(d[word_index]), str(d[text_col])))
            for key, words in buckets.items():
                words.sort(key=lambda w: w[0])
                out[key] = " ".join(w[1] for w in words).strip()

        return out
    finally:
        conn.close()


TATWEEL = "ـ"  # ARABIC TATWEEL (kashida) — the elongation carrier.


def graft_tatweel_carriers(
    arabic: dict[tuple[int, int], str], reference_path: Path
) -> tuple[dict[tuple[int, int], str], int]:
    """Restore the kashida (tatweel) carriers the golden v2 text omits.

    The KFGQPC UthmanicHafs font seats superscript marks — madd (``ٰٓ``),
    dagger-alef (``ٰ``), hamza (``ٔ``) — on a U+0640 tatweel. The
    ``quran.ar.uthmani.v2`` text ships WITHOUT those carriers, so the marks
    collapse onto the previous letter (verified via ``hb-shape``: bare ``يَٰٓ``
    leaves the yeh isolated and the madd floats high; ``يَـٰٓ`` makes the yeh
    connect and the madd seat on the stretch). The canonical Tanzil edition has
    the *same letters* but carries the kashidas — so we diff against it and graft
    across **only the pure-tatweel runs**, leaving our letters and the v2 mark
    encoding (e.g. U+06E1 sukun) untouched. We transfer kashida *positions*, not
    anyone's text.
    """
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    grafted = 0
    out: dict[tuple[int, int], str] = {}
    for pos, text in arabic.items():
        ref = reference.get(f"{pos[0]}:{pos[1]}")
        if ref is None:
            out[pos] = text
            continue
        buf: list[str] = []
        matcher = difflib.SequenceMatcher(None, text, ref, autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag != "insert":
                buf.append(text[i1:i2])  # keep our chars verbatim
            # Only adopt the canonical insertion when it is purely kashida(s).
            run = ref[j1:j2]
            if (tag in ("insert", "replace")) and run and all(c == TATWEEL for c in run):
                buf.append(run)
                grafted += len(run)
        out[pos] = "".join(buf)
    return out, grafted


def read_per_ayah_metadata(spec: dict) -> dict[tuple[int, int], dict]:
    """Read structural metadata when the source already has one row per ayah."""
    path = Path(spec["file"])
    cols = spec.get("columns", {})
    conn = sqlite3.connect(path)
    try:
        table = pick_data_table(conn, spec.get("table"))
        c = table_columns(conn, table)
        colnames = [d[0] for d in conn.execute(f"SELECT * FROM '{table}' LIMIT 0").description]
        surah_col = cols.get("surah") or first_present(c, ["surah", "sura", "chapter"])
        ayah_col = cols.get("ayah") or first_present(c, ["ayah", "verse", "ayah_number"])
        m = {
            "page_number": cols.get("page_number") or first_present(c, ["page_number", "page"]),
            "juz_number": cols.get("juz_number") or first_present(c, ["juz_number", "juz"]),
            "hizb_number": cols.get("hizb_number") or first_present(c, ["hizb_number", "hizb"]),
            "rub_el_hizb": cols.get("rub_el_hizb") or first_present(c, ["rub_el_hizb", "rub", "rub_number"]),
            "ruku_number": cols.get("ruku_number") or first_present(c, ["ruku_number", "ruku"]),
            "sajda": cols.get("sajda") or first_present(c, ["sajda", "sajdah", "sajda_number"]),
        }
        if not (surah_col and ayah_col):
            raise ValueError(f"metadata source missing surah/ayah columns in {path} (have {c})")
        out: dict[tuple[int, int], dict] = {}
        for row in conn.execute(f"SELECT * FROM '{table}'"):
            d = dict(zip(colnames, row))
            key = (int(d[surah_col]), int(d[ayah_col]))
            rec = {}
            for field, src in m.items():
                if src and d.get(src) is not None:
                    if field == "sajda":
                        rec[field] = 1 if str(d[src]).strip() not in ("", "0", "none", "None", "false") else 0
                    else:
                        rec[field] = int(d[src])
            out[key] = rec
        return out
    finally:
        conn.close()


def expand_markers(markers: list[dict], ayah_order: list[tuple[int, int]]) -> dict[tuple[int, int], int]:
    """
    Turn a list of start-markers (each {"surah":S,"ayah":A}) into a per-ayah
    number, given the canonical ayah order. Marker N starts at its (surah,ayah)
    and applies until the next marker. This is how juz/hizb/page boundaries are
    typically encoded (start points only).
    """
    starts = [(int(m["surah"]), int(m["ayah"])) for m in markers]
    start_set = {pos: i + 1 for i, pos in enumerate(starts)}
    out: dict[tuple[int, int], int] = {}
    current = 0
    for pos in ayah_order:
        if pos in start_set:
            current = start_set[pos]
        out[pos] = current
    return out


def read_marker_metadata(spec: dict, ayah_order: list[tuple[int, int]]) -> dict[tuple[int, int], dict]:
    """Read structural metadata from a marker-based JSON file.

    Expected JSON shape (any subset of dimensions):
        {
          "page":  [{"surah":1,"ayah":1}, ...],   # 604 start markers
          "juz":   [{"surah":1,"ayah":1}, ...],   # 30 markers
          "hizb":  [...], "rub_el_hizb": [...], "ruku": [...],
          "sajda": [{"surah":7,"ayah":206}, ...]  # explicit list of sajda ayahs
        }
    """
    path = Path(spec["file"])
    data = json.loads(path.read_text(encoding="utf-8"))
    field_map = {
        "page": "page_number",
        "juz": "juz_number",
        "hizb": "hizb_number",
        "rub_el_hizb": "rub_el_hizb",
        "ruku": "ruku_number",
    }
    out: dict[tuple[int, int], dict] = {pos: {} for pos in ayah_order}
    for src_key, field in field_map.items():
        if src_key in data:
            numbers = expand_markers(data[src_key], ayah_order)
            for pos, num in numbers.items():
                out[pos][field] = num
    if "sajda" in data:
        sajda_set = {(int(m["surah"]), int(m["ayah"])) for m in data["sajda"]}
        for pos in ayah_order:
            out[pos]["sajda"] = 1 if pos in sajda_set else 0
    return out


# --------------------------------------------------------------------------- #
# Build
# --------------------------------------------------------------------------- #

def build(config: dict) -> None:
    out_path = Path(config["output"])
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.exists():
        out_path.unlink()

    schema_sql = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
    conn = sqlite3.connect(out_path)
    conn.executescript(schema_sql)

    checksums: dict[str, str] = {}

    def record_checksum(spec: dict):
        p = Path(spec["file"])
        if not p.exists():
            sys.exit(f"ERROR: source file not found: {p}\n"
                     f"Download it from QUL and place it as configured in the YAML.")
        checksums[p.name] = sha256_of(p)

    sources = config["sources"]

    # 1) Surahs --------------------------------------------------------------
    surah_spec = sources["surahs"]
    record_checksum(surah_spec)
    surahs = read_surahs(surah_spec)
    log(f"surahs: {len(surahs)}")

    # 2) Arabic text ---------------------------------------------------------
    arabic_spec = sources["arabic_uthmani"]
    record_checksum(arabic_spec)
    arabic = read_ayah_text(arabic_spec)
    log(f"arabic ayahs: {len(arabic)}")

    # Restore the kashida carriers the golden v2 text omits but the KFGQPC font
    # needs to seat madd/dagger-alef/hamza marks (see graft_tatweel_carriers).
    ref_path = arabic_spec.get("tatweel_reference")
    if ref_path:
        arabic, grafted = graft_tatweel_carriers(arabic, Path(ref_path))
        log(f"tatweel carriers grafted: {grafted}")

    # Canonical ayah order: sort by (surah, ayah).
    ayah_order = sorted(arabic.keys())

    # Fill in total_ayahs from actual data if a surah row lacked it.
    counts: dict[int, int] = {}
    for (s, _a) in ayah_order:
        counts[s] = counts.get(s, 0) + 1
    for sid, srow in surahs.items():
        if not srow.get("total_ayahs"):
            srow["total_ayahs"] = counts.get(sid, 0)

    # Assign a global running ayah id (1..6236) in canonical order.
    ayah_id: dict[tuple[int, int], int] = {pos: i + 1 for i, pos in enumerate(ayah_order)}

    # 3) Structural metadata -------------------------------------------------
    meta: dict[tuple[int, int], dict] = {pos: {} for pos in ayah_order}
    meta_spec = sources.get("metadata")
    if meta_spec:
        record_checksum(meta_spec)
        mode = meta_spec.get("mode", "per_ayah")
        if mode == "markers":
            meta = read_marker_metadata(meta_spec, ayah_order)
        else:
            meta = read_per_ayah_metadata(meta_spec)
        log(f"metadata mode: {mode}")
    else:
        log("metadata: none provided (page/juz/hizb/ruku will be NULL)")

    # Insert surahs
    for sid in sorted(surahs):
        s = surahs[sid]
        conn.execute(
            "INSERT INTO surahs(id,name_arabic,name_english,revelation_place,total_ayahs)"
            " VALUES (?,?,?,?,?)",
            (s["id"], s["name_arabic"], s["name_english"], s["revelation_place"], s["total_ayahs"]),
        )

    # Insert ayahs
    for pos in ayah_order:
        s, a = pos
        md = meta.get(pos, {})
        conn.execute(
            "INSERT INTO ayahs(id,surah_id,ayah_number,text_arabic_uthmani,"
            "page_number,juz_number,hizb_number,rub_el_hizb,ruku_number,sajda)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                ayah_id[pos], s, a, arabic[pos],
                md.get("page_number"), md.get("juz_number"), md.get("hizb_number"),
                md.get("rub_el_hizb"), md.get("ruku_number"), md.get("sajda", 0),
            ),
        )

    # 4) Translations --------------------------------------------------------
    for tr in config["sources"].get("translations", []):
        record_checksum(tr)
        cur = conn.execute(
            "INSERT INTO resources(type,language_code,name,author,license,source_url)"
            " VALUES ('translation',?,?,?,?,?)",
            (tr["language_code"], tr["name"], tr.get("author"), tr.get("license"), tr.get("source_url")),
        )
        resource_id = cur.lastrowid
        rows = read_ayah_text(tr)  # translation simple.sqlite is also ayah-keyed text
        inserted = 0
        for pos, text in rows.items():
            aid = ayah_id.get(pos)
            if aid is None:
                continue
            conn.execute(
                "INSERT OR IGNORE INTO translations(ayah_id,resource_id,text_content) VALUES (?,?,?)",
                (aid, resource_id, text),
            )
            inserted += 1
        log(f"translation [{tr['language_code']}] {tr['name']}: {inserted} ayahs")

    # 5) db_meta -------------------------------------------------------------
    db_meta = {
        "schema_version": str(int(config.get("schema_version", 1))),  # always a bare integer
        "db_version": str(config.get("db_version", "0.0.0")),
        "built_at": datetime.now(timezone.utc).isoformat(),
        "source_checksums": json.dumps(checksums, ensure_ascii=False, sort_keys=True),
    }
    for k, v in db_meta.items():
        conn.execute("INSERT OR REPLACE INTO db_meta(key,value) VALUES (?,?)", (k, v))

    conn.commit()
    conn.execute("VACUUM")
    conn.close()
    log(f"done -> {out_path} ({out_path.stat().st_size/1024:.0f} KB)")
    log("checksums recorded for: " + ", ".join(sorted(checksums)))


def main() -> None:
    ap = argparse.ArgumentParser(description="Compile the Al Quran seed DB from QUL sources.")
    ap.add_argument("--config", default="config/sources.yaml", help="path to sources YAML")
    args = ap.parse_args()

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        sys.exit(f"config not found: {cfg_path}\nCopy config/sources.example.yaml to {cfg_path} and edit it.")
    config = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    build(config)


if __name__ == "__main__":
    main()
