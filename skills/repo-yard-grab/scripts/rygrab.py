#!/usr/bin/env python3
"""rygrab — grab music through the downloader fleet's headless lanes on your host.

Resolve an artist (or enqueue an album/track/playlist URL) on the fleet
lanes, dispatch the download, and watch it drain through the beets organizer
into the Navidrome library. Stdlib only.

  rygrab.py --status
  rygrab.py --artist "System of a Down" --wait            # priority: Tidal (Qobuz/Deezer sidelined)
  rygrab.py --artist "<huge discog>" --dispatch spread    # round-robin albums across lanes
  rygrab.py --url "https://tidal.com/browse/album/..." --platform tidal --wait
  rygrab.py --group <group_id> [--retry]                  # watch / requeue errored jobs
  rygrab.py --poll

Auth: HEADLESS_TOKEN (env or path-to-credentials) for
lanes; FLEET_ORGANIZER_TOKEN (path-to-credentials) for the organizer.
"""

import argparse
import json
import os
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

REPO = os.environ.get("FLEET_REPO", "")

def _url(env_name: str, default_port):
    """Lane/aggregator/organizer base URL: env override, else <host>:<port>
    placeholder the reader must point at their own fleet."""
    u = os.environ.get(env_name, "").strip()
    if u:
        return u.rstrip("/")
    return "http://<lane-host>:%s" % default_port

TOOLS = {
    "qobuz": _url("FLEET_QOBUZ_URL", 19492),   # Qobuz
    "tidal": _url("FLEET_TIDAL_URL", 19493),   # Tidal
    "deezer": _url("FLEET_DEEZER_URL", 19494),  # Deezer
}
AGGREGATOR = _url("FLEET_AGGREGATOR_URL", 19297)
ORGANIZER = _url("FLEET_ORGANIZER_URL", 19298)

# User-set lane priority (2026-09-06): all lanes are lossless so quality is
# roughly interchangeable — prefer Qobuz, then Tidal, Deezer last.
# 2026-09-21: Qobuz + Deezer sidelined (donor accounts dead/free) —
# tidal is the only provider lane; slskd stays opt-in.
DEFAULT_PLATFORMS = ["tidal"]

THROTTLE = 5  # seconds between per-lane calls
POLL_INTERVAL = 30


