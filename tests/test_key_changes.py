"""
Tests for the key-change annotation schema.

The point of these is that the validation gate is the only thing standing
between a typo made at 1am and a chart built on it. Every check here
corresponds to a mistake a tired human actually makes: a flat written as a
lowercase letter, a semitone count that contradicts the two keys next to it, a
confidence of 5 on a 1-3 scale, an event logged against a track_id that does
not exist.

SPINE is deliberately tiny. These test the rules, not the discography.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.key_changes import (
    expected_semitones,
    is_valid_timestamp,
    parse_key,
    validate_events,
)

SPINE: set[str] = {"inhuman-rampage-1-01", "inhuman-rampage-1-02"}


def event(**overrides: object) -> dict[str, object]:
    """A valid event row, with fields overridden per test."""
    row: dict[str, object] = {
        "track_id": "inhuman-rampage-1-01",
        "event_no": "1",
        "timestamp_mm_ss": "3:47",
        "from_key": "E",
        "to_key": "F",
        "semitones": "1",
        "type": "truck_driver",
        "confidence": "3",
        "notes": "",
    }
    row.update(overrides)
    return row


def covered(track_id: str = "inhuman-rampage-1-01", annotated: str = "yes") -> dict[str, object]:
    return {"track_id": track_id, "annotated": annotated, "listened_at": "2026-09-04"}


# --- key parsing ----------------------------------------------------------

@pytest.mark.parametrize("text,pitch,minor", [
    ("C", 0, False), ("Am", 9, True), ("F#", 6, False),
    ("Bb", 10, False), ("C#m", 1, True), ("Ebm", 3, True),
    ("Cb", 11, False),   # wraps below C
    ("B#", 0, False),    # wraps above B
])
def test_parse_key_accepts_the_documented_format(text, pitch, minor):
    assert parse_key(text) == (pitch, minor)


@pytest.mark.parametrize("text", [
    "H", "c", "C major", "Bbmin", "F##", "", "  ", "Cmaj", "8",
])
def test_parse_key_rejects_everything_else(text):
    # Lowercase and spelled-out modes are rejected on purpose: allowing them
    # means "c" and "C" become two categories nobody notices until a groupby.
    assert parse_key(text) is None


def test_enharmonics_share_a_pitch_class():
    assert parse_key("C#")[0] == parse_key("Db")[0]


def test_expected_semitones_is_the_ascending_interval():
    assert expected_semitones("E", "F") == 1
    assert expected_semitones("E", "D") == 10      # descending, spelled ascending
    assert expected_semitones("C", "Cm") == 0      # borrowed: tonic unchanged
    assert expected_semitones("C", "H") is None


@pytest.mark.parametrize("text,ok", [
    ("3:47", True), ("0:00", True), ("12:05", True),
    ("3:60", False), ("347", False), ("3:7", False), ("", False),
])
def test_timestamp_format(text, ok):
    assert is_valid_timestamp(text) is ok


# --- the empty case, which is the normal one for months -------------------

def test_empty_sheets_produce_nothing():
    errors, warnings = validate_events([], [], SPINE)
    assert errors == []
    assert warnings == []


def test_annotated_track_with_no_events_is_valid():
    # "I listened to the whole thing and it never changes key" is a finding,
    # not a gap, and must not be nagged about.
    errors, warnings = validate_events([], [covered()], SPINE)
    assert errors == []
    assert warnings == []


def test_a_clean_event_passes():
    errors, warnings = validate_events([event()], [covered()], SPINE)
    assert errors == []
    assert warnings == []


# --- errors: these stop the build -----------------------------------------

def test_unknown_track_id_in_events_is_an_error():
    errors, _ = validate_events([event(track_id="not-a-track-9-99")], [], SPINE)
    assert any("not in the spine" in e for e in errors)


def test_unknown_track_id_in_coverage_is_an_error():
    errors, _ = validate_events([], [covered("typo-1-01")], SPINE)
    assert any("not in the spine" in e for e in errors)


def test_duplicate_coverage_row_is_an_error():
    errors, _ = validate_events([], [covered(), covered()], SPINE)
    assert any("duplicate row" in e for e in errors)


@pytest.mark.parametrize("field,value,fragment", [
    ("from_key", "H", "not a key name"),
    ("to_key", "c#", "not a key name"),
    ("timestamp_mm_ss", "3m47s", "timestamp_mm_ss"),
    ("type", "keychange", "is not one of"),
    ("confidence", "5", "confidence must be"),
    ("confidence", "", "confidence must be"),
    ("semitones", "up a bit", "semitones must be an integer"),
    ("semitones", "40", "outside"),
    ("event_no", "0", "positive integer"),
])
def test_bad_values_are_errors(field, value, fragment):
    errors, _ = validate_events([event(**{field: value})], [covered()], SPINE)
    assert any(fragment in e for e in errors), errors


def test_duplicate_event_no_within_a_track_is_an_error():
    errors, _ = validate_events(
        [event(event_no="1"), event(event_no="1", timestamp_mm_ss="4:10")],
        [covered()], SPINE,
    )
    assert any("duplicate event_no" in e for e in errors)


# --- warnings: only the annotator can settle these ------------------------

def test_semitones_contradicting_the_keys_is_a_warning():
    # E -> F is one semitone. Writing 2 means one of the three fields is wrong,
    # and no automated rule can say which — hence a warning, not an error.
    _, warnings = validate_events([event(semitones="2")], [covered()], SPINE)
    assert any("one of the three is a typo" in w for w in warnings)


def test_descending_semitones_are_accepted():
    # -2 and +10 describe the same pair of keys; comparing mod 12 accepts both.
    errors, warnings = validate_events(
        [event(from_key="E", to_key="D", semitones="-2")], [covered()], SPINE,
    )
    assert errors == []
    assert warnings == []


def test_modal_change_of_zero_semitones_is_accepted():
    errors, warnings = validate_events(
        [event(from_key="C", to_key="Cm", semitones="0", type="borrowed")],
        [covered()], SPINE,
    )
    assert errors == []
    assert warnings == []


def test_events_without_a_coverage_row_warn():
    errors, warnings = validate_events([event()], [], SPINE)
    assert errors == []
    assert any("not marked annotated" in w for w in warnings)


def test_gap_in_event_numbering_warns():
    _, warnings = validate_events(
        [event(event_no="1"), event(event_no="3", timestamp_mm_ss="4:10")],
        [covered()], SPINE,
    )
    assert any("no gaps" in w for w in warnings)
