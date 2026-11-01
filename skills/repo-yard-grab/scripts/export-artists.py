#!/usr/bin/env python3
"""Hardlink an artist's library albums into /your-media-path/exports for easy grabbing.

Layout produced:
    /your-media-path/exports/<Artist>/<Album>/<file>

Every audio file (and cover art) is a HARDLINK to the library file — same
inode, zero extra space, and deleting the export never touches the library.
Idempotent: re-run any time (e.g. after downloads finish); existing links are
left alone, only new files are linked.

Usage:
    python3 export-artists.py                 # all artists in ARTISTS
    python3 export-artists.py Radiohead ...   # named subset
    python3 export-artists.py --dry-run       # show what would link
"""
from __future__ import annotations

import os
import re
import sys

LIB = "/storage/library/music-library"
EXPORTS = "/your-media-path/exports"  # == /storage/exports (same btrfs, dev 60)
AUDIO = (".opus", ".mp3", ".flac", ".m4a", ".ogg", ".wav")
ART = ("cover.jpg", "cover.png", "folder.jpg", "front.jpg")

# Edit this list per request; the script also takes artist names as args.
ARTISTS: list[str] = []


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def resolve_lib_artist(want: str) -> str | None:
    """Case/punct-insensitive lookup of the library dir for an artist."""
    key = norm(want)
    for e in os.scandir(LIB):
        if e.is_dir() and norm(e.name) == key:
            return e.path
    return None


def link_file(src: str, dst: str, dry: bool) -> str:
    """Hardlink src->dst. Returns 'linked' | 'exists' | 'skip'."""
    if os.path.lexists(dst):
        try:
            if os.stat(src).st_ino == os.stat(dst).st_ino:
                return "exists"
        except OSError:
            pass
        return "skip"  # a different file is already there — never overwrite
    if dry:
        return "linked"
    os.link(src, dst)  # atomic; raises on cross-device (must not happen)
    return "linked"


def export_artist(artist: str, dry: bool) -> dict:
    src_root = resolve_lib_artist(artist)
    out = {"artist": artist, "lib": src_root, "albums": 0, "linked": 0,
           "exists": 0, "skip": 0, "empty_albums": []}
    if not src_root:
        out["error"] = "not in library"
        return out

    dst_root = os.path.join(EXPORTS, artist)
    if not dry:
        os.makedirs(dst_root, exist_ok=True)

    for e in sorted(os.scandir(src_root), key=lambda x: x.name):
        if not e.is_dir():
            continue
        out["albums"] += 1
        files = [f for f in os.listdir(e.path)
                 if f.lower().endswith(AUDIO) or f.lower() in ART]
        if not files:
            out["empty_albums"].append(e.name)
            continue
        dst_album = os.path.join(dst_root, e.name)
        if not dry:
            os.makedirs(dst_album, exist_ok=True)
        for f in files:
            r = link_file(os.path.join(e.path, f), os.path.join(dst_album, f), dry)
            out[r] += 1
    return out


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    targets = args or ARTISTS
    if not targets:
        print("no artists given: pass names as args or edit ARTISTS")
        return 1

    if not os.path.isdir(EXPORTS):
        print(f"FAIL: {EXPORTS} does not exist")
        return 1

    totals = {"linked": 0, "exists": 0, "skip": 0}
    print(f"{'artist':<18} {'lib?':<5} {'albums':>6} {'linked':>7} {'exists':>7} {'skip':>5}")
    print("-" * 56)
    for a in targets:
        r = export_artist(a, dry)
        if r.get("error"):
            print(f"{a:<18} NO    — {r['error']}")
            continue
        print(f"{a:<18} yes   {r['albums']:>6} {r['linked']:>7} {r['exists']:>7} {r['skip']:>5}")
        if r["empty_albums"]:
            print(f"    (empty, no audio yet: {', '.join(r['empty_albums'][:6])}"
                  f"{' …' if len(r['empty_albums']) > 6 else ''})")
        for k in totals:
            totals[k] += r[k]
    print("-" * 56)
    print(f"{'TOTAL':<18}       {'':>6} {totals['linked']:>7} {totals['exists']:>7} {totals['skip']:>5}"
          + ("   [DRY RUN]" if dry else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
