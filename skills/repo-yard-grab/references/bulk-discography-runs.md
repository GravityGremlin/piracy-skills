# Bulk discography runs (many artists, one request)

Applies when a request names a lot of artists at once ("get the discogs for
A, B, C, …") rather than one band. Run it in two phases — resolve+dispatch,
then curate — with a state file so the run is resumable.

## Phase 0 — resolve every id in one pass, print them for review

Search `type=artist` for each name and print `id -> name` for the top few
candidates. Tidal returns *related* artists alongside the match, so the list
is mostly noise; the signal is the candidate whose name equals the request
exactly (normalise case and diacritics first).

Empty or missing candidate lists mean the lane search is incomplete for that
name — resolve those by hand rather than letting the fallback pick candidate
#1.

**Never dispatch the whole list before reviewing the ids.** A wrong id imports
a stranger's discography, and cancelling it afterwards still costs downloads.

## Same-name artists: probe by album fingerprint

Names shared across bands are the failure mode, and a name search cannot tell
them apart: `Tragedy` (NYHC vs. a rapper), one USBM band (vs. an Italian
hardcore band), `Judge`, `Nails`, `Terror`, `Integrity`, `Grave`, `Warzone`, `Strife`
all resolve to a plausible-looking id whose albums may belong to someone else.

Probe cheaply: dispatch `kind=artist` for the candidate, wait ~3 s, then read
the jobs back by `group_id` and compare the queued **album titles** against the
band you meant.

- Titles match (e.g. `Vengeance`/`Nerve Damage` for Tragedy, `The Tenth Sub
  Level Of Suicide` for that USBM band, `Bringin' It Down` for Judge, `Abandon All
  Life` for Nails) → the entity is right. Keep the group; the probe *is* that
  artist's dispatch, so record the `group_id` and do not re-dispatch.
- Titles belong to another act → cancel every job in the group before anything
  downloads, then try the next candidate id.

One POST per ambiguous name beats discovering the mistake after 15 albums
land in the library.

## Phase 1 — dispatch

One POST per artist (`kind=artist`, `no_singles=1`). The per-client bucket is
sized for track dispatches, so ~50 artist dispatches pace out in ~2 minutes at
2.2 s and never approach the cap. Persist `{artist: {artist_id, group_id}}` to
a state file after every dispatch so a crashed or interrupted run resumes
without double-queueing.

## Phase 2 — curate every group, no exceptions

A discography dispatch returns editions, comps, live albums, demo collections
and reissues as separate jobs. Per group, keep studio albums only:

1. Drop non-studio: title matching live / remix / compilation / greatest /
   anthology / collection / singles / B-sides / sessions / demo / acoustic /
   soundtrack / tribute / hits / box set / rarities / anniversary.
2. Drop albums already in the library (per-artist dir check, not a global title
   scan).
3. Collapse edition duplicates: strip parentheticals and deluxe/remaster/
   expanded/edition tokens to form the key, keep one per key, preferring the
   deluxe/expanded version.

Cancel the rejects paced (~2.2 s); a burst 429s and silently leaves non-studio
jobs queued. Re-audit after the cancels: anything still in the group that
failed to cancel must be cancelled in a second pass, or a comp imports.

## Probe groups must curate too

A group dispatched via the fingerprint probe (dispatch `kind=artist` to check
titles, then keep) skips the normal curation pass by default, so its lives,
comps, demos and edition duplicates land uncurated. Pentagram, Cathedral and
Master all landed with extra releases because they were probe-only. Every
dispatched group — probe or not — must pass through the full curation pass
(drop non-studio, drop owned, collapse edition duplicates) before the run is
called complete.

## Verify after the import drain

Per artist: album directories present under `/music/<Artist>`, and per-album
track counts sane. A comp that slipped through shows up as an extra dir with a
`(Live)`/`Greatest` name; a duplicate edition shows as two dirs whose titles
differ only by `(Deluxe)`. Compare the number of kept groups against planned
artists and report the misses explicitly — a silent short batch looks like
success in the log.

Collab/family albums organize under combined artist dirs — Trio lands under
"Dolly Parton, Linda Ronstadt & Emmylou Harris", not under any solo artist.
When the verifier reports a missing album, check combined-artist dirs before
declaring a gap; the album may have landed under a shared credit.
