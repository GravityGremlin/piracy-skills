---
name: media-library-ops
description: "Use when deduping or maintaining a media library."
version: 1.0.0
author: Gravis Wellz
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [media, dedupe, library, beets, maintenance]
    related: [media-downloader-fleet, media-grabber]
---

# Media Library Operations

Canonical library: `/your-media-path/library` (the directory your import pipeline imports
into and your media server serves from).

**Core principle: every removal is a MOVE to quarantine, never a delete.**
Quarantine root: `/your-media-path/quarantine/<topic>-<date>/`.
Verify file counts after every pass (moved + kept must equal before-count).

---

## Keeper Rules

User-standard rules — apply every pass:

- One copy per canonical studio album; lives/comps/remixes/fragments out.
- Explicit only — clean/radio/edited versions never kept when explicit exists.
- Most-complete edition wins (deluxe/expanded/bonus sets).
- Beets opus copy wins over legacy FLAC **within the library** (the corpus is
  opus-by-convention). This is NOT a licence to drop a lossless copy held
  elsewhere: a staging/quarantine FLAC whose album already has a lossy library
  counterpart is the only lossless master of that recording, so it is
  keep-or-decide-explicitly, never a duplicate to sweep.
- A truncated or damaged library copy is worse than a lossy one: if the library
  recording's duration is far short of the quarantine source, the quarantine
  FLAC is the only correct master — transcode to the library codec, replace the
  bad file, and update Beets length. Never sweep the source to "fix" a bad
  library copy.
- Before calling anything a duplicate, confirm it at CONTENT level — a matching
  artist/album dir, or even a matching title, is not the same recording. Compare
  duration (±2s) and codec/bitrate, and when both sides are real, keep the
  better one rather than dropping the source.
- Trimmed twin tracks go to `_trimmed/` inside the quarantine dir; renumber
  the album's remaining tracks continuous afterwards (gaps confuse players
  and media servers).
- Zero-byte files are never keepers — they are failed downloads or corrupt
  transfers. Quarantine them for inspection, never delete outright.
- Classical music: multi-disc sets with work/movement numbering need special
  handling — the "one copy per album" rule applies to the work, not the
  recording. Keep the best recording of each work.

### Temp / orphan sweep

Conversion temps (`tmp*` written beside a destination before an atomic rename) are left
behind when a transcode run is interrupted. They accumulate silently (hundreds of files,
gigabytes) and read like real files to a casual sweep. Sweep `tmp*` under the library root
as part of the maintenance pass, not ad hoc. Before deleting, confirm redundancy: a
matching final file present (same size/tags/duration), or the temp dates from a known
interrupted run while today's temporaries rename correctly. Verify the moved+kept count
equals before-count like any other pass.

---

## Deduplication Workflow

### Phase 0: Census

Run a full library census before any mutation:

```bash
# Count all audio files by format
find /path/to/library -type f \( -name "*.opus" -o -name "*.flac" -o -name "*.mp3" -o -name "*.m4a" \) | \
  sed 's/.*\.//' | sort | uniq -c

# Count total size
du -sh /path/to/library

# Find zero-byte files
find /path/to/library -type f -empty

# Find empty artist dirs (no audio files)
find /path/to/library -type d -empty
```

### Phase 1: Duplicate Detection

Cluster potential duplicates by:
- Artist name (normalized: casefold, strip non-alnum)
- Album name (normalized: casefold, strip accents, strip year qualifier)
- Track count
- Total duration

```python
# Normalization function for matching
import unicodedata
import re

def normalize(name: str) -> str:
    # Strip accents
    name = unicodedata.normalize('NFKD', name)
    name = ''.join(c for c in name if not unicodedata.combining(c))
    # Casefold and strip non-alphanumeric
    name = name.casefold()
    name = re.sub(r'[^a-z0-9]', '', name)
    # Strip trailing year qualifier
    name = re.sub(r'\(\d{4}\)$', '', name)
    return name
```

### Phase 2: Quarantine Moves

Move duplicates to quarantine, never delete:

```bash
# Create quarantine dir
mkdir -p /path/to/quarantine/dupes-$(date +%Y%m%d)

# Move duplicate album (example)
mv /path/to/library/Artist/Album (Deluxe)/ /path/to/quarantine/dupes-$(date +%Y%m%d)/

# Verify counts
echo "Before: $(find /path/to/library -name '*.opus' | wc -l)"
echo "After:  $(find /path/to/library -name '*.opus' | wc -l)"
echo "Moved:  $(find /path/to/quarantine/dupes-$(date +%Y%m%d) -name '*.opus' | wc -l)"
```

