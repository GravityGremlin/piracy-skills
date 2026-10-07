#!/usr/bin/env python3
"""Transcode 'Movies' library census + AV1 floor-guard simulation (READ-ONLY).

Models the AV1 converter plugin's floor guard so you can answer
"why do large H.264 files never convert?" and "what would preset X / floor Y
do to the backlog?" without touching the server.

Guard model (see references/size-guard-math.md):
  estimates @1080p kbps: efficient 1333, balanced 2133, high 4444, archival 5556
  scaled by output pixel ratio vs 1920x1080, clamped 0.35x-3x
  skip when even the TOP tier estimate < floor_percent% of source bitrate
  otherwise escalate up [efficient, balanced, high, archival] to the first
  tier that clears the floor

Usage:
  python3 guard-sim.py                       # live inputs from librarysettingsjsondb
  python3 guard-sim.py --preset balanced --floor 5
  python3 guard-sim.py --min-gb 20 --limit 15
  python3 guard-sim.py --all                 # every video codec, not just h264

Set TDARR_DB environment variable to point to a different database file.

Nothing here writes to the DB, the server, or the library.
"""

import argparse
import collections
import json
import os
import sqlite3

DB = os.environ.get(
    "TDARR_DB", "<data-dir>/server/Tdarr/DB2/SQL/database.db"
)
EST = {"efficient": 1333, "balanced": 2133, "high": 4444, "archival": 5556}
LADDER = ["efficient", "balanced", "high", "archival"]


def connect(db=DB):
    return sqlite3.connect("file:%s?mode=ro" % db, uri=True, timeout=30)


def rows(cur, table):
    return [json.loads(r[0]) for r in cur.execute("select json_data from %s" % table)]


def tier_est(tier, width, height):
    est = EST.get(tier, EST["balanced"])
    if width and height:
        ratio = (width * height) / (1920.0 * 1080.0)
        est = round(est * min(3.0, max(0.35, ratio)))
    return est


def guard(src_kbps, preset, floor_pct, width, height, guard_on=True):
    """Return (decision, tier_used, est_kbps); decision in ok/escalate/skip/no-guard."""
    if not guard_on or src_kbps <= 0 or floor_pct <= 0:
        return ("no-guard", preset, tier_est(preset, width, height))
    floor = floor_pct * src_kbps / 100.0
    est = tier_est(preset, width, height)
    if est >= floor:
        return ("ok", preset, est)
    for tier in LADDER[LADDER.index(preset) + 1:]:
        te = tier_est(tier, width, height)
        if te >= floor:
            return ("escalate", tier, te)
    return ("skip", None, tier_est("archival", width, height))


def gb_for(est_kbps, duration_s):
    return est_kbps * 0.45 * (duration_s / 3600.0) / 1000.0


