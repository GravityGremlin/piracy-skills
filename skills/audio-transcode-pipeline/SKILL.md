---
name: audio-transcode-pipeline
description: "Use when transcoding audio or auditing music pipelines."
version: 1.0.0
author: Gravis Wellz
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [ffmpeg, transcode, metadata, opus, beets, music, pipeline, audit]
    related: [flask-worker-pool-audit, media-downloader-fleet, transcode-fleet-ops]
---

# Audio Transcode & Post-Processing Pipelines

Correctness rules for pipelines that convert audio and post-process it
(download → import → opus transcode → album art → music server). Each rule
below was found live in production code (the downloader fleet) and verified
empirically before being fixed.

## 1. ffmpeg strips tags on transcode — copy metadata explicitly

`ffmpeg -y -i in.m4a -c:a libopus -b:a 160k -ac 2 out.opus` produces a
TAGLESS file: album/artist/title/ISRC are dropped (verified on ffmpeg 62.x;
the default copy is not universal across container pairs — mp3/flac→opus default copy verified working on 8.1/62.x, so probe the output before concluding tags were dropped). Downstream steps that read file tags —
album-art fetch, beets metadata, Navidrome — then silently fail, and a
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

Embedded cover art (attached_pic) never survives the Ogg/Opus muxer — it has
no METADATA_BLOCK_PICTURE support — so covers must come from the album-art
fetch step, not the source file (verified: mp3 with embedded cover → opus
keeps all text tags, drops the picture).
```

Input side is the reverse: m4a/mp3 tags show under `format_tags` (or
`stream_tags` for ogg). The asymmetry between input and output probe levels
is what makes a working `-map_metadata 0` copy look broken.

## 2. Best-effort post-import steps must run after the DONE transition

Enrichment/conversion/art passes after an import (opus transcode, album-art
fetch+embed) are best-effort by design, but if they run INSIDE the job's
try block before `transition(job, DONE)`, any unexpected exception — a bug
in the enrich code, an OSError, an escaped network error — lands in the
generic `except` and flips a SUCCESSFUL import into READY/retry, skipping
staging cleanup and re-importing later.

**Correct order:** transition(DONE) → audit → staging cleanup → enrich,
with the enrich call itself wrapped in `try/except Exception: log.exception(...)`.
This also frees the staging dir before slow network/transcode work, and a
crash mid-enrichment is self-healing (the periodic whole-library sweep
finishes the job).

## 3. Album-art fetch: never guess from artist alone

Fetching art for a dir whose first audio file has no album tag (singletons,
untagged uploads, or files whose tags a transcode stripped) returns the
first matching ALBUM from the art API — wrong cover embedded on a single.

Guard:
- require a non-empty album tag before fetching (`if not album: return False`);
- skip the beets singleton tree (`Non-Album/`) in whole-library passes;
- run the art scan AFTER tag-preserving conversion — fresh opus files are
  otherwise tagless and nothing resolves.

Also: embed support is format-dependent (opus/ogg/m4a/flac/mp3 via mutagen;
ID3 frames need TPE2/TPE1/TALB mapping for mp3). If the embed step only
handles some formats, say so in the docstring — cover.jpg still gets
written, embedded tags don't.

## 4. Never let the transcode destination equal the source — suffix-swap self-delete

Found live (organizer/engine.py, 2026-08-11 audit; reproduced empirically).
Converters that derive the output path by swapping the source suffix are a
data-loss landmine:

```python
dst = src.with_suffix(".opus")
if dst.exists():
    # "adopt twin" branch — UPDATE path, then src.unlink()   # DANGER
```

When the source ALREADY has the target extension, `dst == src`, so the
"adopt twin / drop the source" branch deletes the very file it was asked to
convert — and counts it as "converted". In the fleet this silently deleted
freshly imported library files on every import: the DB row survived, so the
identity-dedup gate then skipped re-downloads as "already in library" —
effectively unrecoverable without manual DB surgery. The trigger was a
post-import enrich SELECT with NO format filter feeding already-opus items
into the converter.

**Both fixes, not one:**
- Filter the input query so already-target-format rows never reach the
  converter (`WHERE lower(CAST(path AS TEXT)) NOT LIKE '%.opus'`), mirroring
  whatever the whole-library maintenance scan already excludes.
- Defensively `if dst == src: continue` before any unlink/adopt branch —
  cheap, and protects every future caller.

**Blast-radius note:** check WHEN the unfiltered path landed relative to the
last known-healthy library audit; items imported in that window are missing
files with live DB rows, and the dedup gate hides them from re-download.

## 5. "Adopt twin" conversion branches must guard `dst == src`

A convert routine that keeps an existing output twin and deletes the source
(`dst = src.with_suffix(".opus"); if dst.exists(): unlink(src)`) SELF-DELETES
the file when the input is already in the target format — for an `.opus`
item, `dst == src` and the "adopt" branch unlinks the file it was supposed
to preserve. Found live in the downloader fleet's organizer enrich path (2026-08-11):
an unfiltered post-import SELECT fed already-opus items into exactly this
branch — silent data loss on the happy path, and the surviving DB row makes
dedup skip re-downloads (unrecoverable without DB surgery).

Two-layer fix:
- The caller's SELECT excludes passthrough suffixes (mirror the maintenance
  scan's `NOT LIKE '%.opus' / '%.mp3'`), and
- the convert loop guards `if dst == src: continue` before the adopt branch,
  so no caller can ever trigger the self-delete.

## 6. Conversion SELECTs must exclude already-target-format rows

Found live 2026-08-10 (organizer enrich pass, fixed in b5635ae): an
enrichment query that feeds EVERY fresh row into a "convert to opus" helper
can self-delete. For an already-`.opus` path, `dst = src.with_suffix(".opus")`
yields `dst == src`, and the "adopt twin" branch (which unlinks the source)
then deletes the library file the DB row still points at — counted as
"converted". The DB row survives, so identity dedup skips re-downloads as
"already in library" → effectively unrecoverable without manual DB surgery.

Two-layer guard (both required):
1. Filter at the SELECT, mirroring the maintenance query:
   `AND lower(CAST(path AS TEXT)) NOT LIKE '%.opus' AND NOT LIKE '%.mp3'`.
2. In the converter: `if dst == src: continue` before the adopt branch —
   never unlink a file onto its own path, regardless of caller.

## Audit checklist

- [ ] Every ffmpeg transcode in the pipeline includes `-map_metadata 0`?
- [ ] Conversion SELECTs exclude already-target-format paths (%.opus/%.mp3)
      AND the converter skips `dst == src` (self-delete guard)?
- [ ] "Adopt twin" convert branches guard `dst == src` (no self-unlink)?
- [ ] Enrichment/art steps run after the job's DONE transition, wrapped in
      try/except that only logs?
- [ ] Art fetch requires a non-empty album tag / skips singletons?
- [ ] Verify tag preservation at the STREAM level, not format level?
- [ ] Every converter guards `if dst == src` before an unlink/adopt branch,
      and every input query excludes already-target-format rows?
- [ ] Auditing a library for "opus 160k": mp3 inputs pass through
      unconverted by design — 128–192k mp3 files are expected output, not a
      missed/broken conversion (only lossless is opus-targeted)?

## Consumed by

- **music-downloader-fleet-pipeline** — opus 160k transcode
- **tdarr-fleet-ops** — AV1/HEVC video path
- **flask-worker-pool-audit** — worker calls
