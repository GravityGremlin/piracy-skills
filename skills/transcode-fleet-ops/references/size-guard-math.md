# AV1 size guard + gate math

The custom AV1 converter plugin controls output size through two inputs; the
community size-check gate then vetoes whatever falls outside its own window.
They are coupled — tune them together.

## Preset tiers (the size knobs)

| tier | CRF / SVT preset / depth | estimate @1080p | GB per hour |
|------|--------------------------|-----------------|-------------|
| efficient | CRF 43 / preset 8 / 10-bit | 1333 kbps | ~0.6 GB/h |
| balanced | CRF 32 / preset 7 / 10-bit | 2133 kbps | ~0.96 GB/h |
| high | CRF 26 / preset 6 / 10-bit | 4444 kbps | ~2.0 GB/h |
| archival | CRF 20 / preset 5 / 10-bit | 5556 kbps | ~2.5 GB/h |

GB/h = kbps × 0.45. Estimates scale with output pixel ratio vs 1920×1080
(clamped 0.35×–3×), so 4K outputs estimate ~4× higher and small outputs lower.
`custom` mode reads `crf` / `qmin` / `qmax` from the plugin inputs instead.

Expected film size = GB/h × runtime. A 2–3 h feature therefore lands at
~1–3 GB on `balanced` and ~4–6 GB on `high`, which is how you pick a tier for a
stated target window ("~2–4 GB per film" → `balanced`).

## The floor guard (why big files are skipped, not converted)

With `floor_guard=enabled`, the plugin refuses to encode when its estimate for
the tier would fall below `floor_percent` **of the source bitrate** — the
rationale is that such an encode would be rejected by the size gate anyway, so
it would burn CPU for nothing.

- Ceiling for any source: `max_source_kbps = top_tier_estimate / (floor_percent/100)`.
  At the default 40% that is 5556/0.40 ≈ **13.9 Mbps**; at 5% it is ~111 Mbps.
  Above the line the plugin sets `processFile:false` and the job ends `notRequired`
  with no file change — on every scan, forever.
- Between the lines: if the selected tier's estimate is below the floor, the
  plugin escalates up the ladder `[efficient, balanced, high, archival]` to the
  first tier that clears the floor. If none does, the file is skipped.

## The size gate (a9he-style)

The community size-check plugin (`a9he_New_file_size_check` or equivalent) has
two bounds:

- `lowerBound` (e.g., 50%): output must be at least this % of original size.
  Prevents over-compression (e.g., a 10 GB file becoming 200 MB).
- `upperBound` (e.g., 110%): output must not exceed this % of original size.
  Prevents re-encode bloat (e.g., a 700 MB file becoming 1.5 GB).

When the gate vetoes, it reverts the file and the job ends `transcodeError`.
The file is re-queued on the next scan, re-transcoded, re-vetoed — an infinite
loop until the config is fixed or the file is manually excluded.

## Coupling: guard vs. gate

The floor guard and the size gate must be tuned together:

- If `floor_percent` > `lowerBound`, the guard will skip files the gate would
  have accepted (wasted opportunity).
- If the guard's escalated tier still produces output below `lowerBound`, the
  gate vetoes and reverts (wasted CPU).
- The sweet spot: `floor_percent` ≤ `lowerBound`, and the tier ladder should
  have at least one rung that clears the floor for typical source bitrates.

## Diagnosing a veto loop

1. Find the job reports for the stuck file (see report-parsing.md).
2. Extract the veto numbers: `New file size X which Y% original file size: Z MB`.
3. Check which tier the plugin selected and what its estimate was.
4. Check the gate's `lowerBound` and `upperBound`.
5. Determine: is the file above the floor-guard ceiling (skipped), or between
   the lines but the escalated tier still fails the gate (veto loop)?
6. Fix: adjust `floor_percent`, adjust the tier ladder, or adjust the gate
   bounds — but understand the coupling before changing any one knob.
