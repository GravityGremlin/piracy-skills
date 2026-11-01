# Source-quality forensics (why a "lossless" lane delivered lossy)

Use when the user asks why a grab landed at some quality, or when a lane
configured for lossless looks lossy. Work cheapest-first and answer with
measured codec + bit rate — never an adjective like `avg` or `lossless`.

## 1. Read the lane's own download log (seconds)

The downloader names each file by the codec in the stream manifest, so the log
line alone reveals what was delivered:

```bash
docker logs tidal-headless --since 12h 2>&1 | grep -i "Downloading track"
```

A `.m4a` suffix means AAC/MP4A was fetched no matter what the config asks for;
`.flac` means lossless actually arrived.

## 2. Separate lane config from account entitlement

- Lane config chain: `tools/tidal/tidal.yaml` (`tidal.quality: LOSSLESS`)
  → `TIDAL_QUALITY` in `app/config.py` → `session.config.quality` in
  `app/tidal/session.py`. All three can say LOSSLESS while the provider still
  downgrades the stream.
- Entitlement is the real ceiling. `GET users/<id>/subscriptions` returning 404
  means the account has no subscription; such an account returns
  `codecs=MP4A`, `audio_quality=LOW` (~96-100 kbps AAC) for BOTH `LOSSLESS` and
  `HIGH` requests. That is not a misconfiguration to fix in code — it is the
  tier, and the fix is an upgrade or a different lane.
- `/health` and the aggregator `/status` report auth freshness only; they never
  reveal entitlement or delivered quality.

## 3. Measure the stream (the proof)

Run `scripts/probe_tidal_stream_quality.sh <track_id>`: it builds a session
inside the lane container, requests LOSSLESS then HIGH, prints
`codecs`/`audio_quality` for each, downloads one stream and ffprobes the real
bit rate. Quote those numbers back to the user.

`curl` is not installed in the lane containers — fetch with python `urllib`
(the script does), not shell curl.

## 4. Where the original went (policy, not loss)

`/your-stacks-path/beets/config/config.yaml`:

```yaml
convert:
    format: opus
    delete_originals: yes
    formats:
        opus:
            command: ffmpeg -i $source -y -c:a libopus -b:a 160k -ac 2 $dest
import:
    copy: no
    move: yes
```

So the library keeps one opus 160k copy and the source file exists nowhere.
Confirm the library's format mix rather than hunting for originals:

```bash
find /your-media-path/library/music-library -type f | head -2000 | sed 's/.*\.//' | sort | uniq -c | sort -rn
```

`docs/import-ordering-design-20260811.md` §1/§5 is the policy source: source as
lossless as possible, uniform opus 160k on disk.

## 5. The consequence worth stating

A 160k opus cut from ~97 kbps AAC is double-lossy: generational loss, plus 160k
of bits spent carrying a small source. When a genuinely lossless source shows
up, re-grab the album — and remove the existing album dir first, because the
organizer dedupes imports against library holdings and will otherwise route the
new files into the old copy or skip them.

## 6. Lossless sources when the provider lanes are capped

- slskd (opt-in lane) is the practical lossless path when provider tiers cap
  out. Probe before promising, and read `filename` extensions plus sample paths:
  a peer directory tagged `[WEB FLAC]` is real, while a bare artist-name search
  returns mostly substring matches on unrelated artists.
- Qobuz is the lossless-first lane; a lane storing only token + user_id cannot
  self-heal an expired token and needs a human re-login (see SKILL.md Auth).
