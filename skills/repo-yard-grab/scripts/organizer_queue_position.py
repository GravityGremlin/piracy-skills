#!/usr/bin/env python3
"""organizer_queue_position.py — where does an artist sit in the organizer READY backlog?

Reads the organizer queue manifests directly off the host (root-owned docker
volume, so run under sudo). Sort key mirrors organizer/queue.py: (priority,
created_at) — priority 0=uploads, 1=interactive downloads, 2=discography batch.

Usage: sudo python3 organizer_queue_position.py "System of a Down"
"""

import json
import os
import re
import sys
from collections import Counter

QUEUE_ROOT = os.environ.get(
    "ORGANIZER_QUEUE_ROOT_HOST",
    "/var/lib/docker/volumes/fleet_organizer-data/_data/queue",
)


def norm(s):
    return re.sub(r"\s+", " ", (s or "").strip().casefold())


def main():
    want = norm(sys.argv[1] if len(sys.argv) > 1 else "")
    if not want:
        sys.exit("usage: sudo python3 organizer_queue_position.py \"<artist>\"")
    ready = os.path.join(QUEUE_ROOT, "READY")
    if not os.path.isdir(ready):
        sys.exit(f"queue root not found: {ready} (run on your host, under sudo)")
    entries = []
    for name in os.listdir(ready):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(ready, name)) as fh:
                m = json.load(fh)
        except (OSError, ValueError):
            continue
        if m.get("status") != "READY":
            continue
        entries.append((int(m.get("priority", 2)), str(m.get("created_at") or ""),
                        norm(m.get("target_artist")), m.get("target_album") or ""))
    entries.sort()
    print(f"READY backlog: {len(entries)} manifests")
    print(f"by priority: {dict(sorted(Counter(e[0] for e in entries).items()))}")
    hits = [(i, e) for i, e in enumerate(entries) if e[2] == want]
    print(f"'{sys.argv[1]}': {len(hits)} manifest(s) in READY")
    for i, e in hits:
        print(f"  rank {i + 1}/{len(entries)}  prio={e[0]}  enqueued={e[1]}  {e[3]}")
    if hits:
        print(f"earliest at rank {hits[0][0] + 1} → {hits[0][0]} manifest(s) ahead of it")


if __name__ == "__main__":
    main()
