---
name: anti-bot-scraping
description: "Use when scraping bot-walled APIs: TLS fingerprint walls."
version: 1.0.0
license: MIT
---

# Anti-Bot Scraping (authenticated session pools)

Class task: programmatically pull data from sites that fingerprint clients
or login-wall APIs (Instagram, X-class platforms), and build front-ends on
top of such APIs. Distinct from blocked-page-recovery, which recovers single
pages via third-party copies — this drives the site's own API under real
sessions.

## Rules (always-on)

- Uniform 429s (empty body) or HTTP 200 with opaque "couldn't be processed"
  error JSON from python, while the SAME request+cookies replayed in a real
  browser succeeds → the wall is TLS/HTTP2 fingerprinting, not the IP,
  headers, or cookies. Fix: `curl_cffi` `Session(impersonate="chrome131")`
  (verified against Instagram). Prove/kill the hypothesis FIRST by replaying
  one captured request both ways (browser via CDP, python) — don't burn time
  rotating IPs or header sets; the server scores the handshake, headers are
  irrelevant to it.
- Before blaming an IP ban, hit a second endpoint on the same host from the
  same client: a 200 elsewhere proves the IP is fine and the block is
  endpoint+fingerprint specific.
- A session can be SOFT-BLOCKED while every liveness check stays green: HTTP
  200 whose body carries an in-band error (Facebook/IG `__ar` error codes like
  1357004) means benched, not dead. Classify by endpoint class from the
  response body, not the status code.
- Session pools: rotate on soft-block, not on hard 401/403. A hard auth
  failure means the session is dead; a soft block means the fingerprint was
  flagged. Keep both classes in separate pools with independent backoff.
- Rate-limit headers (`X-RateLimit-Remaining`, `Retry-After`) are advisory —
  the server may enforce tighter limits than it advertises. Stay at 50% of
  the advertised limit when scraping at scale.

## Session pool architecture

```python
from curl_cffi import requests as cffi_requests

class SessionPool:
    def __init__(self, impersonate="chrome131", pool_size=5):
        self.sessions = [
            cffi_requests.Session(impersonate=impersonate)
            for _ in range(pool_size)
        ]
        self.current = 0

    def get(self, url, **kwargs):
        session = self.sessions[self.current]
        self.current = (self.current + 1) % len(self.sessions)
        resp = session.get(url, **kwargs)
        if resp.status_code == 200 and self._is_soft_blocked(resp):
            self._rotate_and_backoff()
        return resp

    def _is_soft_blocked(self, resp):
        # Check for in-band error codes in 200 responses
        try:
            data = resp.json()
            return data.get("__ar") or data.get("error", {}).get("code") in (1357004,)
        except Exception:
            return False
```

## Impersonation targets (curl_cffi)

| Target | Use when |
|--------|----------|
| `chrome131` | Instagram, Facebook, most TLS-fingerprinted sites |
| `safari17_0` | Apple-ecosystem sites, iCloud |
| `chrome124` | Older sites that reject newer Chrome fingerprints |

## Related skills

- `scraping-to-api` — build the API when none exists
- `blocked-page-recovery` — recover single blocked pages via archives