### Phase 3: Gap Backfill

After removing duplicates, check for missing tracks:

```bash
# Find albums with gaps in track numbering
for dir in /path/to/library/*/*/; do
  tracks=$(ls "$dir" | grep -oP '^\d+' | sort -n)
  max=$(echo "$tracks" | tail -1)
  count=$(echo "$tracks" | wc -l)
  if [ "$count" -lt "$max" ]; then
    echo "GAP: $dir (has $count tracks, max number $max)"
  fi
done
```

## Library Maintenance Scripts

### Audit Script (read-only)

```python
#!/usr/bin/env python3
"""Audit a media library for duplicates, gaps, and anomalies."""
import os
import sys
import json
import hashlib
from pathlib import Path
from collections import defaultdict

def audit_library(root: str):
    root = Path(root)
    findings = {
        'total_files': 0,
        'total_size': 0,
        'by_format': defaultdict(int),
        'zero_byte': [],
        'empty_dirs': [],
        'duplicate_candidates': [],
        'gap_albums': [],
    }
    
    for dirpath, dirnames, filenames in os.walk(root):
        audio_files = [f for f in filenames if f.endswith(('.opus', '.flac', '.mp3', '.m4a'))]
        
        if not audio_files and not dirnames:
            findings['empty_dirs'].append(dirpath)
        
        for f in audio_files:
            fp = Path(dirpath) / f
            size = fp.stat().st_size
            findings['total_files'] += 1
            findings['total_size'] += size
            findings['by_format'][f.split('.')[-1]] += 1
            
            if size == 0:
                findings['zero_byte'].append(str(fp))
    
    return findings

if __name__ == '__main__':
    root = sys.argv[1] if len(sys.argv) > 1 else '/path/to/library'
    findings = audit_library(root)
    print(json.dumps(findings, indent=2, default=str))
```

### Dedupe Script (with --dry-run)

```python
#!/usr/bin/env python3
"""Find and optionally move duplicate albums."""
import os
import sys
import shutil
import argparse
from pathlib import Path
from collections import defaultdict

def find_duplicates(root: str):
    """Find albums with the same normalized artist+album name."""
    albums = defaultdict(list)
    
    for dirpath, dirnames, filenames in os.walk(root):
        audio_files = [f for f in filenames if f.endswith(('.opus', '.flac', '.mp3', '.m4a'))]
        if not audio_files:
            continue
        
        # Extract artist/album from path
        rel = Path(dirpath).relative_to(root)
        parts = rel.parts
        if len(parts) >= 2:
            artist, album = parts[0], parts[1]
            key = (normalize(artist), normalize(album))
            albums[key].append({
                'path': dirpath,
                'file_count': len(audio_files),
                'total_size': sum(os.path.getsize(os.path.join(dirpath, f)) for f in audio_files),
            })
    
    # Return only groups with more than one entry
    return {k: v for k, v in albums.items() if len(v) > 1}

def normalize(name: str) -> str:
    import unicodedata
    import re
    name = unicodedata.normalize('NFKD', name)
    name = ''.join(c for c in name if not unicodedata.combining(c))
    name = name.casefold()
    name = re.sub(r'[^a-z0-9]', '', name)
    name = re.sub(r'\(\d{4}\)$', '', name)
    return name

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('root')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--quarantine', default='/path/to/quarantine')
    args = parser.parse_args()
    
    dupes = find_duplicates(args.root)
    
    for (artist, album), entries in dupes.items():
        print(f"\nDuplicate: {artist} / {album}")
        # Keeper = most files, then largest size, then alphabetical
        entries.sort(key=lambda e: (-e['file_count'], -e['total_size'], e['path']))
        keeper = entries[0]
        print(f"  KEEP: {keeper['path']} ({keeper['file_count']} files)")
        for e in entries[1:]:
            print(f"  MOVE: {e['path']} ({e['file_count']} files)")
            if not args.dry_run:
                dest = Path(args.quarantine) / f"dupes-{artist[:20]}"
                dest.mkdir(parents=True, exist_ok=True)
                shutil.move(e['path'], dest / Path(e['path']).name)
```