def live_inputs(con):
    lib = rows(con.cursor(), "librarysettingsjsondb")
    if not lib:
        raise SystemExit("no librarysettingsjsondb row")
    lib = lib[0]
    out = {
        "library": lib.get("name"),
        "preset": "balanced",
        "floor_percent": 40.0,
        "guard_on": True,
        "lower_bound": None,
        "upper_bound": None,
    }
    for plug in lib.get("pluginIDs", []):
        inputs = plug.get("InputsDB") or {}
        pid = plug.get("id", "")
        if "av1_svt_converter" in pid:
            if inputs.get("quality_preset"):
                out["preset"] = inputs["quality_preset"].rstrip("*")
            if inputs.get("floor_guard"):
                out["guard_on"] = inputs["floor_guard"].startswith("enabled")
            if inputs.get("floor_percent"):
                out["floor_percent"] = float(str(inputs["floor_percent"]).rstrip("*"))
        if "a9he_New_file_size_check" in pid:
            if inputs.get("lowerBound") is not None:
                out["lower_bound"] = float(str(inputs["lowerBound"]).rstrip("*"))
            if inputs.get("upperBound") is not None:
                out["upper_bound"] = float(str(inputs["upperBound"]).rstrip("*"))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", choices=LADDER)
    ap.add_argument("--floor", type=float, help="floor_percent override")
    ap.add_argument("--min-gb", type=float, default=0.0)
    ap.add_argument("--codec", default="h264")
    ap.add_argument("--all", action="store_true", help="all codecs, not just --codec")
    ap.add_argument("--limit", type=int, default=12)
    args = ap.parse_args()

    con = connect()
    cur = con.cursor()
    live = live_inputs(con)
    preset = args.preset or live["preset"]
    floor = args.floor if args.floor is not None else live["floor_percent"]

    print("DB: %s" % DB)
    print("library: %s | live preset=%s floor_guard=%s floor_percent=%s | gate lower/upper=%s/%s"
          % (live["library"], live["preset"], live["guard_on"],
             live["floor_percent"], live["lower_bound"], live["upper_bound"]))
    print("simulating: preset=%s floor_percent=%s\n" % (preset, floor))

    files = []
    census = collections.Counter()
    success_but_unconverted = 0
    for j in rows(cur, "filejsondb"):
        codec = j.get("video_codec_name") or "?"
        verdict = str(j.get("TranscodeDecisionMaker"))
        census[(codec, verdict)] += 1
        if codec == "h264" and verdict == "Transcode success":
            success_but_unconverted += 1
        if not args.all and codec != args.codec:
            continue
        mb = float(j.get("file_size") or 0)
        if mb / 1024.0 < args.min_gb:
            continue
        streams = (j.get("ffProbeData") or {}).get("streams") or []
        video = next((s for s in streams if s.get("codec_type") == "video"), {})
        files.append({
            "gb": mb / 1024.0,
            "src_kbps": (j.get("bit_rate") or 0) / 1000.0,
            "dur_h": float(j.get("duration") or 0) / 3600.0,
            "w": video.get("width"),
            "h": video.get("height"),
            "verdict": verdict,
            "name": (j.get("file") or "").split("/")[-2][:38],
        })

    print("census (codec, verdict):")
    for (codec, verdict), n in census.most_common():
        print("  %-12s %-20s %d" % (codec, verdict, n))
    print("  note: %d h264 files carry 'Transcode success' - ffprobe them before"
          " assuming the codec changed\n" % success_but_unconverted)

    files.sort(key=lambda f: -f["gb"])
    print("top %d of %d simulated files (>=%s GB, codec=%s):"
          % (min(args.limit, len(files)), len(files), args.min_gb,
             "all" if args.all else args.codec))
    print("  %6s %8s %6s | %-9s %-9s %6s | gate%%" % ("GB", "srcMbps", "dur_h", "decision", "tier", "out_GB"))
    decisions = collections.Counter()
    for f in files:
        decision, tier, est = guard(
            f["src_kbps"], preset, floor, f["w"], f["h"], live["guard_on"])
        decisions[decision] += 1
        out_gb = gb_for(est, f["dur_h"] * 3600.0)
        gate_pct = (out_gb * 100.0 / f["gb"]) if f["gb"] else 0.0
        if f["gb"] >= args.min_gb and (args.all or True):
            pass
    shown = files[: args.limit]
    for f in shown:
        decision, tier, est = guard(
            f["src_kbps"], preset, floor, f["w"], f["h"], live["guard_on"])
        out_gb = gb_for(est, f["dur_h"] * 3600.0)
        gate_pct = (out_gb * 100.0 / f["gb"]) if f["gb"] else 0.0
        print("  %6.1f %8.1f %6.2f | %-9s %-9s %6.2f | %5.1f%%  %s"
              % (f["gb"], f["src_kbps"] / 1000.0, f["dur_h"], decision,
                 tier or "-", out_gb, gate_pct, f["name"]))

    print("\ndecision counts over %d files: %s" % (len(files), dict(decisions)))
    if live["lower_bound"]:
        low = live["lower_bound"]
        if floor > low:
            print("WARNING: floor_percent(%.0f) > gate lowerBound(%.0f) - the guard "
                  "will skip files the gate would have accepted." % (floor, low))
        risky = [f for f in files if f["gb"] and
                 gb_for(guard(f["src_kbps"], preset, floor, f["w"], f["h"],
                              live["guard_on"])[2],
                        f["dur_h"] * 3600.0) * 100.0 / f["gb"] < low]
        if risky:
            print("WARNING: %d simulated outputs would land below the gate "
                  "lowerBound (%.0f%%) and get vetoed+reverted; e.g. %s"
                  % (len(risky), low, ", ".join(r["name"] for r in risky[:3])))
    print("\nreminder: estimates are plugin heuristics; a config change does not "
          "re-queue files that already carry a verdict.")


if __name__ == "__main__":
    main()
