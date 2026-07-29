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
import unicodedata
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


# Circumflex transliteration letters used by the Hilali-Khan English edition for
# long Arabic vowels. The owner wants them flattened to plain ASCII (Allâh →
# Allah) for cleaner reading. Deliberately a fixed 5-char map, NOT a Unicode
# diacritic-strip: embedded Arabic script and curly quotes must survive intact.
_TRANSLIT_DIACRITICS = str.maketrans({"â": "a", "î": "i", "û": "u", "Â": "A", "Î": "I"})


def normalize_translit(text: str) -> str:
    """Flatten â/î/û (and capitals) to a/i/u; leave all other characters as-is."""
    return text.translate(_TRANSLIT_DIACRITICS)


# Precomposed Devanagari nukta letters, U+0958..U+095F — क़ ख़ ग़ ज़ ड़ ढ़ फ़ as a
# SINGLE codepoint each. Unicode lists all eight as composition exclusions, so
# they are neither produced by NFC nor consumed by NFD: `क़` written precomposed
# and `क` + U+093C written decomposed render identically and never compare equal.
# Map: precomposed -> base letter + U+093C NUKTA.
_PRECOMPOSED_NUKTA = {
    chr(c): unicodedata.normalize("NFD", chr(c)) for c in range(0x958, 0x960)
}


def normalize_devanagari_nukta(text: str) -> str:
    """Rewrite precomposed Devanagari nukta letters to base + U+093C.

    The Hindi translation arrives with the precomposed forms (20,476 codepoints
    across 5,363 verses); the Devanagari transliteration produced by
    ``alquran-roman-urdu`` emits the decomposed form. Both are valid Unicode and
    look identical on screen, but they are different byte sequences, so:

      * search never matches across the two — a reader searching ``क़यामत``
        typed with one form silently gets no results from text stored in the
        other, and gets NO error either;
      * any vocabulary keyed on the text splits into two entries.

    Decomposed is the standards-recommended form (the precomposed block is a
    composition exclusion and is discouraged), so we normalise everything to it
    rather than to the majority spelling.

    Owner decision 2026-07-27. Rendering is character-for-character identical —
    this changes bytes, not the text. Verified below by rebuilding and confirming
    every verse is unchanged after folding both sides.

    A no-op for Arabic, Urdu and Latin text: the range is Devanagari-only.
    """
    if not any(0x958 <= ord(c) <= 0x95F for c in text):
        return text
    for pre, dec in _PRECOMPOSED_NUKTA.items():
        text = text.replace(pre, dec)
    return text


def normalize_presentation_forms(text: str) -> str:
    """Fold Arabic Presentation Forms A/B back to their canonical base letters.

    The Junagarhi Urdu source carries 304 stray presentation-form codepoints
    across 238 verses — e.g. ``تبلیﻎ`` ends in U+FECE GHAIN FINAL FORM instead of
    U+063A GHAIN. These are shaping artifacts of the original typesetting, not
    distinct letters: the text renderer already picks the right glyph from
    context, so they are invisible on screen but corrupt the underlying string.
    A reader searching ``غ`` never matches ``ﻎ``, and copy-paste carries the
    artifact out of the app.

    Applied per character and ONLY inside the two presentation-form blocks, so
    the rest of the string is bit-identical — a blanket NFKC over the whole text
    would also rewrite characters we deliberately keep. Ornate parentheses
    ``﴾﴿`` (U+FD3E/FD3F) live in this range but have no decomposition, so they
    survive untouched, which is what we want: they are intentional typography
    marking quoted Quranic text, not an artifact.

    U+FDF0..U+FDFD is excluded outright. Those are the "Arabic ligature word"
    characters — ``ﷺ`` (sallallahou alayhe wasallam), ``ﷻ``, ``ﷲ``, ``﷽`` — which
    are *semantic*, single-glyph honorifics an author typed on purpose, not
    shaping artifacts. NFKC expands ``ﷺ`` into the 18-character phrase
    ``صلى الله عليه وسلم``, which drops a wall of Arabic into the middle of an
    English sentence (Hilali-Khan 13:1). Shaping ligatures OUTSIDE this block —
    lam-alef ``ﻻ`` and friends — are still folded, and must be: they are the
    artifact ``gotchas.md`` §1 in alquran-roman-urdu warns about.

    Verified over the corpus: 203 Urdu verses change, every substitution 1:1,
    do-chashmi he ``ھ`` / gol he ``ہ`` unaffected, and the one ``ﷺ`` in the
    English edition survives.
    """
    return "".join(
        unicodedata.normalize("NFKC", c)
        if (0xFB50 <= ord(c) <= 0xFDFF or 0xFE70 <= ord(c) <= 0xFEFF)
        and not (0xFDF0 <= ord(c) <= 0xFDFD)
        else c
        for c in text
    )


