"""
Schema and validation for the hand-entered audio features.

    data/annotations/audio_features.csv

Deferred data, wired now. Spotify killed the audio-features endpoint for new
apps in November 2024 and nothing has replaced it, so tempo and key get entered
by hand — tapped out, or run through librosa on tracks we own. That work has not
started and may not for a while, which is exactly why the join exists today:
"easy to hook in later" is only true if the joiner, the validation and the
column names are already in place and already exercised against an empty file.
An all-blank column that flows through the pipeline is a solved problem; a
column that appears for the first time six months from now is a refactor.

`source` is the column that earns its place. Mixed provenance is inevitable here
— a tempo tapped by hand and one measured by librosa are not the same
measurement, and an analysis that averages them without knowing is quietly
wrong. Recording it per row keeps that visible in the data instead of in
somebody's memory.

Every field except track_id is optional. Rows get filled in a column at a time
(all the tempos in one sitting, keys later), so a row carrying only a tempo is
a normal intermediate state, not an error.
"""

import re
from typing import Any

COLUMNS: list[str] = [
    "track_id", "tempo_bpm", "key", "mode", "time_signature", "source", "notes",
]

# Columns that join onto the spine. `source` is renamed on the way in: `source`
# alone is ambiguous in a 25-column table that also carries lyric and
# MusicBrainz provenance.
JOIN_COLUMNS: dict[str, str] = {
    "tempo_bpm": "tempo_bpm",
    "key": "audio_key",
    "mode": "audio_mode",
    "time_signature": "time_signature",
    "source": "audio_source",
}

SOURCES: set[str] = {"manual_tap", "librosa", "spotify_legacy"}
MODES: set[str] = {"major", "minor"}

# Tonic only — the mode lives in its own column, so "Am" here would be saying
# the same thing twice and inviting the two to disagree.
_KEY_PATTERN: re.Pattern[str] = re.compile(r"\A[A-G][#b]?\Z")
_TIME_SIGNATURE_PATTERN: re.Pattern[str] = re.compile(r"\A\d{1,2}/\d{1,2}\Z")

# Power metal is fast, not impossible. Outside this range it is a typo — a
# doubled or halved reading, or a stray digit — rather than a real tempo.
MIN_BPM: float = 40.0
MAX_BPM: float = 300.0


def _blank(value: Any) -> bool:
    return str(value or "").strip() == ""


def validate_audio_features(
    rows: list[dict[str, Any]],
    spine_ids: set[str],
) -> tuple[list[str], list[str]]:
    """Check the audio-features sheet against the spine. Returns (errors, warnings).

    Blank cells are skipped, not flagged: the file is filled in a column at a
    time over months. What is checked is that anything actually written down is
    a value the analysis can use.
    """
    errors: list[str] = []
    warnings: list[str] = []
    seen: set[str] = set()

    for index, row in enumerate(rows, start=2):  # start=2: row 1 is the header
        track_id: str = str(row.get("track_id", "")).strip()
        where: str = f"audio_features.csv line {index}"
        if not track_id:
            errors.append(f"{where}: blank track_id")
            continue
        if track_id not in spine_ids:
            errors.append(f"{where}: track_id {track_id!r} is not in the spine")
            continue
        if track_id in seen:
            errors.append(f"{where}: duplicate row for {track_id!r}")
        seen.add(track_id)

        tempo: Any = row.get("tempo_bpm")
        if not _blank(tempo):
            try:
                bpm: float = float(str(tempo).strip())
            except ValueError:
                errors.append(f"{where}: tempo_bpm {tempo!r} is not a number")
            else:
                if not MIN_BPM <= bpm <= MAX_BPM:
                    errors.append(f"{where}: tempo_bpm {bpm} outside "
                                  f"{MIN_BPM:.0f}-{MAX_BPM:.0f}")

        key: str = str(row.get("key", "")).strip()
        if not _blank(key) and not _KEY_PATTERN.match(key):
            errors.append(f"{where}: key {key!r} should be a tonic only "
                          f"(C, F#, Bb) — the mode goes in the mode column")

        mode: str = str(row.get("mode", "")).strip().lower()
        if not _blank(mode) and mode not in MODES:
            errors.append(f"{where}: mode {mode!r} is not one of {sorted(MODES)}")

        time_signature: str = str(row.get("time_signature", "")).strip()
        if not _blank(time_signature) and not _TIME_SIGNATURE_PATTERN.match(time_signature):
            errors.append(f"{where}: time_signature {time_signature!r} should look "
                          f"like 4/4")

        source: str = str(row.get("source", "")).strip()
        if _blank(source):
            # Not an error, because a half-filled row is legitimate — but a
            # measurement whose provenance is unrecorded cannot be pooled with
            # one whose provenance is known, so it has to be visible.
            if not all(_blank(row.get(c)) for c in ("tempo_bpm", "key", "mode",
                                                    "time_signature")):
                warnings.append(
                    f"{where}: {track_id} has measurements but no source — "
                    f"record one of {sorted(SOURCES)} so mixed provenance stays visible"
                )
        elif source not in SOURCES:
            errors.append(f"{where}: source {source!r} is not one of {sorted(SOURCES)}")

    return errors, warnings
