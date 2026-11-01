---
name: youtube-content
description: "YouTube transcripts to summaries, threads, blogs."
version: 1.0.0
author: Gravis Wellz
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [YouTube, Video, Transcripts, Media]

---

# YouTube Content Tool

Extract transcripts from YouTube videos and convert them into structured content (chapters, summaries, threads, blog posts).

## When to use

Use when the user shares a YouTube URL or video link, asks to summarize a video, requests a transcript, or wants to extract and reformat content from any YouTube video.

## Setup

```bash
# Install dependency into current environment
uv pip install youtube-transcript-api
# or pip install youtube-transcript-api
```

## Helper script

```bash
# JSON output with metadata
uv run python SKILL_DIR/scripts/fetch_transcript.py "https://youtube.com/watch?v=VIDEO_ID"

# Plain text (good for piping)
uv run python SKILL_DIR/scripts/fetch_transcript.py "URL" --text-only

# With timestamps
uv run python SKILL_DIR/scripts/fetch_transcript.py "URL" --timestamps

# Specific language with fallback chain
uv run python SKILL_DIR/scripts/fetch_transcript.py "URL" --language tr,en
```

Supported URL formats: standard watch, youtu.be, shorts, embed, live, or raw 11-char video ID.

## Output formats

After fetching the transcript, format it based on the request:

- **Chapters**: Group by topic shifts → timestamped chapter list
- **Summary**: Concise 5-10 sentence overview
- **Thread**: Twitter/X-style thread (1 tweet per key point, ~280 chars each)
- **Blog post**: Structured markdown with H2 sections, intro/conclusion, pull quotes

## Transcript quality notes

- Auto-generated captions: ~90% accuracy, speaker labels often missing
- Manual captions: higher accuracy, may include speaker names
- No captions available → skill returns error (no fallback to ASR)
- Multiple languages → specify `--language` or accept first available

## Example workflow

```bash
# 1. Fetch transcript
uv run python fetch_transcript.py "https://youtu.be/dQw4w9WgXcQ" --json > transcript.json

# 2. Process to desired format
# (Use LLM or custom script with transcript.json as input)
```

## Limitations

- Requires captions to exist on the video
- Rate-limited by YouTube (no official API used)
- Private/unlisted videos need cookies/auth (not supported)
- Live streams without saved captions return empty