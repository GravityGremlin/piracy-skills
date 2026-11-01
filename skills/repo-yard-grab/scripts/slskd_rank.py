#!/usr/bin/env python3
"""slskd_rank.py - refined candidate ranking across saved slskd search responses.

Bakes in the 2026-09-30 "Kathy's Song XXV" hunt lessons:

1. Query-shape decides the responder set. Union MULTIPLE response dumps from
   the shape ladder (artist+title, artist+anniv-token, title+anniv, full title)
   before ranking. Never rank - or conclude absence - from one sweep.
2. The `extension` field is often EMPTY (peer/client dependent). Derive the
   extension from the FILENAME instead, splitting on '@' (e.g. 'mp3@synoeastream').
3. Responses contain only MATCHED files; aux siblings (jpg/m3u/nfo/sfv/log/cue/
   txt/lrc/xml) must not count as tracks and must never be enqueued (one junk
   job wedges the whole lane group).
4. Rank per (user, directory): lossless + complete first, then peer quality
   (free slot, queue, speed), then size. Note the MusicBrainz gate: prefer the
   edition MB actually has (digital) over a scene vinyl rip MB lacks.

Usage:
  python3 slskd_rank.py [--glob 'resp_*.json'] [--extra user_resp.json ...]
      [--lane lane_search.json] [--target xxv] [--expect 4]
      [--out slskd_rank_report.txt] [--top 25]
"""
from __future__ import annotations

import argparse
import glob as _glob
import json
import os
import posixpath
import re
from collections import Counter, defaultdict

AUDIO = {"flac", "wav", "aiff", "aif", "ape", "alac", "m4a", "mp3", "opus",
         "ogg", "oga", "aac", "wma", "mpc", "wv", "dsf", "dff"}
LOSSLESS = {"flac", "wav", "aiff", "aif", "ape", "alac", "wv", "dsf", "dff"}
AUX = {"jpg", "jpeg", "png", "gif", "m3u", "m3u8", "nfo", "sfv", "log", "cue",
       "txt", "lrc", "xml", "md5", "md5sum", "db", "ini", "pdf", "url", "sfv2"}
LEGACY_TOKENS = ("welcome to earth", "singles collection", "sdgxxv", "apbl",
                 "harmonizer", "unicorn", " 7 ", "soli deo gloria")


def ext_of(name: str) -> str:
    """Extension from FILENAME only (slskd's `extension` field is often empty).

    P2P paths are Windows-style (backslashes) and can start with '@@<share>'
    or end with '@<client>' markers (e.g. 'mp3@synoeastream'); strip markers
    from the EXTENSION, never from the whole path.
    """
    b = posixpath.basename(name.replace("\\", "/"))
    if "." not in b:
        return ""
    e = b.rsplit(".", 1)[1].lower()
    if "@" in e:
        e = e.split("@", 1)[0]
    return e if re.fullmatch(r"[a-z0-9]{1,8}", e) else ""


def dir_of(name: str) -> str:
    return posixpath.dirname(name.replace("\\", "/"))


def norm(s: str) -> str:
    return re.sub(r"[\s._\-()\[\]\\/]+", " ", s.lower()).strip()


def load_responses(patterns, extra):
    paths = []
    for p in patterns:
        paths.extend(sorted(_glob.glob(p)))
    paths.extend(x for x in extra or [] if os.path.exists(x))
    rows, src_counts = [], Counter()
    for fp in paths:
        try:
            data = json.load(open(fp))
        except Exception:
            continue
        if not isinstance(data, list):
            continue
        n = 0
        for u in data:
            un = u.get("username") or "?"
            meta = {k: u.get(k) for k in
                    ("hasFreeUploadSlot", "queueLength", "uploadSpeed")}
            for f in u.get("files") or []:
                fn = f.get("filename") or ""
                rows.append({"src": os.path.basename(fp), "user": un, "fn": fn,
                             "dir": dir_of(fn),
                             "base": posixpath.basename(fn.replace("\\", "/")),
                             "ext": ext_of(fn), "size": f.get("size") or 0,
                             "len": f.get("length"), "sr": f.get("sampleRate"),
                             "bd": f.get("bitDepth"), "br": f.get("bitRate"),
                             **meta})
                n += 1
        src_counts[os.path.basename(fp)] = n
    return rows, src_counts


