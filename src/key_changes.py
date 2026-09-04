"""
Schema and validation for the by-ear key-change annotation.

Two hand-entered files, on purpose:

  data/annotations/key_changes.csv           one row per key change EVENT
  data/annotations/key_change_coverage.csv   one row per TRACK, listened or not

The split exists because a track with no key changes contributes zero event
rows, which is indistinguishable from a track nobody has listened to yet. That
is the same "correctly absent vs. we failed to get it" distinction the lyrics
cache makes with no_lyrics_reason, and it matters more here: the annotation is
~110 tracks of listening done by one person over weeks, so "how far in am I"
has to be answerable from the data at any point.

Marking a track annotated with no events is therefore a positive claim —
"I listened to this the whole way through and it never changes key" — not a gap.

Key names use a strict compact format so they sort and compare without
normalization: an uppercase tonic A-G, an optional accidental (# or b), and an
optional trailing m for minor. C, F#, Bb, Am, C#m, Ebm. Nothing else parses;
"C major", "c#", and "Bbmin" are all rejected at build time rather than
silently becoming a category of their own halfway through the dataset.
"""

import re
from typing import Any

# The hand-entered event schema from PLAN.md. Order is the column order in the
# generated sheet, so it is also what the annotator reads left to right.
EVENT_COLUMNS: list[str] = [
    "track_id", "event_no", "timestamp_mm_ss", "from_key", "to_key",
    "semitones", "type", "confidence", "notes",
]

COVERAGE_COLUMNS: list[str] = [
    "track_id", "album", "track_title", "annotated", "listened_at", "notes",
]

# truck_driver is the genre's signature move (the +1 shove into a final chorus)
# and the whole reason type is a column rather than a note: it is the one
# category the analysis actually asks a question about.
EVENT_TYPES: set[str] = {"truck_driver", "modulation", "borrowed", "ambiguous"}

MIN_CONFIDENCE: int = 1
MAX_CONFIDENCE: int = 3

# Enharmonics share a pitch class. Db and C# are the same sound, and an
# annotator will not be consistent about which one they write at 1am, so
# comparison happens on the number and the spelling is preserved as typed.
_NATURALS: dict[str, int] = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_KEY_PATTERN: re.Pattern[str] = re.compile(r"\A([A-G])([#b]?)(m?)\Z")
_TIMESTAMP_PATTERN: re.Pattern[str] = re.compile(r"\A\d{1,2}:[0-5]\d\Z")

# An octave. A key change of 0 semitones is legitimate — a borrowed/modal shift
# like C to Cm keeps the tonic and changes only the mode.
MIN_SEMITONES: int = -12
MAX_SEMITONES: int = 12


def parse_key(text: str) -> tuple[int, bool] | None:
    """Return (pitch_class, is_minor) for a key name, or None if unparseable."""
    match: re.Match[str] | None = _KEY_PATTERN.match((text or "").strip())
    if match is None:
        return None
    natural, accidental, minor = match.groups()
    pitch: int = _NATURALS[natural]
    if accidental == "#":
        pitch += 1
    elif accidental == "b":
        pitch -= 1
    return pitch % 12, minor == "m"


def expected_semitones(from_key: str, to_key: str) -> int | None:
    """Upward distance in semitones between two key names, 0-11, or None.

    Returns the ascending interval. A recorded -2 and a recorded +10 describe
    the same pair of keys, so callers compare modulo 12 rather than directly.
    """
    origin = parse_key(from_key)
    target = parse_key(to_key)
    if origin is None or target is None:
        return None
    return (target[0] - origin[0]) % 12


def is_valid_timestamp(text: str) -> bool:
    """True for m:ss or mm:ss. Songs here run long, but never past 99 minutes."""
    return bool(_TIMESTAMP_PATTERN.match((text or "").strip()))


