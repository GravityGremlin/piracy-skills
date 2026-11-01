# P2P lossless verification — is this "FLAC" actually lossless?

Use before calling a P2P grab "real lossless", and when a user doubts a
track's quality history ("that song never existed above 128 kbps"). The
extension, size and bitrate a peer advertises prove nothing; the spectral
content does.

## The test (spectral cutoff + calibration)

Decode the suspect to mono f32 @48 kHz and average its STFT spectrum over the
loud half of frames; measure energy in bands RELATIVE to the 200 Hz–5 kHz
median. A 128k MP3 ancestor leaves a dead wall above ~16.4 kHz; a genuine
lossless ancestor keeps natural content to ~20 kHz. The test works THROUGH an
opus 160k transcode of the source (the library's converted copies included) —
the ancestor's wall survives the re-encode.

Worked numbers from one calibrated session (dB relative to low-band median):

| ancestry | 17.5–18.5k | 19.5–20k |
|---|---|---|
| lossless → opus controls | −24 to −30 | −25 to −34 |
| 128k MP3 (CBR) | −93 | −92 |
| LAME 128k calibration | −97 | −99 |
| 128k → FLAC → opus160 ("fake lossless") | −50 | −52 |

Verdict heuristics: −80 dB or lower at 17.5k = lossy ancestry (128k-class
wall). Between −40 and −60 = compare against a same-session fake-chain
calibration (opus coding noise floats this band; the fake chain measured −50,
nowhere near −90). −45 or higher = better-than-128k ancestry.

## Run it

    python3 scripts/spectral_cutoff.py SUSPECT [SUSPECT...] --calibrate KNOWN_LOSSLESS

`--calibrate` encodes a known-lossless control to LAME 128k and to the fake
128k→FLAC→opus chain, so verdicts compare against numbers from THIS session,
not folklore. Requires ffmpeg + numpy. Quote the band numbers, never an
adjective — the measured table is the artifact the user accepts.

## Frame-level arithmetic: bitrate from the frames, not the file

A size ÷ duration average LIES when a fat ID3 tag rides along — one measured
CBR 128k file with an 89 KB cover tag averaged ~139.7 kbps, reading as
“~140 VBR” to anyone not excluding tag bytes. Parse MPEG frame headers
instead, in the same session as the spectral test:

- frame count × (1152 samples ÷ 44100 Hz) = exact audio duration (e.g. 2,346
  frames → 61.14 s) — use it to pin which lineage/mastering a file is, since
  durations differ across remasters;
- a constant bitrate index across EVERY frame with no Xing/Info header =
  genuine CBR — state the frame-derived rate (exactly 128 kbps), never the
  file-average, and treat a size-derived "VBR ~140" as an artifact until the
  frames say otherwise.

## Get the master before it's gone

slskd's complete dir (`/your-media-path/slskd/complete/**`) is transient: the lane
cleans landed downloads after the organizer handoff (observed: master files
gone within hours of a successful import, empty dirs left behind). If the
original is wanted — forensics, archival, comparing lineages — copy it out
BEFORE the organizer import completes. Afterward only the organizer's opus
remains; the spectral history survives the transcode, the master's bytes do
not.
