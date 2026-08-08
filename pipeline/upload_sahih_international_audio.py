#!/usr/bin/env python3
"""
Upload Qur'an Sahih International translation audio files to R2.
Uploads ayahs 1-2000 (Surahs 1-16) with aggressive parallelism.
"""

import os
import sys
import subprocess
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
import argparse


# Surah ayah counts (from Qur'an structure)
SURAH_AYAH_COUNTS = {
    1: 7, 2: 286, 3: 200, 4: 176, 5: 120, 6: 165, 7: 206, 8: 75,
    9: 129, 10: 109, 11: 123, 12: 111, 13: 43, 14: 52, 15: 99, 16: 128,
}


def get_sssaaa_from_global_ayah(global_ayah_num):
    """Convert global ayah number (1-6236) to SSSAAA format (e.g., 001001)."""
    cumulative = 0
    for surah in sorted(SURAH_AYAH_COUNTS.keys()):
        ayah_count = SURAH_AYAH_COUNTS[surah]
        if cumulative + ayah_count >= global_ayah_num:
            ayah_in_surah = global_ayah_num - cumulative
            return f"{surah:03d}{ayah_in_surah:03d}"
        cumulative += ayah_count
    raise ValueError(f"Global ayah {global_ayah_num} out of range")


def upload_file(sssaaa, audio_dir, stats_lock, stats):
    """Upload a single audio file to R2."""
    local_path = audio_dir / f"{sssaaa}.mp3"

    # Check if file exists
    if not local_path.exists():
        with stats_lock:
            stats['skipped'] += 1
        return {
            'filename': sssaaa,
            'status': 'skipped',
            'message': 'File not found locally'
        }

    # Build wrangler command
    remote_path = f"al-quran-audio/translation-audio/en-sahih-international/{sssaaa}.mp3"
    cmd = [
        'npx', '--yes', 'wrangler', 'r2', 'object', 'put',
        remote_path,
        '--file', str(local_path),
        '--remote',
        '--content-type', 'audio/mpeg',
        '--cache-control', 'public, max-age=31536000, immutable'
    ]

    try:
        result = subprocess.run(
            cmd,
            cwd=os.path.dirname(os.path.abspath(__file__)) + "/..",
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode == 0:
            with stats_lock:
                stats['uploaded'] += 1
            return {
                'filename': sssaaa,
                'status': 'success',
                'message': 'Uploaded'
            }
        else:
            with stats_lock:
                stats['failed'] += 1
            return {
                'filename': sssaaa,
                'status': 'failed',
                'message': result.stderr[:100] if result.stderr else 'Unknown error'
            }

    except subprocess.TimeoutExpired:
        with stats_lock:
            stats['failed'] += 1
        return {
            'filename': sssaaa,
            'status': 'failed',
            'message': 'Timeout (60s)'
        }
    except Exception as e:
        with stats_lock:
            stats['failed'] += 1
        return {
            'filename': sssaaa,
            'status': 'failed',
            'message': str(e)[:100]
        }


def main():
    parser = argparse.ArgumentParser(
        description='Upload Qur\'an Sahih International audio files to R2'
    )
    parser.add_argument(
        '--audio-dir',
        type=Path,
        default=Path('/Users/mohammadarif/code/alquran-data/sources/audio/sahih-international'),
        help='Path to audio files directory'
    )
    parser.add_argument(
        '--workers',
        type=int,
        default=32,
        help='Number of concurrent workers (default: 32, min: 16)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=2000,
        help='Limit to first N ayahs (default: 2000)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show files to upload without actually uploading'
    )

    args = parser.parse_args()

    # Validate workers
    workers = max(args.workers, 16)

    audio_dir = args.audio_dir
    if not audio_dir.exists():
        print(f"Error: Audio directory not found: {audio_dir}")
        sys.exit(1)

    # Generate list of files to upload for ayahs 1 to limit
    files_to_upload = []
    for global_ayah in range(1, args.limit + 1):
        sssaaa = get_sssaaa_from_global_ayah(global_ayah)
        files_to_upload.append(sssaaa)

    print(f"Audio directory: {audio_dir}")
    print(f"Target ayahs: 1-{args.limit} ({len(files_to_upload)} files)")
    print(f"Concurrent workers: {workers}")

    if args.dry_run:
        print(f"\nDRY RUN: Files to upload:")
        existing = 0
        missing = 0
        for sssaaa in files_to_upload:
            if (audio_dir / f"{sssaaa}.mp3").exists():
                print(f"  ✓ {sssaaa}.mp3")
                existing += 1
            else:
                print(f"  ✗ {sssaaa}.mp3 (missing)")
                missing += 1
        print(f"\nExisting: {existing}, Missing: {missing}")
        return

    # Upload files with progress tracking
    stats = {
        'uploaded': 0,
        'skipped': 0,
        'failed': 0,
    }
    stats_lock = Lock()

    print(f"\nStarting upload with {workers} workers...\n")
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=workers) as executor:
        # Submit all tasks
        futures = {
            executor.submit(upload_file, sssaaa, audio_dir, stats_lock, stats): sssaaa
            for sssaaa in files_to_upload
        }

        # Process results as they complete
        completed = 0
        for future in as_completed(futures):
            completed += 1
            result = future.result()

            # Print progress every 50 files
            if completed % 50 == 0 or result['status'] == 'failed':
                status_icon = {
                    'success': '✓',
                    'skipped': '⊘',
                    'failed': '✗'
                }.get(result['status'], '?')

                print(f"[{completed:4d}/{len(files_to_upload)}] {status_icon} {result['filename']}.mp3")

    elapsed = time.time() - start_time

    # Final report
    print(f"\n{'='*60}")
    print(f"UPLOAD COMPLETE")
    print(f"{'='*60}")
    print(f"Uploaded:  {stats['uploaded']:6d}")
    print(f"Skipped:   {stats['skipped']:6d} (already uploaded)")
    print(f"Failed:    {stats['failed']:6d}")
    print(f"Total:     {stats['uploaded'] + stats['skipped'] + stats['failed']:6d}")
    print(f"Time:      {elapsed:.1f}s ({len(files_to_upload)/elapsed:.0f} files/sec)")
    print(f"{'='*60}")

    return 0 if stats['failed'] == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