def collapse_nbsp(text: str) -> str:
    """Turn no-break spaces (U+00A0) into regular spaces, then squeeze any runs.

    The Hilali-Khan edition glues transliterated terms with NBSP (e.g.
    ``Al-Ansar and Al-Muhajirun``). NBSP forbids line-wrapping, so chained
    ones become long unbreakable runs that get shoved to the next line and leave
    ragged gaps in a narrow reader column. Regular spaces wrap normally.
    """
    return re.sub(r"[ ]{2,}", " ", text.replace(" ", " "))


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


def _carries_madda(text: str, pos: int) -> bool:
    """True if the combining-mark run at ``pos`` includes a maddah (U+0653) — the
    elongated madd that Flutter fails to anchor without a tatweel carrier. Plain
    dagger-alef stacks (no maddah, e.g. ``رَّٰ``) anchor fine on their own, so in
    surgical mode we DON'T carry them (their carrier is the visible over-stretch)."""
    j = pos
    while j < len(text) and unicodedata.combining(text[j]):
        if text[j] == "ٓ":
            return True
        j += 1
    return False


def graft_tatweel_carriers(
    arabic: dict[tuple[int, int], str], reference_path: Path, surgical: bool = False
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
                # Surgical: only carry the elongated-madd cases (a maddah follows);
                # plain dagger-alef stacks render fine without a carrier.
                if (not surgical) or _carries_madda(text, i1):
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

def validate_editions(config: dict) -> None:
    """Check every edition has a unique, non-empty slug.

    Runs before the build deletes the previous DB, so a bad config leaves the
    existing artifact intact rather than a half-written one. A slug collision is
    the failure this whole column exists to prevent: consumers persist the slug
    and download artifacts are named by it, so two editions sharing one would
    silently resolve to each other. Row ids can't substitute — they come from
    cur.lastrowid and shift whenever this list is reordered.
    """
    seen: dict[str, str] = {}
    for tr in config["sources"].get("translations", []):
        slug = (tr.get("slug") or "").strip()
        name = tr.get("name", "?")
        if not slug:
            raise SystemExit(
                f"config: translation '{name}' has no `slug`. Every edition needs a "
                "stable slug — consumers persist it, and row ids shift whenever "
                "this list is reordered."
            )
        if slug in seen:
            raise SystemExit(
                f"config: duplicate slug '{slug}' ({seen[slug]} and {name}). "
                "Slugs must be unique."
            )
        seen[slug] = name


def load_hijri_anchors(conn: sqlite3.Connection, anchors_path: Path) -> None:
    """Load manually verified moon-sighting corrections (config/hijri_anchors.yaml)
    into hijri_anchor_points. Entirely optional and best-effort: a missing file
    just means no anchors ship yet (the app falls back to the raw tabular
    calendar), matching the app-side graceful-degradation contract — this is
    NOT a build-breaking requirement like the Quran text sources are."""
    if not anchors_path.exists():
        log(f"hijri anchors: {anchors_path} not found, skipping (0 anchors)")
        return
    data = yaml.safe_load(anchors_path.read_text(encoding="utf-8")) or {}
    anchors = data.get("anchors", [])
    inserted = 0
    for a in anchors:
        date = a["date"]
        region = a["region"]
        correction_days = int(a["correction_days"])
        source = a.get("source")
        # A malformed date is a config-authoring mistake, not a valid anchor —
        # fail the build loudly rather than shipping bad data silently.
        datetime.strptime(date, "%Y-%m-%d")
        conn.execute(
            "INSERT OR REPLACE INTO hijri_anchor_points"
            "(gregorian_date, region, correction_days, source) VALUES (?,?,?,?)",
            (date, region, correction_days, source),
        )
        inserted += 1
    log(f"hijri anchors: {inserted} loaded from {anchors_path.name}")


def build(config: dict, graft: bool = True, output: str | None = None,
          surgical: bool = True) -> None:
    validate_editions(config)

    out_path = Path(output or config["output"])
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

    # Align the handful of spots where the golden v2 text encodes a mark
    # differently than quran.com's displayed QPC Hafs (hamza form @2:72, imala
    # marker @11:41) — so we render what the site shows. Targeted, per-ayah.
    ov_path = arabic_spec.get("reading_overrides")
    if ov_path and Path(ov_path).exists():
        overrides = json.loads(Path(ov_path).read_text(encoding="utf-8"))
        applied = 0
        for key, text in overrides.items():
            s, a = (int(x) for x in key.split(":"))
            if (s, a) in arabic:
                arabic[(s, a)] = text
                applied += 1
        log(f"reading-form overrides applied: {applied}")

    # Restore the kashida carriers the golden v2 text omits but the KFGQPC font
    # needs to seat madd/dagger-alef/hamza marks (see graft_tatweel_carriers).
    ref_path = arabic_spec.get("tatweel_reference")
    if ref_path and graft:
        arabic, grafted = graft_tatweel_carriers(arabic, Path(ref_path), surgical=surgical)
        log(f"tatweel carriers grafted: {grafted}"
            + (" (surgical: madd-only)" if surgical else ""))
    elif ref_path:
        log("tatweel grafting DISABLED (--no-tatweel-graft): clean text, "
            "verify madd rendering on device with the patched font")

    # IndoPak (Phase 2, optional): standard-Unicode text for the Noorehuda font.
    # ADDITIVE — read straight through, never touches the Uthmani text/grafting.
    indopak_spec = sources.get("arabic_indopak")
    indopak: dict[tuple[int, int], str] = {}
    if indopak_spec:
        record_checksum(indopak_spec)
        indopak = read_ayah_text(indopak_spec)
        log(f"indopak ayahs: {len(indopak)}")

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
            "text_arabic_indopak,"
            "page_number,juz_number,hizb_number,rub_el_hizb,ruku_number,sajda)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                ayah_id[pos], s, a, arabic[pos], indopak.get(pos),
                md.get("page_number"), md.get("juz_number"), md.get("hizb_number"),
                md.get("rub_el_hizb"), md.get("ruku_number"), md.get("sajda", 0),
            ),
        )

    # 4) Translations (slugs already validated by validate_editions) ----------
    for tr in config["sources"].get("translations", []):
        record_checksum(tr)
        cur = conn.execute(
            "INSERT INTO resources(slug,type,language_code,name,native_name,author,"
            "direction,sort_order,default_on,license,source_url)"
            " VALUES (?,'translation',?,?,?,?,?,?,?,?,?)",
            (
                tr["slug"], tr["language_code"], tr["name"], tr.get("native_name"),
                tr.get("author"), tr.get("direction"), int(tr.get("sort_order", 0)),
                1 if tr.get("default_on") else 0,
                tr.get("license"), tr.get("source_url"),
            ),
        )
        resource_id = cur.lastrowid
        rows = read_ayah_text(tr)  # translation simple.sqlite is also ayah-keyed text
        strip_diacritics = bool(tr.get("strip_translit_diacritics"))
        fix_nbsp = bool(tr.get("collapse_nbsp"))
        inserted = 0
        for pos, text in rows.items():
            aid = ayah_id.get(pos)
            if aid is None:
                continue
            # Unconditional: presentation forms are always a typesetting
            # artifact, never a deliberate choice, so there is no edition this
            # should be opt-in for. A no-op for Latin/Devanagari editions — the
            # affected blocks are Arabic-script only. NOTE: this is the
            # translation path; the Arabic Quran text is read separately by
            # read_ayah_text() and never passes through here.
            text = normalize_presentation_forms(text)
            # Same class of fix, other script: precomposed vs decomposed nukta
            # is a silent byte-level mismatch that breaks search. Unconditional
            # for the same reason — never a deliberate authorial choice.
            text = normalize_devanagari_nukta(text)
            if strip_diacritics:
                text = normalize_translit(text)
            if fix_nbsp:
                text = collapse_nbsp(text)
            conn.execute(
                "INSERT OR IGNORE INTO translations(ayah_id,resource_id,text_content) VALUES (?,?,?)",
                (aid, resource_id, text),
            )
            inserted += 1
        log(f"translation [{tr['slug']}] {tr['name']}: {inserted} ayahs")

    # 5) hijri_anchor_points ---------------------------------------------------
    load_hijri_anchors(conn, Path(__file__).parent.parent / "config" / "hijri_anchors.yaml")

    # 6) db_meta -------------------------------------------------------------
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
    ap.add_argument("--no-tatweel-graft", action="store_true",
                    help="skip the kashida graft — build the clean text quran.com "
                         "renders (verify madd rendering on device first)")
    ap.add_argument("--full-graft", action="store_true",
                    help="restore the legacy over-graft (carry plain dagger-alef "
                         "too); the default is the surgical madd-only graft")
    ap.add_argument("--output", help="override the output path from the config")
    args = ap.parse_args()

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        sys.exit(f"config not found: {cfg_path}\nCopy config/sources.example.yaml to {cfg_path} and edit it.")
    config = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    build(config, graft=not args.no_tatweel_graft, output=args.output,
          surgical=not args.full_graft)


if __name__ == "__main__":
    main()
