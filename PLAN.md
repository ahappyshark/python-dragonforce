# Build Plan — Raw Data Aggregation

Working doc. The goal of this phase is a single reproducible command that produces
`data/processed/tracks.csv` and `data/processed/key_change_events.csv`. No analysis
until that exists and passes validation.

Scope decisions already made:
- **Audio features:** deferred. Entered manually later, but the join is built now so
  hooking them in is dropping a CSV into place, not a refactor.
- **Key-change annotation:** all studio tracks (~110), by ear.
- **Deliverable:** a writeup with charts. The repo is supporting evidence, not the product.

---

## Phase 0 — Fix the foundations

### 0.1 `.gitignore` is going to eat the annotation data
`data/raw/*.csv` is ignored. `data/raw/key_changes_manual.csv` (per the README) matches
that pattern. That is ~10 hours of by-ear listening that git will silently refuse to
track and that disappears with the laptop.

The distinction that matters: `data/raw/` means **regenerable by re-running a fetch**.
Hand annotation is not regenerable. It is irreplaceable primary source data and belongs
under version control.

- [x] Create `data/annotations/`, committed, never gitignored.
- [x] Move all manual/hand-entered CSVs there. `data/raw/` now holds only the
      MusicBrainz JSON cache and the gitignored lyrics cache.
- [x] Update the README's build-order step 4 path.

### 0.2 User-Agent will get you blocked
`src/musicbrainz_client.py` ships `USER_AGENT = "... your-email@example.com ..."`.
MusicBrainz throttles or blocks requests that don't genuinely identify themselves.
Fix before the first real pull.

- [x] Read the User-Agent from `MB_USER_AGENT`, defaulting to the repo URL.

---

## Phase 1 — Finish the MusicBrainz spine (the actual blocker)

The TODO in notebook cell 4: `get_release_tracks()` needs a **release** MBID (a specific
pressing), but `get_release_groups()` returns **release-group** MBIDs (the abstract album).

### The decision: hand-pin the releases. Don't automate it.
Auto-selecting "the canonical pressing" is a rabbit hole — deluxe editions, Japanese
bonus tracks, remasters, and promos that sort earlier by date than the real release.
Every rule you write has an exception in a 9-album discography.

Nine albums is twenty minutes on musicbrainz.org. Pin them in a committed config, write
down *why* you picked each one, and the track count stops changing between runs forever.
That decision log is also exactly the kind of thing that makes a portfolio piece read as
competent rather than lucky.

- [x] Created as `data/albums.json` (JSON rather than YAML to avoid adding a
      dependency for one config file). All nine pressings pinned by hand with a
      `note` explaining each choice, plus `expected_track_count` for the gate.
- [ ] Drop the `secondary-types` filter from the notebook. It's fragile —
      `.apply(lambda x: len(x) == 0)` raises `TypeError` the moment MusicBrainz returns a
      row without that key — and with a hand-pinned list you don't need it. Keep the
      release-group pull as a *check* that the config hasn't gone stale.
- [x] Built as `build_rows()` in `scripts/build_dataset.py` rather than in the
      client, keeping the client a thin MusicBrainz wrapper and the project's
      table shape in one place. `get_release_tracks()` now attaches disc context
      to each track, so 2-disc editions don't produce two ambiguous track 1s.

### Spine schema — decide this now, everything joins to it

| column | why |
|---|---|
| `track_id` | surrogate PK: `slug(album)-{disc}-{track_no}`, e.g. `inhuman-rampage-1-01` |
| `recording_mbid` | MusicBrainz's stable recording ID — the **real** join key |
| `album`, `album_mbid`, `release_mbid` | |
| `release_year` | |
| `disc_no`, `track_no` | |
| `track_title` | as MusicBrainz has it |
| `title_key` | normalized: lowercase, punctuation and parentheticals stripped |
| `length_ms` | |
| `is_bonus_track` | from your curation notes |
| `is_cover` | they've done several — flag them, they'll skew any lyric analysis |
| `is_instrumental` | no lyrics expected; keeps validation honest |

