# tests/unit/test_transcriber_count_window.py
from app.core import transcriber as tr


def test_count_window_exact_from_num_speakers():
    assert tr.speaker_count_window(num_speakers=5) == {"min_speakers": 5, "max_speakers": 5}


def test_count_window_explicit_range_wins():
    assert tr.speaker_count_window(num_speakers=5, min_speakers=4, max_speakers=6) == {
        "min_speakers": 4,
        "max_speakers": 6,
    }


def test_count_window_unconstrained_is_empty():
    assert tr.speaker_count_window() == {}
    assert tr.speaker_count_window(num_speakers=0) == {}


def test_count_window_floors_at_one():
    assert tr.speaker_count_window(min_speakers=0, max_speakers=2) == {"max_speakers": 2}


def test_run_kwargs_at_least_n_window():
    # expected_count drives "at least N, room for one more"
    assert tr.diarization_run_kwargs(5, 9) == {"min_speakers": 5, "max_speakers": 6}


def test_run_kwargs_falls_back_to_exact_count():
    assert tr.diarization_run_kwargs(0, 7) == {"num_speakers": 7}


def test_run_kwargs_floor_at_one():
    assert tr.diarization_run_kwargs(1, 5) == {"min_speakers": 1, "max_speakers": 2}