def _env_value(path, key):
    try:
        with open(path) as fh:
            for line in fh:
                if line.strip().startswith(key + "="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def lane_token(lane: str = "tidal"):
    """The lane bearer is the per-service TOOL_HEADLESS_TOKENS entry from the
    fleet .env (a JSON map of lane -> bearer), NOT a plain HEADLESS_TOKEN;
    a plain HEADLESS_TOKEN gets 401 from the lane. Env overrides win."""
    tok = os.environ.get("HEADLESS_TOKEN", "").strip()
    if tok:
        return tok
    raw = _env_value(os.path.join(REPO, ".env"), "TOOL_HEADLESS_TOKENS")
    if raw:
        try:
            tokens = json.loads(raw)
        except ValueError:
            return ""
        if isinstance(tokens, dict):
            return tokens.get(lane, "")
    return ""


def organizer_token():
    tok = os.environ.get("FLEET_ORGANIZER_TOKEN", "").strip()
    if tok:
        return tok
    if not REPO:
        raise SystemExit("Set FLEET_TOKEN (lane bearer) / FLEET_ORGANIZER_TOKEN or FLEET_REPO (fleet checkout) first")
    return _env_value(os.path.join(REPO, ".env"), "FLEET_ORGANIZER_TOKEN")


def _request(url, token, payload=None, timeout=120):
    data = None
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode()
        return json.loads(body) if body.strip() else {}


def _retry(fn, *args, retries=3, delay=10, **kwargs):
    for attempt in range(retries):
        try:
            return fn(*args, **kwargs)
        except urllib.error.HTTPError as exc:
            if exc.code < 500 and exc.code != 429:  # 4xx = our mistake, don't retry
                raise
            last = exc
        except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as exc:
            last = exc
        if attempt == retries - 1:
            raise last
        print(f"  [retry {attempt + 1}/{retries}] {type(last).__name__}: {last}", flush=True)
        time.sleep(delay)


def norm(s):
    s = unicodedata.normalize("NFKC", s or "").strip().lower()
    s = re.sub(r"[^\w\s]", "", s)
    return re.sub(r"\s+", " ", s)


def aggregator_auth():
    try:
        return _retry(_request, f"{AGGREGATOR}/status", None, timeout=15).get("health", {})
    except Exception as exc:
        print(f"[warn] aggregator status unreachable: {exc}")
        return {}


def lane_summary(lane):
    return _retry(_request, f"{TOOLS[lane]}/download/jobs/summary", lane_token(lane))


def lane_depth(lane):
    try:
        groups = lane_summary(lane)
        return sum(g.get("queued", 0) + g.get("running", 0) for g in groups)
    except Exception:
        return None


def organizer_queue():
    try:
        return _retry(_request, f"{ORGANIZER}/queue/status", organizer_token(), timeout=15)
    except Exception as exc:
        return {"error": str(exc)}


def resolve_artist(lane, artist):
    url = f"{TOOLS[lane]}/search/json?" + urllib.parse.urlencode(
        {"q": artist, "type": "artist"}
    )
    results = _retry(_request, url, lane_token(lane), timeout=30).get("results", [])
    target = norm(artist)
    for r in results:
        if norm(r.get("title") or "") == target:
            return r
    return results[0] if results else None


def dispatch_discography(lane, artist_id, artist_name):
    """Dispatch discography with duplicate-group protection.

    A discography POST accepts the work server-side but may still hit the
    HTTP timeout (huge artists). Blind retry = duplicate mega-group
    (21.9k tracks x3 observed 2026-09-07). A timed-out POST first checks
    /download/jobs/summary: if a group for this artist was created within
    the last 10 min, treat the POST as accepted and return.
    """
    payload = {"artist_id": artist_id or "", "artist_name": artist_name or "",
                "override_existing": "0"}
    url = f"{TOOLS[lane]}/download/discography"

    def _post():
        return _request(url, lane_token(lane), payload=payload)

    def _recent_group_exists():
        try:
            summ = _request(f"{TOOLS[lane]}/download/jobs/summary",
                             lane_token(lane), timeout=30)
        except Exception:
            return False
        groups = summ if isinstance(summ, list) else summ.get("groups", [])
        cutoff = time.time() - 600
        for g in groups:
            if norm(str(g.get("artist") or "")) != norm(artist_name):
                continue
            fa = str(g.get("first_at") or "")
            if not fa:
                continue
            try:
                ts = time.mktime(time.strptime(fa[:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone
            except ValueError:
                continue
            if ts >= cutoff:
                return True
        return False

    def _dispatch():
        return _retry(_post, retries=3, delay=10)

    try:
        return _dispatch()
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as exc:
        if _recent_group_exists():
            msg = '[guard] ' + lane + ': POST timed out but recent group exists - accepted (artist=' + artist_name[:40] + ')'
            print(msg, flush=True)

            return {"guarded": True, "artist": artist_name}
        raise

def dispatch_url(lane, url):
    kind = "playlist" if "playlist" in url else ("album" if "album" in url else "track")
    return _retry(_request, f"{TOOLS[lane]}/download/enqueue", lane_token(lane),
                  payload={"url": url, "kind": kind})


def search_albums(lane, artist):
    url = f"{TOOLS[lane]}/search/json?" + urllib.parse.urlencode(
        {"q": artist, "type": "album"}
    )
    return _retry(_request, url, lane_token(lane), timeout=30).get("results", [])


def spread_albums(usable, platforms, artist):
    """Round-robin an artist's albums across lanes for very large discographies.

    Each lane enqueues albums from its OWN provider catalog (its search results
    carry its own URLs); dedupes by normalized album title so the same release
    is never grabbed twice. All lanes are lossless, so this is purely load
    spreading, not quality trade-off.
    """
    lanes = [l for l in platforms if l in usable]
    lists, cursors = {}, {}
    for lane in lanes:
        try:
            lists[lane] = search_albums(lane, artist)
        except Exception as exc:
            print(f"  [warn] {lane} album search failed: {exc}")
            lists[lane] = []
        cursors[lane] = 0
        time.sleep(THROTTLE)
    print(f"== spread: {sum(len(v) for v in lists.values())} album results "
          f"across {lanes} ==")
    seen, allocated = set(), 0
    while any(cursors[l] < len(lists[l]) for l in lanes):
        for lane in lanes:
            if cursors[lane] >= len(lists[lane]):
                continue
            alb = lists[lane][cursors[lane]]
            cursors[lane] += 1
            title = norm(alb.get("title") or "")
            if not alb.get("url") or title in seen:
                continue
            seen.add(title)
            try:
                dispatch_url(lane, alb["url"])
                allocated += 1
                print(f"  {lane:12} {str(alb.get('title'))[:52]}")
            except Exception as exc:
                print(f"  {lane:12} FAILED {str(alb.get('title'))[:40]}: {exc}")
            time.sleep(THROTTLE)
    print(f"== spread done: {allocated} albums enqueued ==")


def retry_group_errored(group_id):
    """POST /retry for every errored job in a dispatch group (any lane)."""
    for lane in TOOLS:
        try:
            jobs = _retry(_request, f"{TOOLS[lane]}/download/jobs/data", lane_token(lane),
                          timeout=30)
        except Exception as exc:
            print(f"  {lane:12} unreachable: {exc}")
            continue
        for j in jobs:
            if j.get("group_id") == group_id and j.get("status") == "error":
                try:
                    resp = _retry(_request,
                                  f"{TOOLS[lane]}/download/jobs/{j['id']}/retry",
                                  lane_token(lane), payload={}, timeout=30)
                    print(f"  {lane:12} retry {j['id']} ({str(j.get('title'))[:40]}): "
                          f"{json.dumps(resp)}")
                except Exception as exc:
                    print(f"  {lane:12} retry {j['id']} FAILED: {exc}")


def print_group(group_id):
    found = False
    for lane in TOOLS:
        try:
            jobs = _retry(_request, f"{TOOLS[lane]}/download/jobs/data", lane_token(lane),
                          timeout=30)
        except Exception as exc:
            print(f"  {lane:12} unreachable: {exc}")
            continue
        group = [j for j in jobs if j.get("group_id") == group_id]
        if not group:
            continue
        found = True
        print(f"== group {group_id} on {lane} ({len(group)} jobs) ==")
        for j in group:
            prog = (j.get("progress") or 0) * 100
            extra = f"  ERROR: {j['error']}" if j.get("error") else ""
            print(f"  {j['status']:9} {prog:5.1f}%  {j['artist']} — {j['title'][:52]}{extra}")
    if not found:
        print(f"group {group_id} not found on any lane (purged or wrong id)")


def library_albums(artist):
    """Albums the library already holds for an artist (organizer skip-if-known)."""
    url = f"{ORGANIZER}/library/albums?" + urllib.parse.urlencode({"artist": artist})
    return _retry(_request, url, organizer_token(), timeout=30)


def print_status():
    health = aggregator_auth()
    print("== lanes ==")
    for lane, base in TOOLS.items():
        auth = health.get(lane, {}).get("auth", "?")
        depth = lane_depth(lane)
        print(f"  {lane:12} {base}  auth={auth:8} queued+running={depth}")
    print("== organizer queue ==")
    print(f"  {json.dumps(organizer_queue())}")


def cmd_grab(args):
    # --platform (single, for --url) must WIN over the --platforms default list;
    # previously the truthy default made --platform a silent no-op (hit 2026-09-20:
    # `--platform qobuz` still gated on tidal/deezer auth and refused).
    platforms = ([args.platform] if args.platform else None) or args.platforms
    if not platforms:
        sys.exit("pick lanes with --platform <lane> (single) or --platforms a b c")

    health = aggregator_auth()
    expired = [p for p in platforms if health.get(p, {}).get("auth") not in ("ok", "?")]
    if expired:
        sys.exit(f"refusing to dispatch — provider auth expired on: {', '.join(expired)} "
                 f"(check {AGGREGATOR}/status)")

    if args.url:
        lane = platforms[0]
        print(f"[dispatch] url -> {lane}")
        resp = dispatch_url(lane, args.url)
        print(f"  accepted: {json.dumps(resp)}")
        chosen = [lane]
    else:
        if not args.artist:
            sys.exit("give --artist \"Name\" or --url <url>")
        resolutions = {}
        for lane in platforms:
            try:
                r = resolve_artist(lane, args.artist)
                resolutions[lane] = (r.get("id"), r.get("title")) if r else (None, None)
            except Exception as exc:
                print(f"  [warn] {lane} search failed: {exc}")
                resolutions[lane] = (None, None)
            time.sleep(THROTTLE)
        print("== resolutions ==")
        for lane, (aid, title) in resolutions.items():
            print(f"  {lane:12} id={aid}  title={title}")
        usable = {l: v for l, v in resolutions.items() if v[0] or v[1]}
        if not usable:
            sys.exit("no lane resolved that artist — try a different spelling/platform")

        if args.dispatch == "spread":
            spread_albums(usable, platforms, args.artist)
            chosen = [l for l in platforms if l in usable]
        else:
            if args.dispatch == "all":
                chosen = list(usable)
            elif args.dispatch == "least-loaded":
                chosen = [min(usable, key=lambda l: lane_depth(l)
                              if lane_depth(l) is not None else 10**9)]
            else:  # priority (default): first resolvable candidate in priority order
                chosen = [l for l in platforms if l in usable][:1]
            print("== dispatch ==")
            for lane in chosen:
                aid, title = usable[lane]
                try:
                    resp = dispatch_discography(lane, aid, title or args.artist)
                    print(f"  {lane:12} accepted: {json.dumps(resp)}")
                except Exception as exc:
                    print(f"  {lane:12} FAILED: {exc}")
                time.sleep(THROTTLE)

    if args.wait:
        wait_drain(chosen, args.timeout)


def wait_drain(lanes, timeout):
    print(f"== waiting for drain on {', '.join(lanes)} (timeout {timeout}s) ==")
    deadline = time.time() + timeout
    while time.time() < deadline:
        pending = {}
        for lane in lanes:
            d = lane_depth(lane)
            pending[lane] = d
        line = "  " + "  ".join(f"{l}={d}" for l, d in pending.items())
        print(line, flush=True)
        if all(d == 0 for d in pending.values() if d is not None) and pending:
            break
        time.sleep(POLL_INTERVAL)
    print("== lane queues ==")
    print_status()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--status", action="store_true", help="print lane + organizer state")
    ap.add_argument("--artist", help="artist name — resolve + dispatch discography")
    ap.add_argument("--url", help="album/track/playlist URL — enqueue on --platform lane")
    ap.add_argument("--platform", choices=TOOLS, help="single lane (for --url)")
    ap.add_argument("--platforms", nargs="+", choices=TOOLS, default=DEFAULT_PLATFORMS,
                    help="candidate lanes in priority order (default: qobuz tidal deezer)")
    ap.add_argument("--dispatch", choices=["priority", "least-loaded", "all", "spread"],
                    default="priority",
                    help="priority=first available lane (default); spread=round-robin "
                         "albums across lanes for very large discographies")
    ap.add_argument("--wait", action="store_true", help="poll until lane queues drain")
    ap.add_argument("--timeout", type=int, default=3600, help="--wait timeout seconds")
    ap.add_argument("--group", help="dump job statuses for a dispatch group_id")
    ap.add_argument("--retry", action="store_true",
                    help="with --group: POST /retry for every errored job in that group")
    ap.add_argument("--lib", help="list albums the library holds for an artist "
                                  "(organizer /library/albums)")
    ap.add_argument("--poll", action="store_true", help="alias for --status")
    args = ap.parse_args()

    if args.lib:
        resp = library_albums(args.lib)
        albums = resp.get("albums", [])
        print(f"== library holds {len(albums)} albums for '{args.lib}' ==")
        for a in albums:
            print(f"  {a}")
        return

    if args.retry:
        if not args.group:
            sys.exit("--retry needs --group <group_id>")
        retry_group_errored(args.group)
        print_group(args.group)
        return

    if args.group:
        print_group(args.group)
        print_status()
        return

    if args.status or args.poll or not (args.artist or args.url):
        print_status()
        if len(sys.argv) == 1:
            ap.print_help()
        return
    cmd_grab(args)


if __name__ == "__main__":
    main()
