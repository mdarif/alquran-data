# Translation-Audio R2 Publish Plan — Al-Fatihah Pilot (Sahih International)

Self-contained execution plan. No prior conversation context needed — this
doc has everything required to run the publish and verify it worked.

## What this is for

The **Al Quran** Flutter app (`../alquran-app`) currently bundles 7 local MP3
assets — Sahih International's spoken English translation for Al-Fatihah's 7
verses — directly inside the app (`assets/audio/poc/en-sahih-international/`,
~948 KB). The app wants to stop embedding audio and instead stream + cache it
from R2, the same way it already does for Arabic recitation (Alafasy). This is
the **data-repo half** of that move: publish just the 7 Al-Fatihah files to R2
first (not the full 6236-file set — that fetch is still in progress locally
and out of scope here), so the app side can be built and tested against real
URLs before scaling up.

Full background: `../alquran-app/docs/translation-audio-chaining-plan.md`
(source-data section + Phase 1). Do not re-derive decisions from scratch —
that doc is the source of truth for *why*; this doc is the *how* for this one
narrow step.

## Source files (already fetched, verify before publishing)

```
sources/audio/sahih-international/001001.mp3   (171,910 bytes)
sources/audio/sahih-international/001002.mp3   (121,754 bytes)
sources/audio/sahih-international/001003.mp3   (124,889 bytes)
sources/audio/sahih-international/001004.mp3   (82,884 bytes)
sources/audio/sahih-international/001005.mp3   (123,008 bytes)
sources/audio/sahih-international/001006.mp3   (81,630 bytes)
sources/audio/sahih-international/001007.mp3   (250,904 bytes)
```

These came from `pipeline/quranenc/fetch_everyayah_audio.py
Sahih_Intnl_Ibrahim_Walk_192kbps sahih-international` (everyayah.com). They
are byte-identical to what's currently bundled in the app
(`../alquran-app/assets/audio/poc/en-sahih-international/*.mp3`) — same
sizes, same source. **Do not re-fetch or re-encode them.** If any of the 7
files above is missing or a different size, stop and re-run the fetch script
for just Al-Fatihah before publishing — do not publish a partial/corrupt file.

Sanity check before you start:
```bash
for n in 1 2 3 4 5 6 7; do
  f=$(printf "sources/audio/sahih-international/001%03d.mp3" "$n")
  [[ -f "$f" ]] && echo "OK   $f ($(stat -f%z "$f" 2>/dev/null || stat -c%s "$f") bytes)" \
                || echo "MISSING $f"
done
```

## Destination

- **Bucket:** `al-quran-audio` (same bucket the Arabic recitation audio
  already lives in — Cloudflare R2, custom domain `audio.alquranreader.com`,
  r2.dev URL disabled).
