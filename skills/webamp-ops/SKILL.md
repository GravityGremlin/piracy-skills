---
name: webamp-ops
description: Deploy and operate a self-hosted Webamp instance (captbaritone/webamp fork) with custom library data, butterchurn visualizer, and media library window. Covers build pipeline, bundle handling, load-order requirements, CDP verification gates, and known production traps.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [webamp, captbaritone, music, visualizer, butterchurn, deploy]
    related_skills: []

---

# Webamp Ops (Self-hosted)

Operating a self-hosted Webamp fork with a custom music library, butterchurn (Milkdrop) visualizer, and the media library window component.

## Architecture overview

```
Host page (index.html)
  ├─ Static bundle: webamp-butterchurn.js (ES module, default export = WebampWithButterchurn class)
  ├─ Starters script: library.js (starters array + defaultName, reshuffled per load)
  └─ Dynamic library data: library-data.js (WA_LIBRARY object + wa-library event dispatch)
```

**Critical load order** (enforced in prod gates):
1. `library.js` loads → Winamp renders
2. Milkdrop initializes
3. Library window opens (empty is fine)
4. `library-data.js` loads (4.5MB dynamic script) → window re-renders on `wa-library` event

The 4.5MB library-data.js must **never gate Winamp boot**. Verify with timeline gates, not end-state.

## Build pipeline

```bash
# Prerequisites: pnpm, TypeScript
cd /path/to/webamp-fork

# Build all bundles (first time: build dependencies)
pnpm --filter ani-cursor build && pnpm --filter winamp-eqf build
pnpm --filter webamp build

# Type gate
npx tsc -p packages/webamp --noEmit

# Copy bundle with .js extension (nginx serves .mjs as octet-stream; module scripts reject it)
cp packages/webamp/built/webamp.butterchurn-bundle.min.mjs deploy/webamp-butterchurn.js

# Local mirror test (always before deploy)
./stage-localtest.sh  # copies page + bundle + data to .localtest/, serves on 127.0.0.1:8901
```

## Deploy discipline (non-negotiable)

1. **Local mirror first** — run CDP verification gate against local mirror (see cdp-web-verification skill)
2. **Commit + push to git BEFORE any prod deploy** — prod files must match a pushed commit
3. **Bundle copy freshness** — re-copy bundle AFTER final build, re-diff before deploy
4. **Rollback** — keep previous known-good bundle on prod; rollback = scp old files, one command

## Host page requirements (minimal)

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Webamp</title>
  <link rel="stylesheet" href="/webamp-butterchurn.css">
</head>
<body>
  <script type="module">
    import Webamp from "/webamp-butterchurn.js";
    window.Webamp = Webamp;  // REQUIRED: default export IS the butterchurn subclass
    window.LIBRARY_CONFIG = { /* reshuffle seed, etc */ };
  </script>
  <script src="/library.js"></script>           <!-- Starters (tiny, reshuffled) -->
  <script src="/library-data.js"></script>      <!-- Dynamic library (4.5MB, LAST) -->
</body>
</html>
```

**Key traps:**
- `webampWithButterchurn.ts` ends with `window.Webamp = Webamp` (BASE class). Host pages MUST `import Webamp from "/webamp-butterchurn.js"` — the module's default export IS the butterchurn subclass. `new window.Webamp(...)` silently boots with NO milkdrop.
- nginx serves `.mjs` as `application/octet-stream`; ES modules reject it. Serve bundle as `.js` (application/javascript) OR add full `types {}` block in nginx (replaces inherited mime table — enumerate every type you serve).
- Group-drag connection requires ABUTMENT (15px snap), overlap rejects. Docking: compute from live state, never hardcode.

## Library data generation

```bash
# Scan music collection → emit library.js (starters) + library-data.js (WA_LIBRARY)
python3 scripts/webamp-tracks.py /path/to/music --output-dir /deploy/

# library.js: ~15KB, starters array with defaultName "Artist - Title", reshuffled per page load (Fisher-Yates)
# library-data.js: ~4.5MB, sets window.WA_LIBRARY + dispatches 'wa-library' CustomEvent
```

## Verification gates (CDP-based)

```bash
# Local gate (after stage-localtest.sh)
python3 deploy/verify/verify-lib-content.py      # Library window loads, search works
python3 deploy/verify/verify-toggle-buttons.py   # Milkdrop/Library toggles work
python3 deploy/verify/verify-fit-workspace.py    # Library maximize/restore works

# Prod gate (after deploy)
python3 deploy/verify/verify-prod-libsearch.py   # Search on 30k rows, no UI freeze
```

## Known production traps (all hit in prod 2026)

| Trap | Symptom | Fix |
|------|---------|-----|
| Bundle extension | Milkdrop never loads | Serve as `.js`, not `.mjs` |
| Import target | Milkdrop missing | Import from bundle default export, not `window.Webamp` |
| Late data race | Library window empty | Check `window.WA_LIBRARY` at effect start AND listen for `wa-library` event |
| 30k-row search freeze | UI freezes on keystroke | One-time lowercase index + 120ms debounce + 400-row cap |
| Gen-window sizing | Wrong dimensions | Formula: `(275 + w*25) × (116 + h*29)` from `size: [w, h]` |
| Live rendition filter | Live tracks missing from starters | Filter on RAW title (`"live" in title.lower()`) before normalizer strips parens |

## Configuration

- **Starters spec**: `STARTERS_SPEC` = list of {artist, limit} → top-N tracks each, reshuffled per load
- **Default playlist**: Fisher-Yates reshuffle per page load (generator round-robin stays fixed-seed)
- **Milkdrop/Library**: Start CLOSED; toggle via host-page buttons (`TOGGLE_WINDOW` action)
- **Audio source**: Read-only mount of music collection; Webamp fetches via HTTP range requests

## Upstream sync

Fork base: `captbaritone/webamp`. Track upstream for:
- Butterchurn version updates
- Core Winamp skin/engine fixes
- React/TypeScript dependency updates

Cherry-pick upstream commits; fork internals touched: constants/types, windows reducer, App.tsx render, LibraryWindow, webampWithButterchurn.