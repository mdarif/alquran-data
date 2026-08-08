# Translation-Audio R2 Publish — Full Quran (Sahih International)

Self-contained execution plan. No prior conversation context needed — this
doc has everything required to finish the fetch and publish the rest of the
Sahih International translation-audio set.

## What this is for

The Al-Fatihah pilot (7 files) is already live at
`https://audio.alquranreader.com/translation-audio/en-sahih-international/`
— see `docs/translation-audio-r2-publish-plan.md` for that narrower step,
already done. This doc extends the SAME prefix to the full 6236-verse Sahih
International set (`sources/audio/sahih-international/`), which was only
partially fetched (2,818/6236 as of 2026-08-08).

Read `docs/translation-audio-r2-publish-plan.md` first if anything here is
unclear about *why* this prefix/bucket/naming — this doc assumes those
decisions and just extends them to the full set.

## Step 1 — finish the fetch

```bash
python3 pipeline/quranenc/fetch_everyayah_audio.py \
    Sahih_Intnl_Ibrahim_Walk_192kbps sahih-international
```

This is the SAME command that produced the 2,818 files already in
`sources/audio/sahih-international/` — it's idempotent (skips any file that
already exists locally), so re-running it just fetches what's missing. It
prints progress every 20 surahs and a final count. everyayah.com's own
listing claims 6236/6236 complete for this edition (per
`../alquran-app/docs/translation-audio-chaining-plan.md`'s source-data
table) — if the run finishes with fewer than 6236 files, some verses 404'd
on their end; note exactly which ones (the script prints a `WARNING:
missing verses` line with the list) and re-run once more before moving on,
since a transient network blip is the more likely cause than the source
actually being incomplete.

**Do not proceed to Step 2 until this is at 6236/6236** (or you've confirmed
with a second run that the remaining gaps are genuinely missing upstream,
not transient — in which case note them and proceed with the rest, we'll
backfill later).

Verify the count:
```bash
find sources/audio/sahih-international -maxdepth 1 -name '*.mp3' | wc -l
# expect 6236
```

## Step 2 — publish to R2

```bash
pipeline/publish_translation_audio.sh \
    sources/audio/sahih-international \
    translation-audio/en-sahih-international
```

This is a new script (written alongside this doc) — resumable: it tracks
successfully-uploaded keys in `sources/audio/sahih-international.uploaded`
and skips them on a re-run, so it's safe to interrupt and restart, or to run
in batches. **`--remote` is baked into every `wrangler r2 object put` call
inside it — do not edit that out.** It uploads plain files (no gzip, no
catalogue.json), same as the Al-Fatihah pilot — this deliberately does NOT
follow `pipeline/publish_editions.sh`'s content-addressed/manifest pattern,
audio publishing is simpler than text editions.

This will take a while (6236 sequential `wrangler` invocations — expect this
to run for a long time, likely over an hour). Let it run to completion
rather than interrupting partway through; if it does get interrupted,
re-running the same command resumes from the manifest instead of
re-uploading everything.

If it reports any `FAILED:` lines at the end, re-run the exact same command
once — it retries only what's missing. If failures persist after a second
attempt, stop and report which specific keys keep failing rather than
continuing to retry indefinitely.

## Step 3 — verify

```bash
python3 pipeline/verify_translation_audio.py \
    sources/audio/sahih-international translation-audio/en-sahih-international
```

This is a sampling check (~40 random files checked for HTTP 200 + exact
`Content-Length` match against the local file), not a full 6236-file audit —
at this scale that's the right tradeoff (a full byte-for-byte check would
mean 6236 more HTTP requests just to verify what the publish step already
confirmed succeeded). It exits non-zero and prints specifics if anything
doesn't match.

Also re-confirm the original 7 Al-Fatihah files are still fine (this publish
uses the same prefix, so a sanity check that nothing got overwritten badly):
```bash
for n in 1 2 3 4 5 6 7; do
  url=$(printf "https://audio.alquranreader.com/translation-audio/en-sahih-international/001%03d.mp3" "$n")
  curl -s -o /dev/null -w "001$(printf %03d $n).mp3 -> HTTP %{http_code}, %{size_download} bytes\n" "$url"
done
```

## What this does NOT cover

- **Rowwad / QuranEnc audio, other translation-audio editions** — separate,
  deferred work (compression needed first for Rowwad specifically — see the
  app plan doc's open questions).
- **The app-side full-Quran wiring** — the app (`alquran-app`) currently only
  chains translation audio for Al-Fatihah (`isFatihaPocAyah` gates it). Making
  the full 6236 files actually usable in the app is separate follow-up work
  there (removing/expanding that scope gate), not part of this repo's job.
- **A `translation_audio_resources` metadata table or catalogue.json.** Not
  needed yet — the app resolves URLs by formula
  (`translationAudioUrl`/`translationAudioCacheRelativePath` in
  `../alquran-app/lib/core/audio/translation_audio_source.dart`), same as it
  does for `recitation/`. Only becomes relevant if/when the app needs a
  per-ayah availability manifest (e.g. for a future edition with gaps).

## Done-when

- [ ] `sources/audio/sahih-international/` has 6236 files (or a documented,
      re-confirmed list of upstream-missing verses).
- [ ] `pipeline/publish_translation_audio.sh` completed with 0 failures (or
      failures were retried and either resolved or reported as persistent).
- [ ] `pipeline/verify_translation_audio.py` passes (sampled files match).
- [ ] The 7 Al-Fatihah files still verify correctly (nothing regressed).
- [ ] Report back: final file count published, any upstream-missing verses,
      and confirmation the sampling check passed.
