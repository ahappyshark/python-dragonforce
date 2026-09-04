# DragonForce Discography Analysis

A data science portfolio project analyzing DragonForce's full studio discography:
lyrical themes, audio characteristics (tempo, key, energy), and manually-annotated
key-change frequency, tracked across their career arc.

## Questions this project explores
- Does tempo/energy/valence trend downward after *Ultra Beatdown*?
- How many songs contain a key change, and how many contain more than one?
- What lyrical themes dominate each album era (battle / heaven-hell / time-eternity / etc.)?
- Do lineup changes (vocalist especially) correlate with audible shifts in the data?

## Project structure
```
python-dragonforce/
├── data/
│   ├── raw/           # cached API responses — written by code, never edited by hand
│   ├── annotations/   # hand-entered data (key changes, audio features)
│   └── processed/     # cleaned, joined tables built by the pipeline
├── notebooks/
│   └── 01_aggregate_metadata.ipynb   # start here
├── src/
│   ├── musicbrainz_client.py   # album/track/lineup metadata
│   ├── spotify_client.py       # tempo, key, energy, valence per track
│   └── genius_client.py        # lyrics for NLP (local use only, see note below)
├── PLAN.md            # build plan and working checklist
├── requirements.txt
└── .env.example       # copy to .env and fill in your own API keys
```

The three data directories differ by **where the data comes from**, not by how
clean it is:

| directory | source | committed? |
|---|---|---|
| `data/raw/` | fetched by a client module, regenerable | yes — MusicBrainz JSON is CC0 and small, so a fresh clone runs offline. Lyrics are the exception and stay local. |
| `data/annotations/` | typed by hand, **not** regenerable | always. Losing this means re-listening to the whole discography. |
| `data/processed/` | built by the pipeline from the two above | yes — it's ~110 rows, and tracking it means a pipeline change shows up as a reviewable diff |

Nothing in `data/raw/` or `data/processed/` should ever be edited by hand. If a
value there is wrong, fix the code or the annotation that produced it and re-run.

## Build order
1. **Metadata backbone** — MusicBrainz gives album/track/year/writer/lineup.
   This is the spine table everything else joins to. Responses are cached to
   `data/raw/` on the first pull and read from disk on every run after that, so
   re-running the notebook is free and works offline. That cache is committed, so
   a fresh clone doesn't need to hit the API at all. Pass `refresh=True` to any
   client function when you actually want a fresh fetch.
2. **Spotify audio features** — ⚠️ **currently broken.** Spotify killed
   `audio-features`/`audio-analysis` for new apps in Nov 2024, no official
   replacement exists yet. Album/track metadata via Spotify still works.
   See `src/spotify_client.py` docstring for fallback options.
3. **Lyrics + NLP** — Genius API for lyric text, then word-frequency /
   theme-bucket analysis locally.
4. **Manual key-change annotation** — the one API-can't-do-it step. Spotify's
   `key` field is one estimate per whole track and misses mid-song modulations.
   Run `python scripts/make_annotation_sheet.py` to generate the sheets, then
   log by ear into `data/annotations/key_changes.csv`, one row per key change
   rather than a count per track, so each call stays auditable later. Tick each
   track off in `data/annotations/key_change_coverage.csv` as you finish it —
   including tracks that turn out to have no key changes, which is a finding and
   not a gap. `build_dataset.py` validates both and writes
   `data/processed/key_change_events.csv`. See `PLAN.md` for the column layout.

## Note on lyrics/copyright
Genius' API is fine for pulling lyrics into local analysis, but don't publish
or redistribute the raw lyric text in the portfolio piece — publish the
*findings* (word frequency charts, theme clustering, sentiment trends), not
the lyrics themselves.

## Setup
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env      # then fill in your API keys
```

`MB_USER_AGENT` is the only value needed to pull MusicBrainz data — it takes no
API key, but it does require a User-Agent identifying the client. The default in
`.env.example` uses this repo's URL as the contact route, so it works as-is.
Spotify and Genius keys are only needed for those steps.

Then either run the fetch scripts directly:

```bash
python scripts/explore_releases.py   # list pressings per album
```

or explore interactively:

```bash
jupyter notebook
```