## Media Server Integration

After any library mutation, media server indexes are stale until rebuilt:

- **Watch-folder server** — auto-imports within ~90s, or trigger via admin UI
- **Folder-scan server** — run "Scan Library" or wait for the scheduled scan
- **Metadata-driven server** — run "Scan Library Files" or "Refresh All Metadata"
- **CLI-importer server** — run `manage.py import_files` or wait for the watcher

Set `MEDIA_API_KEY` to your media server's API key (admin UI → Settings → API Keys),
then verify with read-only queries:

```bash
# Media server: check song count
sqlite3 "/path/to/media-server.db" "SELECT COUNT(*) FROM song;"  # your media server db file

# Media server: check item count via API
curl -s "http://media-server-host:8096/Items?Recursive=true&IncludeItemTypes=Audio" \
  -H "X-Emby-Token: $MEDIA_API_KEY" | python3 -c "import json,sys; print(json.load(sys.stdin)['TotalRecordCount'])"
```

## Playlist Maintenance

After library changes, playlists may reference moved/deleted files:

```bash
# Find broken playlist entries
while IFS= read -r line; do
  [ -f "$line" ] || echo "BROKEN: $line"
done < /path/to/library/playlists/playlist.m3u8
```

Rebuild playlists by matching against the current library:

```python
#!/usr/bin/env python3
"""Rebuild playlists by matching entries against current library."""
import os
from pathlib import Path

def rebuild_playlist(playlist_path: str, library_root: str):
    library_files = set()
    for dirpath, _, filenames in os.walk(library_root):
        for f in filenames:
            if f.endswith(('.opus', '.flac', '.mp3', '.m4a')):
                library_files.add(os.path.join(dirpath, f))
    
    # Index by filename for matching
    by_name = {}
    for f in library_files:
        name = os.path.basename(f)
        by_name.setdefault(name, []).append(f)
    
    with open(playlist_path) as f:
        entries = [l.strip() for l in f if l.strip() and not l.startswith('#')]
    
    matched = []
    unmatched = []
    for entry in entries:
        name = os.path.basename(entry)
        if name in by_name:
            matched.append(by_name[name][0])
        else:
            unmatched.append(entry)
    
    # Write rebuilt playlist
    with open(playlist_path, 'w') as f:
        f.write('#EXTM3U\n')
        for m in matched:
            f.write(m + '\n')
    
    print(f"Matched: {len(matched)}, Unmatched: {len(unmatched)}")
    if unmatched:
        print("Unmatched entries:")
        for u in unmatched:
            print(f"  {u}")
```

## Storage Management

### Disk Space Monitoring

```bash
# Check library filesystem usage
df -h /path/to/library

# Find largest directories
du -h /path/to/library | sort -rh | head -20

# Find files larger than expected (e.g., > 500MB for a single track)
find /path/to/library -type f -size +500M
```

### Multi-Root Storage

If the library spans multiple mounts, the import pipeline should support
multiple staging roots:

```yaml
# import pipeline config
staging_roots:
  - /path/to/staging-1
  - /path/to/staging-2
library_root: /path/to/library
```

The import pipeline watches all staging roots and imports into the single library.

## Recovery Procedures

### Recovering from a Bad Import

If beets imported files with wrong metadata:

1. **Stop the import pipeline** (prevent further imports)
2. **Identify the bad import** (check recent beets logs)
3. **Move the bad files to quarantine**
4. **Fix the metadata source** (MusicBrainz, Discogs, etc.)
5. **Re-import with correct metadata**
6. **Restart the import pipeline**

### Recovering from Accidental Deletion

If files were accidentally deleted (not moved to quarantine):

1. **Check if the media server has a cache** (some do)
2. **Check if the files exist in the staging area** (not yet imported)
3. **Check if the files exist in a backup** (if you have one)
4. **If all else fails, re-download** (use the media-grabber skill)

## Best Practices

- **Always dry-run first** — every mutation script should have a `--dry-run` mode
- **Verify counts after every pass** — moved + kept must equal before-count
- **Quarantine, never delete** — you can always delete from quarantine later
- **Document every pass** — what was moved, why, and when
- **Backup before major operations** — at minimum, a file listing
- **Test on a subset first** — run dedup on one artist before the whole library
- **Monitor disk space** — a full filesystem breaks everything
