# Downloadable Tafsir Plan

Tafsir should ship as a separate downloadable catalogue, not inside `quran.db`
and not inside `editions.db`.

Reasons:

- Tafsir text is much larger than translation text and would hurt install size.
- QUL Tafsir rows can cover a range of ayahs, so flattening to one text per ayah
  duplicates long commentary and loses source semantics.
- App UX should stay reader-first: download Tafsir explicitly, then open it on
  demand from an ayah action/sheet. Do not render Tafsir inline by default.

## Data Contract

`pipeline/build_tafsir.py` reads a local QUL-style SQLite export and emits:

- `dist/tafsir/<slug>-<sha12>.db.gz`
- `dist/tafsir/catalogue.json`

Each artifact contains:

- `tafsir_resource`: metadata for one resource.
- `tafsir_entries`: one row per ayah key, preserving `group_ayah_key`,
  `from_ayah`, `to_ayah`, `ayah_keys`, and nullable `text`.

For grouped commentary, only the leading `group_ayah_key` row carries text; the
following ayah rows point back to that group. The app can resolve any ayah by
querying its row, then loading `group_ayah_key` if `text` is null.

## First Resource

Start with English Tafsir Ibn Kathir abridged from QUL:
https://qul.tarteel.ai/resources/tafsir/35

Expected local source file:

```bash
sources/tafsir-ibn-kathir-english.sqlite
```

Use the abridged edition because the product goal is concise, high-confidence
commentary: weak narrations, long repetitions, and unverified Isra'iliyyat are
reduced compared with the full source.

Licensing still needs explicit verification on the QUL resource page before a
public release. Record the final license in `config/tafsir.yaml` and update
`ATTRIBUTION.md` when the resource is enabled for publication.

## Smoke Test

```bash
python tests/make_fixtures.py
python pipeline/build_tafsir.py \
  --config tests/fixtures/tafsir.yaml \
  --out /tmp/alquran-tafsir-fixture \
  --expected-ayahs 10
```

The fixture includes a `2:2` to `2:3` grouped commentary row to protect the
range semantics.

## Publish

```bash
python pipeline/build_tafsir.py --config config/tafsir.yaml --out dist/tafsir
pipeline/publish_tafsir.sh
```

The live app-facing catalogue is:

```text
https://editions.alquranreader.com/tafsir/catalogue.json
```