**Join on `recording_mbid`, not `album + track_title`.** The README currently says title —
that's a landmine. Titles drift between sources: feat. tags, `Pt. II` vs `Part 2`, unicode
en-dashes, inconsistent capitalization. Use the MBID as the internal primary key and keep
`title_key` only as the fuzzy bridge to Genius, which has never heard of MBIDs.

---

## Phase 2 — Lyrics

`genius_client.py` has no caching at all — unlike the MusicBrainz client, every run
re-hits the API. Fix that first; you'll be re-running this a lot.

- [x] Disk caching at `data/raw/lyrics/{track_id}.json`, misses cached with a
      reason. The cache holds RAW text and cleaning happens on read, so improving
      the scrubber is a rebuild rather than a re-fetch of ninety songs.
- [x] `data/annotations/genius_overrides.csv` supports four corrections per row:
      `search_title` (search Genius with different text), `genius_song_id` (exact),
      `same_as_track_id` (an alternate cut sharing the base track's words), and
      `no_lyrics_reason`. Pre-seeded with Soldiers of the Wasteland and both
      Power Within collisions. fetch_lyrics.py prints a match report flagging
      every result whose title or artist disagrees with what was searched.
- [x] `clean_lyrics()` plus `strip_section_headers()` and `lyric_stats()`, with 12
      tests in `tests/test_clean_lyrics.py`. Fixtures use invented lyrics, since real
      ones in a public repo would be the redistribution the project rules out.
      Includes adversarial cases: a lyric line containing the word "lyrics", and one
      containing "Embed", must both survive an anchored pattern.
- [x] Copyright discipline is already right in the README: cached lyrics stay local,
      only derived findings get published. `data/raw/lyrics/` is now gitignored explicitly.

---

## Phase 3 — Key-change annotation scaffold

Generate the sheet from the spine so the by-ear pass is pure data entry, not spreadsheet
construction. Anything you have to hand-type twice is a place typos enter the dataset.

- [x] `scripts/make_annotation_sheet.py` → writes **two** files, not one:
      `key_changes.csv` (the event log, starts header-only) and
      `key_change_coverage.csv` (one pre-filled row per track).

      The split is the correction to this bullet's original plan. Events are
      0..n per track, so a track with no key changes contributes no rows — and
      "no key changes" would then be indistinguishable from "not listened to
      yet". Coverage answers that separately, which makes marking a track
      annotated-with-zero-events a positive finding rather than a gap, and makes
      progress through the ~110-track grind countable at any point. Same
      distinction the lyrics cache draws with `no_lyrics_reason`.

      Re-running is safe: hand-entered rows are never rewritten or reordered,
      new spine tracks are appended, and coverage rows whose track has left the
      spine are reported rather than deleted.

### Log events, not counts
Tempting schema: `track_id, n_key_changes`. Don't. A count is one number you can't audit
six weeks later, and it throws away the interesting part.

```
track_id, event_no, timestamp_mm_ss, from_key, to_key, semitones,
type, confidence, notes
```

- `type`: `truck_driver` | `modulation` | `borrowed` | `ambiguous`
- `confidence`: 1–3

Why it's worth the extra columns: `semitones` + `type` lets you ask *"is the +1 semitone
truck-driver key change into the final chorus DragonForce's actual signature move, and did
it survive the vocalist change?"* That's a blog post. "6.2 key changes per album" is a
number nobody remembers.

`confidence` matters because you are the sole annotator. Some calls will be genuinely
ambiguous, and being able to write *"the finding holds when low-confidence calls are
excluded"* is the difference between a defensible result and a vibe.

- [ ] **Double-annotate a 10-track subset, at least two weeks apart, and report your own
      agreement rate.** This is intra-rater reliability. It costs an hour and it is the
      single thing that will make an experienced reader trust a solo by-ear dataset.
      Do the re-pass blind — don't look at your first answers.

---

## Phase 4 — Audio features hook (deferred, wired now)

You'll enter these by hand later. "Easy to hook in later" means the join exists **today**,
against an empty file.

- [ ] `data/annotations/audio_features.csv`, header only for now:
      `track_id, tempo_bpm, key, mode, time_signature, source, notes`
- [ ] `source` is the important column: `manual_tap` | `librosa` | `spotify_legacy`.
      Mixed provenance stays visible in the data instead of being lost. If you ever do run
      librosa on tracks you own, it merges into the same table without a schema change.
- [ ] The joiner left-joins this file whether or not it has rows, and the analysis handles
      an all-NaN column without crashing. Verify that with an empty file now.

---

## Phase 5 — Join + validation

- [x] `scripts/build_dataset.py` (in `scripts/` alongside `explore_releases.py`)
      writes `data/processed/tracks.csv` and `data/processed/key_change_events.csv`.
      Spine, hand-entered flags, lyric counts and key-change annotation all join
      in. Both outputs are written even when an annotation file is empty, so the
      analysis never branches on a missing file.
      `tracks.csv` carries `key_changes_annotated` and `key_change_count`; the
      count is derived from the event log, never entered, and stays blank rather
      than 0 for a track nobody has listened to.

**Make this a script, not a notebook.** Notebooks are for exploring. A notebook that
*builds* your dataset is how you end up unable to reproduce your own numbers, because
cell 12 ran before cell 8 that one time.

### The validation gate
This is the step beginners skip and it's the one that saves you. Plain `assert`s in the
build script, or `pytest`:

- [x] per-album track count matches `expected_track_count` in `albums.json`
- [x] `track_id` unique (error); duplicate `recording_mbid` (warning, since a
      repeated recording can be legitimate); blank `recording_mbid` is an error
- [x] **every `track_id` in every annotation file exists in the spine** — catches hand-entry
      typos, which are otherwise completely silent and produce dropped rows
- [x] `title_key` collisions within an album are reported — two tracks that
      normalize to the same key (e.g. a track and its alternate-lyric version)
      are exactly where automated Genius matching picks the wrong song
- [x] every non-instrumental track has lyrics *or* an explicit recorded reason it doesn't
- [x] `release_year` within a sane range
- [x] `semitones` within -12..12; `from_key`/`to_key` parse as key names
      (`C`, `F#`, `Bb`, `Am`, `C#m` — nothing else), `type` and `confidence`
      inside their domains, `event_no` unique per track, timestamps `m:ss`.
      Plus the cross-check that actually catches tired typing: the two key
      names imply an interval, and it must match the `semitones` written next
      to them (compared mod 12, so `-2` and `+10` both pass). That one is a
      warning, not an error — three fields disagree and no rule can say which
      is wrong. 47 tests in `tests/test_key_changes.py`.

If the build fails the gate, it exits non-zero and writes nothing. Fail loud.

---

## After aggregation — analysis sketch

Not for now, but so you know what the data has to support:

1. Descriptive pass — track lengths, key-change rates, lyric word counts by album era.
2. Lyric NLP — word frequency (TF-IDF over albums), theme buckets, sentiment trend.
3. Key-change analysis — the signature-move question above.
4. Writeup.

### One constraint to keep in mind, whatever questions emerge

The README's example questions are placeholders, not goals — but the sample size
applies to anything you end up asking:

- **Track level (~110 rows)** is fine for distributions, word frequencies, and
  key-change rates. Real analysis is possible here.
- **Album level is n = 9.** Every album-to-album "trend" is eyeballing nine points.
  Chart them, describe them, don't fit regression lines with confidence bands to them.
- **Era comparisons are n = 1 events.** Only one vocalist change, and it's confounded
  with six years passing, different producers, and the genre drifting around them.
  Anything you find there is descriptive, not causal.

None of this blocks a good writeup. It just means the interesting claims will be
"here's what the data looks like and when it changed," not "X caused Y." Say that
plainly in the piece and it reads as competence rather than hedging.

---

## Order of operations

```
0.1 gitignore + annotations dir     ← 10 min, do it first, it protects everything else
0.2 User-Agent                      ← 2 min
1   albums.yml + build_track_table  ← the actual blocker
5   build_dataset.py + validation   ← build it early, run it after every phase
2   lyrics cache + overrides + scrub
3   annotation sheet  → then the ~110-track listening grind
4   audio_features.csv (empty, wired)
```

Phase 5 comes early on purpose. Get the pipeline end-to-end on just the spine, then let
each later phase light up another column. You'll always have something that runs.
