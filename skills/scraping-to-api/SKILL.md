---
name: scraping-to-api
description: "Use when a service has no API: build one via UI automation."
version: 1.0.0
license: MIT
---

# Scraping-to-API: build the API the vendor didn't ship

Trigger: a service has a web UI (or app) but no official API, and you need
programmatic access. Key insight: if a web UI exists, an unofficial API
already exists — the front end has to talk to the backend somehow. Walk this
ladder, best door first. The barrier to doing this by hand collapsed: one
person with coding agents can automate a UI in an afternoon.

## When to Use

- A service you need data from offers only a web UI or app — no API, no
  export path.
- An API exists but lacks the endpoint/scope you need (same ladder applies,
  one rung up).
- You're entitled to the data (own account, own org) but the vendor won't
  give you programmatic access.

## The ladder

1. **Undocumented public endpoints** — /api/, /graphql, .json suffixes,
   RSS/Atom, CSV export buttons. Check before automating anything.
2. **Internal JSON API** (the front end's own calls) — capture once, replay
   with a session. Best stability-per-effort: structured data, and UI
   redesigns change the DOM far more than they change these calls.
3. **HTML scraping** (BeautifulSoup / pandas.read_html) — when calls can't
   be replayed, parse the pages. Most fragile rung. Some apps only offer
   manual CSV exports; automate the button click.
4. **Full headless-browser automation** (Playwright) — the
   last resort when the data is rendered client-side only or behind
   complex auth flows.

## Capturing internal API calls

```python
# Intercept network requests via Playwright
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()

    api_calls = []
    def handle_request(request):
        if "/api/" in request.url or request.url.endswith(".json"):
            api_calls.append({
                "url": request.url,
                "method": request.method,
                "headers": dict(request.headers),
                "post_data": request.post_data,
            })

    page.on("request", handle_request)
    page.goto("https://example.com/app")
    # Navigate, log in, trigger the data load you need
    # ...
    browser.close()
```

## Replaying captured calls

```python
import requests

session = requests.Session()
# Copy cookies from the browser session
session.cookies.update(captured_cookies)

resp = session.get(
    "https://api.example.com/v1/data",
    headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        # Copy other headers from the capture
    }
)
```

## Stability tips

- Prefer JSON APIs over HTML scraping — they survive UI redesigns.
- Cache captured responses during development; replay live only for fresh data.
- Respect rate limits — the vendor's official API (if one exists) may have
  documented limits you can infer.
- When automating a UI, add waits for network idle, not fixed sleeps.

## Related skills

- `anti-bot-scraping` — handle TLS fingerprint walls
- `blocked-page-recovery` — recover single blocked pages