- **Prefix:** `translation-audio/en-sahih-international/` — a **sibling** to
  the existing `recitation/` prefix, NOT nested under it. This is a
  conceptually distinct thing (a narrator reading a translation aloud, not
  Qur'an recitation) even though it shares a bucket.
- **Key scheme:** `SSSAAA.mp3` (zero-padded surah + ayah, e.g. Fatiha 1:1 →
  `001001.mp3`) — **NOT** the global 1..6236 id the `recitation/` prefix uses.
  This mirrors how the app's `translation_audio_source.dart` already keys
  everything (`translationAudioKey`) — do not renumber to match recitation's
  scheme, the two are deliberately different (see that file's doc comment).
- **Final URLs**, e.g.:
  `https://audio.alquranreader.com/translation-audio/en-sahih-international/001001.mp3`

No `catalogue.json` and no content-addressed (`-sha12`) filenames for this —
audio publishing follows the simpler `recitation/` precedent (plain files,
direct URL construction in the app), NOT the text-editions pattern in
`pipeline/publish_editions.sh`. Do not build a manifest for this step.

## Publish commands

Run from the repo root. **`--remote` is mandatory on every command** — without
it, wrangler writes to a local simulated bucket and still prints "Upload
complete", which looks identical to a real publish. This has bitten this repo
before on the editions bucket; don't repeat it here.

```bash
BUCKET=al-quran-audio
PREFIX=translation-audio/en-sahih-international
SRC=sources/audio/sahih-international

for n in 1 2 3 4 5 6 7; do
  key=$(printf "%03d" "$n")
  f="$SRC/001${key}.mp3"
  echo "→ 001${key}.mp3"
  npx --yes wrangler r2 object put "$BUCKET/$PREFIX/001${key}.mp3" \
    --file "$f" --remote \
    --content-type "audio/mpeg" \
    --cache-control "public, max-age=31536000, immutable"
done
```

Notes on the flags:
- `--content-type audio/mpeg` — these are real MP3s served as-is, not gzip
  artifacts, so unlike `publish_editions.sh` there is no `Content-Encoding`
  trap to worry about here.
- `--cache-control public, max-age=31536000, immutable` — matches the
  `recitation/` prefix's caching (these files never change once published;
  a corrected/re-recorded file would get a new key, not overwrite this one,
  same content-addressing philosophy as editions but expressed via the
  `SSSAAA` key staying stable rather than a hash).

## Verify

After publishing, confirm all 7 files are live and correct **over the public
domain**, not just "wrangler said success":

```bash
for n in 1 2 3 4 5 6 7; do
  url="https://audio.alquranreader.com/translation-audio/en-sahih-international/001${n}.mp3"
  # zero-pad n to 3 digits for the URL
  url=$(printf "https://audio.alquranreader.com/translation-audio/en-sahih-international/001%03d.mp3" "$n")
  code=$(curl -s -o /dev/null -w "%{http_code}" "$url")
  size=$(curl -sI "$url" | grep -i content-length | tr -d '\r' | awk '{print $2}')
  echo "001$(printf %03d $n).mp3 -> HTTP $code, $size bytes"
done
```

Expect `HTTP 200` for all 7, with `Content-Length` matching the source file
sizes listed above exactly. If any file 404s or has a mismatched size, do not
tell the app team it's ready — re-check the `wrangler r2 object put` output
for that specific key and re-publish just that file.

Also spot-check one file plays correctly (not silently truncated):
```bash
curl -s -o /tmp/001001-check.mp3 \
  "https://audio.alquranreader.com/translation-audio/en-sahih-international/001001.mp3"
# should be exactly 171910 bytes and a valid MP3
ls -la /tmp/001001-check.mp3
file /tmp/001001-check.mp3   # expect "MPEG ADTS, layer III" or similar
```

## What this does NOT cover (explicitly out of scope for this doc)

- **The other 6229 verses.** The full Sahih International fetch
  (`sources/audio/sahih-international/`) is still in progress (2,820/6236
  files as of this writing) — do not publish partial full-Quran coverage.
  This doc is Al-Fatihah only, matching the app's current POC scope.
- **Rowwad / QuranEnc audio** — deferred pending compression (~5 GB
  uncompressed), separate future work.
- **The app-side switch** from bundled local asset to streaming this R2 URL —
  that's `alquran-app` repo work (new `translationAudioUri`/cache-key helpers,
  a stream+cache player replacing the current one-shot local-asset player,
  removing the bundled assets from `pubspec.yaml`). Not this repo's job; see
  `../alquran-app/docs/translation-audio-chaining-plan.md` Phase 1.5 once this
  publish is verified live.
- **Licensing/attribution file.** The owner already confirmed (2026-08-08,
  per the app plan doc) that everyayah.com's Sahih International/Ibrahim Walk
  recording is free to distribute non-commercially — this is not a new
  blocker, just noting it's already cleared, not re-litigated here.

## Done-when

- [ ] All 7 URLs return `HTTP 200` with byte-exact `Content-Length` matching
      the source files.
- [ ] One file's bytes were downloaded and spot-checked as a valid,
      non-truncated MP3.
- [ ] Report back (to the human, or to whoever picks up the app-side work)
      the 7 final URLs and confirmation they're live — that's the handoff
      artifact the app-side change needs.
