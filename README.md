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
dragonforce-analysis/
├── data/
│   ├── raw/          # untouched API pulls (json/csv), never edited by hand
│   └── processed/     # cleaned, joined tables ready for analysis
├── notebooks/
│   └── 01_aggregate_metadata.ipynb   # start here
├── src/
│   ├── musicbrainz_client.py   # album/track/lineup metadata
│   ├── spotify_client.py       # tempo, key, energy, valence per track
│   └── genius_client.py        # lyrics for NLP (local use only, see note below)
├── requirements.txt
└── .env.example       # copy to .env and fill in your own API keys
```

## Build order
1. **Metadata backbone** — MusicBrainz gives album/track/year/writer/lineup.
   This is the spine table everything else joins to.
2. **Spotify audio features** — ⚠️ **currently broken.** Spotify killed
   `audio-features`/`audio-analysis` for new apps in Nov 2024, no official
   replacement exists yet. Album/track metadata via Spotify still works.
   See `src/spotify_client.py` docstring for fallback options.
3. **Lyrics + NLP** — Genius API for lyric text, then word-frequency /
   theme-bucket analysis locally.
4. **Manual key-change annotation** — the one API-can't-do-it step. Spotify's
   `key` field is one estimate per whole track and misses mid-song modulations.
   This gets logged by ear into `data/raw/key_changes_manual.csv`.

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
jupyter notebook
```
