#!/usr/bin/env python3
"""Plan artist-dir merges in music-library with collision guards.

Emits a plan; does NOT move anything. Feed the plan to a mover that
`shutil.move`s each src album into the keeper dir, rmdirs emptied sources,
and writes the reverse moves as a rollback script.

Guards enforced here (the parts that cost time when skipped):
  * normalized album-name collision -> refuse the pair (triage, not a dead
    end: most collisions are the same recording with a year/edition suffix)
  * target album dir already exists -> refuse
  * direction chosen by SUBSTANCE (albums, then files), not by which name
    looks canonical

Always review the printed pairs for same-act before moving: similar names can
be different bands (Subhumans vs The Subhumans; Trex vs T. Rex).
"""
import json
import os
import re
import sys

LIB = "/storage/library/music-library"
AUDIO = (".opus", ".mp3", ".flac", ".m4a", ".ogg")


def albums(d):
    p = os.path.join(LIB, d)
    if not os.path.isdir(p):
        return None
    out = {}
    for e in os.listdir(p):
        ep = os.path.join(p, e)
        if not os.path.isdir(ep):
            continue
        n = 0
        for dp, _, fns in os.walk(ep):
            n += sum(1 for f in fns if f.lower().endswith(AUDIO))
        out[e] = n
    return out


def norm_album(s):
    """Collision key: strip year, brackets, and edition words."""
    s = s.casefold()
    s = re.sub(r"\(\d{4}\)$", "", s).strip()
    s = re.sub(r"\[[^\]]*\]", "", s)
    s = re.sub(
        r"\b(remaster(ed)?|deluxe|expanded|edition|version|reissue|"
        r"bonus|anniversary|special)\b", "", s)
    s = re.sub(r"\b(cd|disc|disk)\s*\d+\b", "", s)
    return re.sub(r"[^a-z0-9]+", "", s)


def main(pairs_path):
    pairs = json.load(open(pairs_path))  # [["name A", "name B"], ...]
    plan = []
    for a, b in pairs:
        ia, ib = albums(a), albums(b)
        if ia is None or ib is None:
            print(f"SKIP {a!r}/{b!r}: missing side")
            continue
        fa = sum(ia.values())
        fb = sum(ib.values())
        keep, src = (a, b) if (len(ia), fa) >= (len(ib), fb) else (b, a)
        ka, sa = albums(keep), albums(src)
        kn = {norm_album(x): x for x in ka}
        sn = {norm_album(x): x for x in sa}
        coll = sorted(set(kn) & set(sn))
        move = sorted(set(sa) - {sn[c] for c in coll})
        print(f"{keep:<24} <- {src:<24} move {len(move):>3}  collide {len(coll):>2}")
        for c in coll:
            print(f"     COLLIDE {kn[c]!r} ({ka[kn[c]]} trk)  vs  {sn[c]!r} ({sa[sn[c]]} trk)")
        plan.append({
            "keep": keep, "src": src,
            "keep_albums": ka, "src_albums": sa,
            "move": move,
            "collisions": [(kn[c], sn[c], ka[kn[c]], sa[sn[c]]) for c in coll],
        })
    out = os.path.join(os.path.dirname(pairs_path) or ".", "merge-plan.json")
    json.dump(plan, open(out, "w"), indent=1)
    print(f"\nwrote {out}")
    print("clean pairs (move only):", sum(1 for p in plan if not p["collisions"]))
    print("with collisions:       ", sum(1 for p in plan if p["collisions"]))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: artist-merge-plan.py <pairs.json>")
    main(sys.argv[1])
