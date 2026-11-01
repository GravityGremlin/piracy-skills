#!/usr/bin/env python3
"""Dispatch a curated shortlist of albums through the downloader fleet.

Thin driver over the sanctioned pieces — no bespoke download path:
  * aggregator meta-search (IPVPLACEHOLDER:19297/search/json) to resolve the album,
  * the repo-yard-grab skill's rygrab.py to enqueue on the Tidal lane,
  * the organizer imports it as usual.

Input: one or more shortlist JSON files (genre/artists/albums). Skips anything
beets already owns so a re-run never re-buys the library.

  grab_shortlist.py <file>.json [--dry-run] [--limit N]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.parse
import urllib.request

AGGREGATOR = os.environ.get('FLEET_AGGREGATOR_URL', 'http://<aggregator-host>:19297')
RYGRAB = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'rygrab.py') 
RYGRAB_PY = sys.executable
BEETS_DB = os.environ.get('BEETS_DB', os.path.expanduser('~/beets/library.db'))
OUT = os.environ.get('RYGRAB_OUT', 'shortlist-run.json')
THROTTLE_S = 5.0
EDITION_RX = re.compile(r'\b(deluxe|legacy|anniversary|remaster|remastered|expanded|'
                        r'super|special|bonus|collector|edition|reissue|mono|stereo)\b',
                        re.I)


def norm(s: str) -> str:
    s = (s or '').casefold()
    s = re.sub(r'\s*[\(\[][^)\]]*[\)\]]', ' ', s)
    return re.sub(r'[^a-z0-9]+', ' ', s).strip()


def base_title(s: str) -> str:
    return norm(re.sub(r'\s*[\(\[][^)\]]*[\)\]]', '', s or ''))


def library_index() -> dict[str, set[str]]:
    db = sqlite3.connect(f'file:{BEETS_DB}?mode=ro', uri=True)
    try:
        rows = db.execute('select albumartist, album from albums').fetchall()
    finally:
        db.close()
    idx: dict[str, set[str]] = {}
    for artist, album in rows:
        idx.setdefault(norm(artist), set()).add(base_title(album))
    return idx


def search(q: str) -> list[dict]:
    url = f'{AGGREGATOR}/search/json?' + urllib.parse.urlencode({'q': q, 'type': 'album'})
    try:
        with urllib.request.urlopen(url, timeout=90) as resp:
            data = json.load(resp)
    except Exception:  # noqa: BLE001 - a lane timeout is a miss, not a crash
        return []
    return data.get('results') or []


def pick(rows: list[dict], artist: str, album: str) -> dict | None:
    want_artist, want_album = norm(artist), base_title(album)
    scored = []
    for r in rows:
        r_artist, r_title = norm(r.get('artist') or ''), r.get('title') or ''
        if r_artist != want_artist:
            continue
        if base_title(r_title) != want_album:
            continue
        edition_penalty = len(EDITION_RX.findall(r_title))
        tracks = int(r.get('track_count') or r.get('tracks') or 0) or 999
        scored.append((edition_penalty, tracks, len(r_title), r))
    if not scored:
        return None
    scored.sort(key=lambda t: (t[0], t[1], t[2]))
    return scored[0][3]


def dispatch(url: str) -> tuple[bool, str]:
    cmd = [RYGRAB_PY, RYGRAB, '--url', url, '--platform', 'tidal']
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    ok = res.returncode == 0
    return ok, (res.stdout or res.stderr or '').strip()[-400:]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('shortlists', nargs='+')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--limit', type=int, default=0)
    args = ap.parse_args()

    paths = [p for pattern in args.shortlists for p in sorted(glob.glob(pattern))]
    if not paths:
        print('no shortlist files matched', file=sys.stderr)
        return 1

    have = library_index()
    run: list[dict] = []
    count = 0
    for path in paths:
        data = json.load(open(path))
        genre = data.get('genre', os.path.basename(path))
        for entry in data.get('artists', []):
            artist = (entry.get('name') or '').strip()
            if not artist:
                continue
            owned = have.get(norm(artist), set())
            for rec in entry.get('albums', []):
                album = (rec.get('title') or '').strip()
                if not album:
                    continue
                if args.limit and count >= args.limit:
                    break
                row = {'genre': genre, 'artist': artist, 'album': album,
                       'year': rec.get('year'), 'tier': entry.get('tier')}
                if base_title(album) in owned:
                    row['status'] = 'held'
                    run.append(row)
                    continue
                rows = search(f'{artist} {album}')
                hit = pick(rows, artist, album)
                if not hit:
                    row['status'] = 'not_found'
                    row['candidates'] = len(rows)
                    run.append(row)
                    print(f"MISS {genre:16s} {artist[:26]:26s} - {album[:36]}", flush=True)
                    continue
                row['resolved_title'] = hit.get('title')
                row['url'] = hit.get('url')
                row['service'] = hit.get('service') or hit.get('platform')
                if args.dry_run:
                    row['status'] = 'would_dispatch'
                    run.append(row)
                    print(f"DRY  {genre:16s} {artist[:26]:26s} - {hit.get('title')}", flush=True)
                    continue
                ok, out = dispatch(hit['url'])
                row['status'] = 'dispatched' if ok else 'dispatch_failed'
                row['detail'] = out
                run.append(row)
                count += 1
                print(f"{'OK  ' if ok else 'FAIL'} {genre:16s} {artist[:26]:26s} - "
                      f"{(hit.get('title') or '')[:34]}", flush=True)
                time.sleep(THROTTLE_S)
            if args.limit and count >= args.limit:
                break

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(run, open(OUT, 'w'), indent=1)
    tally: dict[str, int] = {}
    for r in run:
        tally[r['status']] = tally.get(r['status'], 0) + 1
    print('run:', tally, '->', OUT)
    return 0


if __name__ == '__main__':
    sys.exit(main())
