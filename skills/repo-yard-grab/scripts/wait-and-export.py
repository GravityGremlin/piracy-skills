#!/usr/bin/env python3
"""Wait for a set of lane job groups to finish, then (re)run the export hardlinker.

Uses /download/jobs/summary — the per-group AGGREGATE endpoint. Do NOT use
/download/jobs/data for this: it returns only the most recent 500 rows (a
rotating window), so a deep queue hides the jobs you care about and the
watcher falsely reports "drained".

Bounded: gives up after --max-minutes and exports whatever landed (the export
is idempotent, so a partial run is still useful).

Edit GROUPS with the group_ids you dispatched (the /discography and /dispatch
responses both return `group_id` / `job_ids`).

Usage: python3 wait-and-export.py [--max-minutes N]
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import time
import urllib.request

ENV = "path-to-credentials"
LANE = "http://IPVPLACEHOLDER:19493"
EXPORT_SCRIPT = "path-to-credentials"
LOG = "path-to-credentials"

# group_id -> artist label, filled in per dispatch.
GROUPS: dict[str, str] = {}


def log(msg: str) -> None:
    line = f"{time.strftime('%H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(LOG, "a") as fh:
        fh.write(line + "\n")


def lane_token() -> str:
    """The lane bearer is the per-service TOOL_HEADLESS_TOKENS value, NOT the
    plain HEADLESS_TOKEN — that one 401s."""
    env = open(ENV).read()
    m = re.search(r"^TOOL_HEADLESS_TOKENS=(.*)$", env, re.M)
    if not m:
        raise SystemExit("TOOL_HEADLESS_TOKENS not found in " + ENV)
    return json.loads(m.group(1).strip().strip('"').strip("'"))["tidal"]


def group_status(tok: str) -> tuple[int, int, dict]:
    """Return (pending, completed, per_artist) from the per-group SUMMARY endpoint."""
    req = urllib.request.Request(
        f"{LANE}/download/jobs/summary",
        headers={"Authorization": f"Bearer {tok}"},
    )
    rows = json.load(urllib.request.urlopen(req, timeout=30))
    pending = completed = 0
    per: dict[str, dict] = {}
    for r in rows:
        gid = r.get("group_id")
        if gid not in GROUPS:
            continue
        q = (r.get("queued") or 0) + (r.get("running") or 0)
        c = r.get("completed") or 0
        pending += q
        completed += c
        a = per.setdefault(GROUPS[gid], {"done": 0, "queued": 0, "error": 0})
        a["done"] += c
        a["queued"] += q
        a["error"] += r.get("error") or 0
    return pending, completed, per


def main() -> int:
    max_min = 300
    if "--max-minutes" in sys.argv:
        max_min = int(sys.argv[sys.argv.index("--max-minutes") + 1])
    deadline = time.time() + max_min * 60
    tok = lane_token()
    log(f"watcher start (summary endpoint), budget {max_min}m")

    last = ""
    while time.time() < deadline:
        try:
            pending, completed, per = group_status(tok)
        except Exception as e:
            log(f"summary fetch error: {e}")
            time.sleep(120)
            continue
        snap = "pending=%d done=%d | %s" % (
            pending, completed,
            " ".join(f"{k}:{v['done']}/{v['done'] + v['queued']}"
                     for k, v in sorted(per.items())))
        if snap != last:
            log(snap)
            last = snap
        if pending == 0:
            log("all groups finished")
            break
        time.sleep(120)

    log("running export hardlinker")
    r = subprocess.run([sys.executable, EXPORT_SCRIPT], capture_output=True, text=True)
    for line in (r.stdout or "").splitlines():
        log("  " + line)
    if r.returncode != 0:
        log(f"export FAILED rc={r.returncode}: {r.stderr[:400]}")
        return r.returncode
    log("export complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
