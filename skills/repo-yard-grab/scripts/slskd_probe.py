#!/usr/bin/env python3
"""slskd_probe.py - fire/poll/dump slskd raw searches for a release hunt.

Pairs with slskd_rank.py: this script produces the raw response dumps
(resp_<uuid>.json), the ranker consumes every dump in the directory. Read the
query-shape ladder rules in references/slskd-search-probing.md before picking
shapes - the long full-phrase form is the one most likely to return 0.

Usage:
  python3 slskd_probe.py fire   "<query>"
  python3 slskd_probe.py poll   <uuid> [max_wait_s]
  python3 slskd_probe.py dump   <uuid>          # fetch + save resp_<uuid>.json
  python3 slskd_probe.py ladder "shape 1" "shape 2" ...   # spaced fires

Env: BASE (default http://IPVPLACEHOLDER:5030), SLSKD_KEY
(docker exec slskd-headless printenv SLSKD_API_KEY).
Never DELETEs a search: slskd then throws DbUpdateConcurrencyException and
subsequent searches report 0 responses (indistinguishable from absence).
"""
import json
import os
import sys
import time
import urllib.request
import uuid

BASE = os.environ.get("BASE", "http://IPVPLACEHOLDER:5030")
KEY = os.environ["SLSKD_KEY"]


def api(path, method="GET", body=None, timeout=25):
    req = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"X-API-Key": KEY, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode()
    return json.loads(raw) if raw.strip() else {}


def fire(text):
    sid = str(uuid.uuid4())
    api("/api/v0/searches", "POST", {"searchText": text, "id": sid})
    json.dump({"id": sid, "text": text, "fired": time.time()},
              open(f"search_{sid}.fired.json", "w"))
    print("FIRED", sid, "|", text, flush=True)
    return sid


def wait_terminal(sid, max_s=90, step=5):
    t0 = time.time()
    while time.time() - t0 < max_s:
        st = api(f"/api/v0/searches/{sid}")
        if str(st.get("state", "")).startswith(("Completed", "Cancelled")):
            return st
        time.sleep(step)
    return api(f"/api/v0/searches/{sid}")


def dump(sid):
    st = wait_terminal(sid)
    resp = api(f"/api/v0/searches/{sid}/responses", timeout=30)
    json.dump(resp, open(f"resp_{sid}.json", "w"))
    json.dump(st, open(f"state_{sid}.json", "w"))
    users = len(resp)
    files = sum(len(u.get("files", [])) for u in resp)
    print(f"DUMP {sid[:8]} state={st.get('state')} users={users} files={files} "
          f"-> resp_{sid}.json", flush=True)
    return resp


def ladder(shapes):
    """Fire shapes ~45s apart (slskd drops back-to-back searches)."""
    ids = []
    for i, s in enumerate(shapes):
        if i:
            time.sleep(45)
        ids.append(fire(s))
    for sid in ids:
        time.sleep(20)
        dump(sid)
    print("done - now run: slskd_rank.py --glob 'resp_*.json' --target <token>",
          flush=True)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit(1)
    cmd = sys.argv[1]
    if cmd == "fire":
        fire(sys.argv[2])
    elif cmd == "poll":
        sid = sys.argv[2]
        mx = int(sys.argv[3]) if len(sys.argv) > 3 else 90
        st = wait_terminal(sid, mx)
        print({k: st.get(k) for k in ("state", "fileCount", "responseCount")})
        resp = api(f"/api/v0/searches/{sid}/responses", timeout=30)
        print("users:", len(resp), "files:", sum(len(u.get("files", [])) for u in resp))
    elif cmd == "dump":
        dump(sys.argv[2])
    elif cmd == "ladder":
        ladder(sys.argv[2:])
    else:
        print(__doc__)
