"""voiceprints store: running-mean centroid, persistence, multi-person."""

from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")

from app.core import library, voiceprints  # noqa: E402


def _slug() -> str:
    return library.create_campaign("Strahd")


def test_empty_load_returns_empty_dict():
    slug = _slug()
    assert voiceprints.load(slug) == {}
    assert voiceprints.get_centroids(slug) == {}


def test_update_first_sample_is_the_vector_normalized():
    slug = _slug()
    voiceprints.update(slug, "Mike", np.array([3.0, 4.0], dtype="float32"))  # norm 5
    cen = voiceprints.get_centroids(slug)["Mike"]
    assert np.allclose(np.linalg.norm(cen), 1.0, atol=1e-5)
    assert np.allclose(cen, np.array([0.6, 0.8]), atol=1e-5)


def test_update_running_mean_then_normalize():
    slug = _slug()
    # running mean is computed on the RAW vectors: new = (old*count + emb)/(count+1)
    voiceprints.update(slug, "Mike", np.array([1.0, 0.0], dtype="float32"))
    voiceprints.update(slug, "Mike", np.array([0.0, 1.0], dtype="float32"))
    cen = voiceprints.get_centroids(slug)["Mike"]
    # raw mean (0.5, 0.5) -> normalized (0.7071, 0.7071)
    assert np.allclose(cen, np.array([0.70710678, 0.70710678]), atol=1e-5)
    assert voiceprints.load(slug)["Mike"]["count"] == 2


def test_persistence_round_trip_across_calls():
    slug = _slug()
    voiceprints.update(slug, "Mike", np.array([1.0, 2.0, 3.0], dtype="float32"))
    reloaded = voiceprints.load(slug)  # fresh read from disk
    assert "Mike" in reloaded
    assert reloaded["Mike"]["count"] == 1
    assert reloaded["Mike"]["centroid"].shape == (3,)


def test_multiple_people_kept_separate():
    slug = _slug()
    voiceprints.update(slug, "Mike", np.array([1.0, 0.0], dtype="float32"))
    voiceprints.update(slug, "Jo", np.array([0.0, 1.0], dtype="float32"))
    cen = voiceprints.get_centroids(slug)
    assert set(cen) == {"Mike", "Jo"}
    assert np.allclose(cen["Mike"], [1.0, 0.0], atol=1e-5)


# ---------------------------------------------------------------------------
# Task 2 — matcher
# ---------------------------------------------------------------------------


def test_match_picks_the_right_person():
    slug = _slug()
    voiceprints.update(slug, "Mike", np.array([1.0, 0.0], dtype="float32"))
    voiceprints.update(slug, "Jo", np.array([0.0, 1.0], dtype="float32"))
    clusters = {"SPEAKER_00": np.array([0.9, 0.1], dtype="float32")}
    res = voiceprints.match(slug, clusters, threshold=0.70)
    person, score = res["SPEAKER_00"]
    assert person == "Mike"
    assert score >= 0.70


def test_match_below_threshold_returns_none():
    slug = _slug()
    voiceprints.update(slug, "Mike", np.array([1.0, 0.0], dtype="float32"))
    clusters = {"SPEAKER_00": np.array([0.0, 1.0], dtype="float32")}  # orthogonal -> cos 0
    person, score = voiceprints.match(slug, clusters, threshold=0.70)["SPEAKER_00"]
    assert person is None
    assert score < 0.70


def test_match_empty_store_all_none():
    slug = _slug()
    clusters = {"SPEAKER_00": np.array([1.0, 0.0], dtype="float32")}
    person, score = voiceprints.match(slug, clusters, threshold=0.70)["SPEAKER_00"]
    assert person is None


def test_match_ranks_among_multiple_people():
    slug = _slug()
    voiceprints.update(slug, "Mike", np.array([1.0, 0.0, 0.0], dtype="float32"))
    voiceprints.update(slug, "Jo", np.array([0.0, 1.0, 0.0], dtype="float32"))
    voiceprints.update(slug, "Sam", np.array([0.0, 0.0, 1.0], dtype="float32"))
    clusters = {"A": np.array([0.1, 0.95, 0.1], dtype="float32")}
    assert voiceprints.match(slug, clusters, threshold=0.70)["A"][0] == "Jo"


def test_config_has_voice_match_keys():
    from app import config

    assert config.DEFAULT_CONFIG.get("voice_match_enabled") is True
    assert 0.0 < config.DEFAULT_CONFIG.get("voice_match_threshold") < 1.0


def test_session_embedding_stash_peek_pop():
    from app.core import voiceprints

    vec = np.array([1.0, 2.0], dtype="float32")
    voiceprints.stash_session_embeddings(101, {"SPEAKER_00": vec})
    assert voiceprints.peek_session_embeddings(101)["SPEAKER_00"].tolist() == [1.0, 2.0]
    # peek does not remove
    assert voiceprints.peek_session_embeddings(101) is not None
    popped = voiceprints.pop_session_embeddings(101)
    assert "SPEAKER_00" in popped
    assert voiceprints.peek_session_embeddings(101) is None
    assert voiceprints.pop_session_embeddings(999) is None  # missing -> None


def test_load_corrupt_npz_returns_empty(tmp_path):
    slug = library.create_campaign("Strahd")
    voiceprints.update(slug, "Mike", np.array([1.0, 0.0, 0.0], dtype="float32"))
    # corrupt the npz on disk
    npz = library._campaign_dir(slug) / "fingerprints.npz"
    npz.write_bytes(b"not a real npz")
    # load must degrade gracefully, not crash
    assert voiceprints.load(slug) == {}
    assert voiceprints.get_centroids(slug) == {}
