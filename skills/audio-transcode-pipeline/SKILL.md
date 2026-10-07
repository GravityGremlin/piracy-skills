---
name: audio-transcode-pipeline
description: "Use when transcoding audio or auditing media pipelines."
version: 1.0.0
author: Community
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [ffmpeg, transcode, metadata, opus, beets, media, pipeline, audit]
    related: [flask-worker-pool-audit, media-downloader-fleet]
---

# Audio Transcode & Post-Processing Pipelines

Correctness rules for pipelines that convert audio and post-process it
(download → import → opus transcode → album art → media server). Each rule
below was found live in production code and verified empirically before being
fixed.

## 1. ffmpeg strips tags on transcode — copy metadata explicitly

`ffmpeg -y -i in.m4a -c:a libopus -b:a 160k -ac 2 out.opus` produces a
TAGLESS file: album/artist/title/ISRC are dropped (verified on ffmpeg 62.x;
the default copy is not universal across container pairs — mp3/flac→opus
default copy verified working on 8.1/62.x, so probe the output before
concluding tags were dropped). Downstream steps that read file tags —
album-art fetch, beets metadata, media servers — then silently fail, and a
whole-library maintenance pass can look healthy while doing nothing.

**Fix:** add `-map_metadata 0` before the codec args:

```bash
ffmpeg -y -i in.m4a -map_metadata 0 -c:a libopus -b:a 160k -ac 2 out.opus
```

**Verification gotcha:** ffmpeg writes the copied tags to the output's
STREAM tags. `ffprobe -v error -show_entries format_tags out.opus` comes
back EMPTY for opus/ogg — which looks exactly like a failed copy. Probe at
stream level:

```bash
ffprobe -v error -show_entries stream_tags out.opus
```

Embedded cover art (attached_pic) never survives the Ogg/Opus muxer — it has
no METADATA_BLOCK_PICTURE support — so covers must be added separately after
transcode, not relied upon from the source.

## 2. Opus encoding: use `-vbr on` and `-application audio`

Default ffmpeg opus encoding uses constrained VBR which can produce
inconsistent quality. For archival-quality opus:

```bash
ffmpeg -y -i in.flac -map_metadata 0 -c:a libopus -b:a 160k -vbr on \
  -application audio -ac 2 out.opus
```

- `-vbr on` — full variable bitrate (better quality at same average bitrate)
- `-application audio` — optimizes for music (vs. `voip` or `lowdelay`)
- `-ac 2` — force stereo (avoid silent downmix issues with multi-channel)

## 3. Never transcode from a lossy source to "lossless"

A FLAC that was transcoded from MP3 is not lossless. Check the spectral
content before labeling:

```bash
# Check for lossy encoding artifacts (frequency cutoff)
ffmpeg -i in.flac -af "highpass=f=20000,astats=metadata=1:reset=1" \
  -f null - 2>&1 | grep -i "overall"
```

A true lossless source will have content above 20kHz. A lossy transcode
will show a sharp cutoff at ~16-18kHz (MP3 128k) or ~20kHz (MP3 320k/AAC).

## 4. Batch transcode with parallel workers

For large libraries, use parallel transcoding:

```bash
# Transcode all FLACs in a directory to opus 160k, 4 parallel jobs
find /path/to/library -name "*.flac" -print0 | \
  xargs -0 -P 4 -I {} bash -c '
    out="${1%.flac}.opus"
    [ -f "$out" ] && exit 0
    ffmpeg -y -i "$1" -map_metadata 0 -c:a libopus -b:a 160k \
      -vbr on -application audio -ac 2 "$out" && rm "$1"
  ' _ {}
```

Key points:
- Skip files that already have an opus counterpart (idempotent)
- Remove source only after successful transcode
- Use `-P` matching your CPU core count

## 5. Album art handling

Album art must be extracted and re-embedded after transcode:

```bash
# Extract cover from source
ffmpeg -y -i in.flac -an -vcodec copy cover.jpg

# Embed into opus (as sidecar file, since opus doesn't support embedded art)
ffmpeg -y -i out.opus -i cover.jpg -map 0 -map 1 -c copy \
  -metadata:s:v title="Album cover" -metadata:s:v comment="Cover (front)" \
  out-with-cover.opus
```

For beets-based pipelines, configure the art filename and let beets handle
fetching and embedding.

## 6. Metadata field mapping

When transcoding between formats, metadata field names can differ:

| Source (FLAC) | Opus (Ogg) | Notes |
|---|---|---|
| `ARTIST` | `ARTIST` | Direct map |
| `ALBUM` | `ALBUM` | Direct map |
| `TITLE` | `TITLE` | Direct map |
| `TRACKNUMBER` | `TRACKNUMBER` | Direct map |
| `DISCNUMBER` | `DISCNUMBER` | Direct map |
| `DATE` | `DATE` | May need reformatting |
| `ISRC` | `ISRC` | Direct map |
| `COMPOSER` | `COMPOSER` | Direct map |
| `GENRE` | `GENRE` | Direct map |

Use `-map_metadata 0` to copy all, then verify with `ffprobe`.

## 7. Verification checklist after transcode

After any transcode batch:

1. **Tag integrity** — `ffprobe -show_entries stream_tags out.opus` shows
   expected tags
2. **Duration match** — source and output durations within ±1s
3. **No clipping** — check peak levels with `ffmpeg -i out.opus -af volumedetect -f null -`
4. **File size sanity** — opus 160k stereo ≈ 1.2MB/minute
5. **Playability** — spot-check with a media player

## Common Pipeline Patterns

### Download → Import → Transcode → Library

```
[Source] → /path/to/downloads/ (staging)
  → beets import (fetch metadata, move to library)
  → transcode to opus 160k
  → /path/to/library/ (final)
```

### Watch directory pattern

```bash
# Watch staging directory, transcode new files automatically
inotifywait -m -e close_write --format '%w%f' /path/to/downloads/ | \
while read f; do
  case "$f" in
    *.flac|*.m4a|*.mp3)
      out="${f%.*}.opus"
      ffmpeg -y -i "$f" -map_metadata 0 -c:a libopus -b:a 160k \
        -vbr on -application audio -ac 2 "$out"
      ;;
  esac
done
```

### Beets integration

In beets `config.yaml`:

```yaml
paths:
  default: $artist/$album%aunique{}/$track $title
  singleton: Non-Album/$artist/$title

plugins: info edit fromfilename

import:
  move: yes
  write: yes
  bell: yes
  duplicate_action: skip

# Transcode hook (via plugin or post-import script)
```

## Troubleshooting

### "ffmpeg returned non-zero exit code"

- Check source file integrity: `ffprobe -v error source.flac`
- Check disk space: `df -h /path/to/downloads`
- Check for special characters in filenames (quote all paths)

### "Tags are missing after transcode"

- Verify `-map_metadata 0` is present
- Check that source actually has tags: `ffprobe -show_entries format_tags source.flac`
- Remember: opus stores tags at STREAM level, not FORMAT level

### "Output file is larger than expected"

- Verify bitrate: `-b:a 160k` (not `-b:a 160000`)
- Check for accidental video stream: `-vn` to disable video
- Check sample rate: `-ar 48000` for opus
