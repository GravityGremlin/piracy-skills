#!/usr/bin/env python3
"""Post-enqueue check for slskd lane groups (the downloader fleet).

Usage:
    python3 slskd_group_check.py [--db PATH] [--staging DIR] [--hours N] [--group GID]

Read-only, stdlib only — reads the lane's sqlite DB directly (no lane app
import) and prints per group: job-state counts, how many jobs carry staged
files, whether the group handed off to the organizer (organizer_job_id), and
how many files sit in its staging dir.

Healthy album group: N audio jobs (N == the album's track count), all
completed, one organizer_job_id, staging holds the staged audio.
Broken signals: job count well below the track count (sibling expansion was
truncated), any 'error' job (a group with any error never finalizes), or no
organizer_job_id after everything completed (finalize never ran).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import time
from collections import Counter, defaultdict
from pathlib import Path

DEFAULT_DB = "/storage/fleet/slskd/data/lane.db"
DEFAULT_STAGING = "/storage/fleet/slskd"


def find_jobs_table(con: sqlite3.Connection) -> tuple[str, list[str]]:
    for (name,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'"):
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({name})")]
        if "group_id" in cols and "state" in cols:
            return name, cols
    raise SystemExit("no jobs table with group_id/state columns found")


def is_recent(row: sqlite3.Row, cutoff: float) -> bool:
    value = row["created_at"]
    try:
        return float(value) > cutoff
    except (TypeError, ValueError):
        return True  # unknown format: over-report rather than hide a group


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=DEFAULT_DB)
    ap.add_argument("--staging", default=DEFAULT_STAGING)
    ap.add_argument("--hours", type=float, default=4.0, help="window on created_at")
    ap.add_argument("--group", default=None, help="single group id")
    args = ap.parse_args()

    db = Path(args.db)
    if not db.exists():
        raise SystemExit(f"lane DB not found: {db}")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    table, cols = find_jobs_table(con)

    if args.group:
        rows = list(con.execute(f"SELECT * FROM {table} WHERE group_id = ?", (args.group,)))
    else:
        rows = list(con.execute(f"SELECT * FROM {table}"))
        cutoff = time.time() - args.hours * 3600
        rows = [r for r in rows if is_recent(r, cutoff)]

    groups: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        groups[row["group_id"]].append(row)

    if not groups:
        print("no recent groups found")
        return 0

    for gid, jobs in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        states = Counter(j["state"] for j in jobs)
        staged = 0
        if "files" in cols:
            for j in jobs:
                try:
                    staged += len(json.loads(j["files"] or "[]"))
                except (TypeError, ValueError):
                    pass
        org = None
        if "organizer_job_id" in cols:
            org = next((j["organizer_job_id"] for j in jobs if j["organizer_job_id"]), None)
        user = jobs[0]["username"] if "username" in cols else "?"
        staging_files = 0
        sdir = Path(args.staging) / gid
        if sdir.is_dir():
            staging_files = sum(1 for p in sdir.rglob("*") if p.is_file())
        print(
            f"{gid}  peer={user}  jobs={len(jobs)} {dict(states)}  "
            f"files_on_jobs={staged}  organizer={org or '-'}  staging_files={staging_files}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