def _as_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def validate_events(
    events: list[dict[str, Any]],
    coverage: list[dict[str, Any]],
    spine_ids: set[str],
) -> tuple[list[str], list[str]]:
    """Check both annotation files against each other and the spine.

    Returns (errors, warnings). Errors are things that would corrupt the
    analysis — an unknown track_id, an unparseable key, a confidence outside
    the scale — and stop the build. Warnings are things only the annotator can
    resolve, chiefly a semitone count that disagrees with the two key names.

    Deliberately strict about the value domains and lenient about completeness:
    an empty sheet is the normal state for months, and must produce no output
    at all rather than a hundred "not yet annotated" lines.
    """
    errors: list[str] = []
    warnings: list[str] = []

    covered: dict[str, dict[str, Any]] = {}
    for row in coverage:
        track_id: str = str(row.get("track_id", "")).strip()
        if not track_id:
            continue
        if track_id not in spine_ids:
            errors.append(
                f"key_change_coverage.csv: track_id {track_id!r} is not in the spine"
            )
            continue
        if track_id in covered:
            errors.append(f"key_change_coverage.csv: duplicate row for {track_id!r}")
        covered[track_id] = row

    annotated: set[str] = {
        track_id for track_id, row in covered.items()
        if str(row.get("annotated", "")).strip().lower() in {"yes", "y", "true", "1"}
    }

    seen_events: dict[str, list[int]] = {}
    for index, row in enumerate(events, start=2):  # start=2: row 1 is the header
        track_id = str(row.get("track_id", "")).strip()
        where: str = f"key_changes.csv line {index}"
        if not track_id:
            errors.append(f"{where}: blank track_id")
            continue
        if track_id not in spine_ids:
            errors.append(f"{where}: track_id {track_id!r} is not in the spine")
            continue

        event_no: int | None = _as_int(row.get("event_no"))
        if event_no is None or event_no < 1:
            errors.append(f"{where}: event_no must be a positive integer, "
                          f"got {row.get('event_no')!r}")
        else:
            seen_events.setdefault(track_id, []).append(event_no)

        timestamp: str = str(row.get("timestamp_mm_ss", "")).strip()
        if not is_valid_timestamp(timestamp):
            errors.append(f"{where}: timestamp_mm_ss must look like 3:47, "
                          f"got {timestamp!r}")

        from_key: str = str(row.get("from_key", "")).strip()
        to_key: str = str(row.get("to_key", "")).strip()
        for label, value in (("from_key", from_key), ("to_key", to_key)):
            if parse_key(value) is None:
                errors.append(f"{where}: {label} {value!r} is not a key name "
                              f"(expected e.g. C, F#, Bb, Am, C#m)")

        semitones: int | None = _as_int(row.get("semitones"))
        if semitones is None:
            errors.append(f"{where}: semitones must be an integer, "
                          f"got {row.get('semitones')!r}")
        elif not MIN_SEMITONES <= semitones <= MAX_SEMITONES:
            errors.append(f"{where}: semitones {semitones} outside "
                          f"{MIN_SEMITONES}..{MAX_SEMITONES}")
        else:
            # The cross-check that actually catches typing mistakes: the two key
            # names imply an interval, and it has to be the one that was written
            # down. Compared mod 12 so descending (-2) and its ascending
            # spelling (+10) both pass.
            implied: int | None = expected_semitones(from_key, to_key)
            if implied is not None and semitones % 12 != implied:
                warnings.append(
                    f"{where}: {from_key}->{to_key} is {implied} semitones up, "
                    f"but the row says {semitones} — one of the three is a typo"
                )

        event_type: str = str(row.get("type", "")).strip()
        if event_type not in EVENT_TYPES:
            errors.append(f"{where}: type {event_type!r} is not one of "
                          f"{sorted(EVENT_TYPES)}")

        confidence: int | None = _as_int(row.get("confidence"))
        if confidence is None or not MIN_CONFIDENCE <= confidence <= MAX_CONFIDENCE:
            errors.append(f"{where}: confidence must be "
                          f"{MIN_CONFIDENCE}-{MAX_CONFIDENCE}, "
                          f"got {row.get('confidence')!r}")

        if track_id not in annotated:
            warnings.append(
                f"{where}: {track_id} has events but its coverage row is not "
                f"marked annotated — mark it, or the track reads as unlistened"
            )

    for track_id, numbers in seen_events.items():
        if len(set(numbers)) != len(numbers):
            errors.append(f"key_changes.csv: {track_id} has duplicate event_no "
                          f"{sorted(n for n in set(numbers) if numbers.count(n) > 1)}")
        elif sorted(numbers) != list(range(1, len(numbers) + 1)):
            warnings.append(
                f"key_changes.csv: {track_id} event_no runs {sorted(numbers)} — "
                f"expected 1..{len(numbers)} with no gaps"
            )

    return errors, warnings
