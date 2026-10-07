# Reading transcode job reports

Field-tested recipes from an audit session. All paths relative to
`<data-dir>/server/Tdarr/DB2/JobReports/`.

## Layout

- One dir per job (`<jobId>/`), files named `<jobId>()<tdarrVer>()<stage>()<workerId>()<ts>.txt`.
- Same job dir accumulates one .txt per worker ATTEMPT (a file that re-fails on
  every scan gains a new report per scan — span of mtimes across days = stuck queue).

## Live-file gotchas

- Reports are LIVE: the `Successfully updated server verdict: ...` line is
  appended by the server some minutes after the job events, so verdict regexes
  can miss on fresh files. Classify by markers in the LAST ~3000 chars
  (`[-success-]` / `[-error-]`), not by first-match.
- mtime ordering shifts between calls as the server appends; never index into
  a cached find() row list across calls. Re-sort per call, dedupe by jobId dir.

## Homoglyphs break text regexes

Plugin/log text contains non-ASCII look-alikes inside words (`which`, `original`
in the size-check veto line), so `r"which (\d+)%"` silently fails while the line
prints fine. Workarounds:

- Anchor on ASCII substrings that do appear literally: `not within limits`,
  `is above floor`, `[-success-]`, `[-error-]`, `Pre-processing Tdarr_Plugin_`.
- Extract numbers from RAW BYTES around the anchor, e.g.
  `i = raw.find(b"not within limits")` then slice 140 bytes and
  `re.findall(rb"(\d{2,4})\s?%", slice)` (first pct = growth, 110% = upperBound).
- Or clean once with `re.sub(r"[^\x00-\x7f]", " ", s)` — but beware fused words
  after dropping NBSP-style chars; prefer byte-anchored slicing for numbers.

## Reconstructing what ran

- Cycles: `[Step W02] [C3] Running pre-process file` ... `[Step W06] [C3] Worker [-success-]`.
  Each cycle re-runs the full plugin stack (audio downmixes created in C1 can
  be re-budgeted in C3 — see plugin-deploy.md incident class 1).
- Per-cycle input/output sizes: `Source file size:` lines and
  `Updating transcode stats` boundaries.

## Sizing the queue

- `find . -type f -newermt '<date>' -printf '%T@\t%p\n' | sort -n` for activity
  windows; per-day histograms spot the drift (2348/day → ~0 → 22 on a churn
  day).
- `grep -rl "not within limits" --include=*.txt .` + `stat -c %Y` cutoff for
  error-class counts since a restart; dedupe by parent dir for unique jobs.

## Terminal/output-channel mangling (display vs file)

Output shown in tool results can drop ` = `, `||`, `&&`, `>`, `=>` from
pure-ASCII lines (emoji-bearing lines survive). Consequences + discipline:

- Never trust displayed file content for exact-string edits; read exact bytes
  by printing them base64-encoded (`base64.b64encode(line)`) — base64 is
  immune — then decode mentally or programmatically.
- Make operator-heavy edits by writing the file from python (execute_code
  bytes-exact with count asserts), then re-verify with `node --check` and a
  targeted base64 print of the changed region.
