#!/usr/bin/env python3
"""
Upload Qur'an translation audio files to R2 with aggressive parallelism.

Uploads all files in sources/audio/sahih-international/ for ayahs 4500-6236
(Surahs ~38-114) using wrangler with 16+ concurrent workers.

Usage:
    python pipeline/upload_audio.py
"""
import subprocess
import sqlite3
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import time


def get_ayah_mapping(db_path: Path) -> dict[int, tuple[int, int]]:
    """Load global_ayah_id -> (surah_id, ayah_number) mapping from database."""
    mapping = {}
    c = sqlite3.connect(db_path)
    try:
        # Get mapping from database for ayahs 4500-6236
        rows = c.execute(
            "SELECT id, surah_id, ayah_number FROM ayahs WHERE id >= 4500 AND id <= 6236 ORDER BY id"
        ).fetchall()
        for global_id, surah_id, ayah_number in rows:
            mapping[global_id] = (surah_id, ayah_number)
    finally:
        c.close()
    return mapping


def generate_filenames() -> list[tuple[int, str]]:
    """Generate SSSAAA.mp3 filenames for ayahs 4500-6236."""
    db_path = Path("assets/quran.db")
    ayah_mapping = get_ayah_mapping(db_path)

    filenames = []
    for global_id in sorted(ayah_mapping.keys()):
        surah_id, ayah_number = ayah_mapping[global_id]
        filename = f"{surah_id:03d}{ayah_number:03d}.mp3"
        filenames.append((global_id, filename))

    return filenames


def upload_file(filename: str, source_dir: Path) -> tuple[str, bool, str]:
    """Upload a single file to R2. Returns (filename, success, message)."""
    source_file = source_dir / filename

    # Skip if file doesn't exist
    if not source_file.exists():
        return (filename, False, "File not found locally - skipped")

    # Construct R2 path
    r2_path = f"al-quran-audio/translation-audio/en-sahih-international/{filename}"

    # Build wrangler command
    cmd = [
        "npx",
        "--yes",
        "wrangler",
        "r2",
        "object",
        "put",
        r2_path,
        "--file",
        str(source_file),
        "--remote",
        "--content-type",
        "audio/mpeg",
        "--cache-control",
        "public, max-age=31536000, immutable"
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode == 0:
            return (filename, True, "Uploaded")
        else:
            error = result.stderr or result.stdout
            return (filename, False, f"Upload failed: {error[:100]}")
    except subprocess.TimeoutExpired:
        return (filename, False, "Timeout (60s)")
    except Exception as e:
        return (filename, False, f"Error: {str(e)[:100]}")


def main():
    """Main upload routine."""
    source_dir = Path("sources/audio/sahih-international")

    if not source_dir.exists():
        print(f"Error: {source_dir} does not exist")
        return

    start_time = datetime.now()
    print(f"[{start_time.strftime('%H:%M:%S')}] Generating filenames for ayahs 4500-6236...")

    # Generate list of files to upload
    filenames = generate_filenames()
    total_files = len(filenames)
    print(f"Found {total_files} ayahs to process")

    # Track results
    uploaded = 0
    skipped = 0
    failed = 0
    failed_files = []

    # Use ThreadPoolExecutor with aggressive parallelism
    max_workers = 32  # Use 32 concurrent workers for maximum throughput

    print(f"\nUploading with {max_workers} concurrent workers...")
    print("=" * 80)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all upload tasks
        futures = {
            executor.submit(upload_file, filename, source_dir): filename
            for _, filename in filenames
        }

        # Process completed uploads
        completed = 0
        for future in as_completed(futures):
            filename, success, message = future.result()
            completed += 1

            if success:
                uploaded += 1
                status = "✓"
            else:
                if "not found" in message.lower():
                    skipped += 1
                    status = "○"
                else:
                    failed += 1
                    failed_files.append((filename, message))
                    status = "✗"

            # Progress indicator every 100 files
            if completed % 100 == 0:
                elapsed = (datetime.now() - start_time).total_seconds()
                rate = completed / elapsed
                remaining = (total_files - completed) / rate if rate > 0 else 0
                print(f"  [{completed}/{total_files}] {status} {filename}  "
                      f"~{remaining:.0f}s remaining")

    # Print summary
    elapsed = (datetime.now() - start_time).total_seconds()
    print("=" * 80)
    print(f"\nUpload Complete!")
    print(f"  Total time:  {elapsed:.1f}s")
    print(f"  Uploaded:    {uploaded:,} files")
    print(f"  Skipped:     {skipped:,} files (not found locally)")
    print(f"  Failed:      {failed:,} files")

    if failed_files:
        print(f"\nFailed uploads:")
        for filename, error in failed_files[:10]:  # Show first 10 failures
            print(f"  {filename}: {error}")
        if len(failed_files) > 10:
            print(f"  ... and {len(failed_files) - 10} more")

    # Compute rates
    if uploaded > 0:
        upload_rate = uploaded / elapsed
        print(f"\nUpload rate: {upload_rate:.1f} files/sec")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit(main())
