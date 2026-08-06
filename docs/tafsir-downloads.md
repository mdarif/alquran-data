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

## Publish runbook

Run every command from the **repo root** (`~/code/alquran-data`). Steps 1–3 are
local and safe to repeat; step 4 is the only one that changes what users
download.

### 0. Prerequisites (once per machine)

```bash
npx --yes wrangler whoami        # must print an account, not a login prompt
```

Needs `sources/*.sqlite` present (git-ignored — re-download from QUL signed in)
and `python3 -m pip install -r requirements.txt`.

### 1. Rebuild the artifacts

```bash
python3 pipeline/build_tafsir.py --config config/tafsir.yaml --out dist/tafsir
```

Prints one line per resource and writes `dist/tafsir/<slug>-<sha12>.db.gz` plus
`catalogue.json`. **The `<sha12>` in the filename changes whenever the text
changes** — that is how a republish is distinguishable from the old pack.

Delete any leftover artifact whose digest is no longer in `catalogue.json`;
publishing only uploads what the catalogue references, so stale local files just
cause confusion.

### 2. Run the tests

```bash
python3 -m unittest discover -s tests
```

This is the real gate on tafsir text. It re-derives the KFGQPC placeholder table
from the shipped font and asserts that **no ◉ placeholder character survives in
any `qpc-hafs` region across all 6,236 rows of both tafsirs** — see the
"KFGQPC ◉ placeholder trap" section in `CLAUDE.md`. It also asserts no Arabic
letter was altered. If a new tafsir source is added and this fails, fix the
pipeline; do not patch the app.

### 3. Check the built artifacts before uploading

```bash
python3 - <<'PY'
import gzip, json, sqlite3, sys, tempfile, os
sys.path.insert(0, '.')
from pipeline.verify_tafsir import count_qpc_placeholder_rows
for r in json.load(open('dist/tafsir/catalogue.json'))['tafsir']:
    raw = gzip.decompress(open('dist/tafsir/' + r['file'], 'rb').read())
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as fh:
        fh.write(raw); path = fh.name
    conn = sqlite3.connect(path)
    rows = conn.execute('SELECT COUNT(*) FROM tafsir_entries').fetchone()[0]
    print(r['slug'], rows, 'rows,', count_qpc_placeholder_rows(conn), 'placeholder rows')
    conn.close(); os.unlink(path)
PY
```

Expect `6236 rows, 0 placeholder rows` for each.

### 4. Publish to R2

```bash
pipeline/publish_tafsir.sh
```

Uploads the immutable artifacts first and `catalogue.json` **last** (so no client
ever sees a catalogue pointing at an object that isn't there yet), then runs
`verify_tafsir.py` against the public domain automatically. Success looks like:

```text
PASS  en-ibn-kathir-abridged         3834 KB
PASS  ur-ibn-kathir                  4427 KB
OK - every Tafsir artifact matches its catalogue digest
```

`verify_tafsir.py` checks both checksums, byte length, slug, 6,236-row coverage,
the absence of `Content-Encoding`, **and** `no-qpc-placeholders`. A `PASS` here is
real proof the ◉ data is gone from the CDN.

### 5. Confirm the CDN flipped

```bash
curl -sS "https://editions.alquranreader.com/tafsir/catalogue.json?$(date +%s)" | python3 -m json.tool
```

The cache-buster matters: artifacts are `immutable, max-age=31536000` but
`catalogue.json` is `no-cache, must-revalidate`. Check `generatedAt` and that the
`file` digests match what step 1 built.

### 6. See it in the app

**Publishing alone does not update an installed tafsir.** `TafsirCubit._merge()`
marks a resource `installed` by slug and never compares the catalogue `sha256`
against the installed one, so there is no "update available" state. Anyone who
already downloaded the tafsir keeps the old text until they **Remove** it in the
tafsir sheet and download again. (Wiring sha-based update detection is open
follow-up work in the app repo.)

To test a build *before* publishing, serve `dist/tafsir` off the Mac and point
the app at it — `ios/Runner/Info.plist` already sets `NSAllowsLocalNetworking`,
so plain HTTP works on device and simulator:

```bash
cd dist/tafsir && python3 -m http.server 8777 --bind 0.0.0.0   # leave running
ipconfig getifaddr en0                                          # e.g. 192.168.0.8
```

```bash
cd ~/code/alquran-app
flutter run --dart-define=TAFSIR_CATALOGUE_URL=http://192.168.0.8:8777/catalogue.json
```

Then Remove + re-download in the tafsir sheet. Good regression spots for Arabic
rendering: **Al-Baqarah 2:1** — `«عمل الیوم واللیلہ»` and `«واللہ اعلم»` on the
Urdu tab, the `تَعَلَّمُوا القُرْآنَ` hadith on the English tab.

### 7. Delete the superseded artifacts (optional cleanup)

`publish_tafsir.sh` uploads what the catalogue names and **never prunes**, so
every republish leaves the previous `<slug>-<sha12>.db.gz` behind as an orphan.
Deleting them is optional housekeeping, not part of publishing.

Check first — deletion is not reversible from the dashboard:

```bash
npx --yes wrangler r2 object get "al-quran-editions/tafsir/catalogue.json" \
  --remote --pipe | python3 -m json.tool | grep '"file"'
```

**Only delete an object whose filename is absent from that output.** Anything the
live catalogue still names is what clients download; removing it breaks installs
immediately.

The two orphans left by the 2026-08-06 ◉-placeholder republish were:

```bash
npx --yes wrangler r2 object delete \
  "al-quran-editions/tafsir/en-ibn-kathir-abridged-3fd7d96a64a4.db.gz" --remote
npx --yes wrangler r2 object delete \
  "al-quran-editions/tafsir/ur-ibn-kathir-b69bfb26b450.db.gz" --remote
```

Both were superseded by `en-ibn-kathir-abridged-e31c65b4127d.db.gz` and
`ur-ibn-kathir-51872451aab9.db.gz`. Substitute the real orphan filenames each
time — never copy these two literally.

Then re-run step 5 and confirm the app can still install the tafsir. Nothing is
lost permanently either way: `build_tafsir.py` gzips with `mtime=0`, so builds are
byte-deterministic, and checking out the old commit and rebuilding from the same
`sources/` reproduces the exact same digest.

**This is only this simple while tafsir is unreleased** — no client has ever
fetched those objects. Once the feature ships publicly, a device that is
mid-download, or holding a stale catalogue, will 404 on a deleted artifact. After
release, leave the previous generation in place for a release cycle before
pruning.

### Gotchas that have actually bitten

| Symptom | Cause |
| --- | --- |
| `no catalogue.json in dist/tafsir` | Ran the script from inside `pipeline/`. Fixed — paths now resolve against the repo root. |
| `mapfile: command not found` | `mapfile` is a bash 4 builtin; macOS ships bash 3.2. Fixed in both publish scripts. |
| Fix committed but reader unchanged | Artifacts were never rebuilt/republished. A commit to `build_tafsir.py` changes nothing until step 1 **and** step 4 run. |
| Reader still shows old text after publishing | No sha-based update detection in the app — Remove and re-download (step 6). |
| ◉ bullets in Arabic quotes | The KFGQPC placeholder trap. See `CLAUDE.md`. |