def load_lane(path):
    rows = []
    if not path or not os.path.exists(path):
        return rows
    try:
        d = json.load(open(path))
    except Exception:
        return rows
    r = d.get("results") if isinstance(d, dict) else d
    for x in r or []:
        url = x.get("url") or ""
        fn = ""
        if url.startswith("slskd://"):
            parts = url.split("/", 3)
            if len(parts) == 4:
                fn = parts[3].replace("/", "\\")
        rows.append({"user": x.get("username"), "fn": fn,
                     "lossless": x.get("dir_lossless"),
                     "files": x.get("dir_files"), "album": x.get("album")})
    return rows

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--glob", default=None, action="append",
                    help="glob(s) of raw /searches/<id>/responses dumps (repeatable; default resp_*.json)")
    ap.add_argument("--extra", nargs="*", default=[],
                    help="extra response dump files (e.g. user_resp.json)")
    ap.add_argument("--lane", default="", help="lane /search/json dump to merge")
    ap.add_argument("--target", default="", help="require token in normalized paths")
    ap.add_argument("--expect", type=int, default=0, help="expected track count")
    ap.add_argument("--out", default="slskd_rank_report.txt")
    ap.add_argument("--top", type=int, default=25)
    args = ap.parse_args()

    patterns = args.glob or ["resp_*.json"]
    rows, src = load_responses(patterns, args.extra)
    # dedupe across sources: same (user, filename, size)
    seen, ded = set(), []
    dups = 0
    for r in rows:
        k = (r["user"], r["fn"], r["size"])
        if k in seen:
            dups += 1
            continue
        seen.add(k)
        ded.append(r)

    groups = defaultdict(lambda: {"files": [], "lane": []})
    for r in ded:
        groups[(r["user"], r["dir"])]["files"].append(r)

    lane = load_lane(args.lane)
    lane_only = 0
    for lr in lane:
        dr = dir_of(lr["fn"]) if lr["fn"] else ""
        key = (lr["user"], dr)
        if key in groups:
            groups[key]["lane"].append(lr)
        else:
            groups[key]["lane"].append(lr)
            lane_only += 1

    cands, skipped_target = [], 0
    for (un, dr), e in groups.items():
        fs = e["files"]
        t = norm(dr + " " + " ".join(f["base"] for f in fs))
        if args.target and args.target.lower() not in t:
            skipped_target += 1
            continue
        exts = Counter(f["ext"] for f in fs)
        audio = [f for f in fs if f["ext"] in AUDIO]
        lossless = [f for f in audio if f["ext"] in LOSSLESS]
        aux = [f for f in fs if f["ext"] in AUX]
        unknown = [f for f in fs if f["ext"] == "" and (f["size"] or 0) > 2_000_000]
        peer = fs[0] if fs else {}
        slot = peer.get("hasFreeUploadSlot")
        queue = peer.get("queueLength")
        speed = peer.get("uploadSpeed")
        sr = sorted({f["sr"] for f in audio if f["sr"]})
        bd = sorted({f["bd"] for f in audio if f["bd"]})
        lens = [f["len"] for f in audio if f["len"]]
        legacy = any(k in t for k in LEGACY_TOKENS)
        edition = "?"
        if "vinyl" in t:
            edition = "VINYL-FLAC" if lossless else ("VINYL-MP3" if audio else "VINYL-?")
        elif "web" in t:
            edition = "WEB-FLAC" if lossless else "WEB-lossy"
        elif lossless:
            edition = "FLAC"
        elif audio:
            edition = "MP3"
        complete = (len(audio) >= args.expect) if args.expect else None
        lane_ll = None
        if e["lane"]:
            ll = [x["lossless"] for x in e["lane"] if x["lossless"] is not None]
            if ll:
                lane_ll = max(ll)
        cands.append({
            "user": un, "dir": dr, "edition": edition, "legacy": legacy,
            "audio": len(audio), "lossless": len(lossless), "aux": len(aux),
            "unknown": len(unknown), "ext": dict(exts), "sr": sr, "bd": bd,
            "lens": lens, "size": sum(f["size"] or 0 for f in fs),
            "slot": slot, "queue": queue, "speed": speed,
            "complete": complete, "lane_lossless": lane_ll, "files": fs,
            "lane": e["lane"],
        })

    cands.sort(key=lambda c: (
        1 if c["lossless"] else 0,
        c["lossless"],
        1 if c["complete"] else 0,
        c["audio"],
        1 if c["slot"] else 0,
        -(c["queue"] if isinstance(c["queue"], int) else 99999),
        c["speed"] or 0,
        c["size"],
    ), reverse=True)

    with open(args.out, "w") as out:
        out.write("slskd_rank report\n")
        out.write("sources: " + json.dumps(src) + "\n")
        out.write(f"rows: {len(rows)} raw, {dups} dupes dropped, {len(ded)} kept | "
                  f"groups: {len(groups)} | candidates: {len(cands)} "
                  f"(target filter {args.target!r}, skipped {skipped_target})\n\n")
        for c in cands[: args.top]:
            out.write(f"== {c['user']} | {c['edition']}"
                      f"{' LEGACY' if c['legacy'] else ''}"
                      f"{' COMPLETE' if c['complete'] else (' INCOMPLETE' if c['complete'] is False else '')}"
                      f" | lossless {c['lossless']}/{c['audio']} audio (+{c['aux']} aux, {c['unknown']} unk)"
                      f" | sr={c['sr']} bd={c['bd']} lens={c['lens']}"
                      f" | slot={c['slot']} q={c['queue']} spd={c['speed']}"
                      f" | {c['size']/1e6:.1f} MB"
                      f"{' | lane_ll=' + str(c['lane_lossless']) if c['lane_lossless'] is not None else ''}\n")
            out.write(f"   dir: {c['dir']}\n")
            for f in c["files"][:8]:
                out.write(f"     [{f['ext'] or '?'}] {f['size']}B {f['base'][:110]}\n")
            for lr in c["lane"][:4]:
                out.write(f"     lane: lossless={lr['lossless']}/{lr['files']} album={lr['album']}\n")
            out.write("\n")
        safe = next((c for c in cands if c["lossless"] and not c["legacy"]
                     and "vinyl" not in c["edition"].lower()), None)
        vin = next((c for c in cands if c["lossless"] and not c["legacy"]
                    and "vinyl" in c["edition"].lower()), None)
        if safe:
            f0 = next((f for f in safe["files"] if f["ext"] in LOSSLESS), None)
            out.write("SAFE PICK (MB-matchable edition; survives the import gate): %s | %s | %s (%d lossless%s)\n" % (
                safe["user"], safe["edition"], safe["dir"], safe["lossless"],
                ", COMPLETE" if safe["complete"] else ""))
            if f0:
                out.write("  enqueue sample url: slskd://%s/%s\n" % (safe["user"], f0["fn"]))
        if vin:
            f0 = next((f for f in vin["files"] if f["ext"] in LOSSLESS), None)
            out.write("ARCHIVAL ALTERNATE (vinyl rip; check MB first - can quarantine): %s | %s | %s (%d lossless%s)\n" % (
                vin["user"], vin["edition"], vin["dir"], vin["lossless"],
                ", COMPLETE" if vin["complete"] else ""))
            if f0:
                out.write("  enqueue sample url: slskd://%s/%s\n" % (vin["user"], f0["fn"]))
    print(f"wrote {args.out}: {len(cands)} candidates "
          f"(rows {len(rows)} raw -> {len(ded)} kept)")
    for c in cands[: min(args.top, 12)]:
        print(f"  {c['user']:>16} | {c['edition']:>10} | ll {c['lossless']}/{c['audio']} | "
              f"slot={c['slot']} q={c['queue']} | {c['dir'][:90]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
