#!/usr/bin/env bash
# Measure what the Tidal lane's own Tidal session really returns for a
# track: requested quality vs delivered codec, then the real bit rate.
# Use when a lane configured LOSSLESS looks lossy, or the user asks why a
# grab is not FLAC. Quote the measured numbers; never an adjective.
#
# Usage: probe_tidal_stream_quality.sh <track_id> [container]
set -euo pipefail

TRACK="${1:?usage: probe_tidal_stream_quality.sh <track_id> [container]}"
CTR="${2:-tidal-headless}"
PROBE="/app/downloads/_quality_probe.bin"

docker exec -i "$CTR" python3 - "$TRACK" <<'PY'
import sys, urllib.request
sys.path.insert(0, "/app")
from app.tidal import session as S

s = S._create_session()
print("configured quality:", s.config.quality)
print("user:", getattr(s.user, "id", None), getattr(s.user, "username", None))
try:
    r = s.request.request("GET", "users/{}/subscriptions".format(s.user.id))
    print("subscriptions:", r.status_code)
except Exception as exc:
    print("subscriptions: ERR", repr(exc)[:120], "(404 = no subscription)")

track_id = int(sys.argv[1])
for quality in ("LOSSLESS", "HIGH"):
    s.config.quality = quality
    try:
        stream = s.track(track_id).get_stream()
        manifest = stream.get_stream_manifest()
        print("requested {}: codecs={} audio_quality={}".format(
            quality, manifest.codecs, getattr(stream, "audio_quality", None)))
        if quality == "LOSSLESS":
            urllib.request.urlretrieve(manifest.get_urls()[0], "/app/downloads/_quality_probe.bin")
    except Exception as exc:
        print("requested {}: ERR {}".format(quality, repr(exc)[:160]))
PY

docker exec "$CTR" ffprobe -v error \
  -show_entries format=bit_rate,duration,format_name \
  -show_entries stream=codec_name,sample_rate,channels \
  -of default=nw=1 "$PROBE" || echo "probe file missing — stream fetch failed"
docker exec "$CTR" rm -f "$PROBE"
