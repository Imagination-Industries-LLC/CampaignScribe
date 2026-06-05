"""Per-campaign voice fingerprints: running-mean centroids, local-only.

Tk-free, pure numpy. Persists to <campaign_dir>/fingerprints.npz (float32
raw running-mean vectors) + a fingerprints.json sidecar (per-person count +
updated_at). Reuses app.core.library for the per-campaign folder. Never
uploaded; never written into the versioned speakers.json docs.
"""

from __future__ import annotations

import json
import os
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from app.core import library

_NPZ = "fingerprints.npz"
_JSON = "fingerprints.json"

# ---------------------------------------------------------------------------
# Session-embedding stash (in-memory, Task 4)
# Holds per-cluster embeddings extracted during a transcribe run until the
# ② Review screen reads them. Never persisted; cleared by pop_session_embeddings.
# ---------------------------------------------------------------------------

_SESSION_EMB: dict[int, dict] = {}


def stash_session_embeddings(session_id: int, embeddings: dict) -> None:
    """Hold this run's {cluster: embedding} for a session until the ② Review screen reads it."""
    _SESSION_EMB[int(session_id)] = embeddings


def peek_session_embeddings(session_id: int) -> dict | None:
    """Read without removing (② reads on open; may re-open)."""
    return _SESSION_EMB.get(int(session_id))


def pop_session_embeddings(session_id: int) -> dict | None:
    """Remove and return the stashed embeddings, or None if absent."""
    return _SESSION_EMB.pop(int(session_id), None)


def _paths(slug: str) -> tuple[Path, Path]:
    d = library._campaign_dir(slug)
    return d / _NPZ, d / _JSON


def _normalize(v: np.ndarray) -> np.ndarray:
    v = np.asarray(v, dtype="float32")
    n = float(np.linalg.norm(v))
    return v / n if n > 1e-9 else v


def load(slug: str) -> dict[str, dict[str, Any]]:
    """Return {person: {"centroid": float32[D] (L2-normalized), "raw": float32[D],
    "count": int, "updated_at": iso}}. Empty dict when no store exists."""
    npz_path, json_path = _paths(slug)
    if not npz_path.exists():
        return {}
    meta: dict[str, Any] = {}
    if json_path.exists():
        try:
            meta = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
    out: dict[str, dict[str, Any]] = {}
    try:
        npz_data = np.load(npz_path)
    except (OSError, ValueError, zipfile.BadZipFile):
        return {}
    with npz_data:
        for person in npz_data.files:
            raw = np.asarray(npz_data[person], dtype="float32")
            m = meta.get(person, {})
            out[person] = {
                "centroid": _normalize(raw),
                "raw": raw,
                "count": int(m.get("count", 1)),
                "updated_at": m.get("updated_at", ""),
            }
    return out


def _save(slug: str, store: dict[str, dict[str, Any]]) -> None:
    npz_path, json_path = _paths(slug)
    npz_path.parent.mkdir(parents=True, exist_ok=True)
    arrays = {p: np.asarray(rec["raw"], dtype="float32") for p, rec in store.items()}
    npz_tmp = npz_path.with_name("fingerprints.tmp.npz")
    np.savez(npz_tmp, **arrays)
    os.replace(npz_tmp, npz_path)
    meta = {
        p: {"count": int(rec["count"]), "updated_at": rec["updated_at"]} for p, rec in store.items()
    }
    json_tmp = json_path.with_suffix(".json.tmp")
    json_tmp.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    os.replace(json_tmp, json_path)


def update(slug: str, person: str, embedding: np.ndarray) -> None:
    """Incrementally fold one cluster embedding into person's running-mean
    centroid: new_raw = (old_raw*count + emb) / (count+1). Stored normalized
    for cosine via get_centroids."""
    emb = np.asarray(embedding, dtype="float32")
    store = load(slug)
    rec = store.get(person)
    if rec is None:
        new_raw, new_count = emb.copy(), 1
    else:
        count = int(rec["count"])
        new_raw = (rec["raw"] * count + emb) / (count + 1)
        new_count = count + 1
    store[person] = {
        "centroid": _normalize(new_raw),
        "raw": new_raw,
        "count": new_count,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }
    _save(slug, store)


def get_centroids(slug: str) -> dict[str, np.ndarray]:
    """{person: L2-normalized centroid vector} for cosine matching."""
    return {p: rec["centroid"] for p, rec in load(slug).items()}


def match(
    slug: str,
    cluster_embeddings: dict[str, np.ndarray],
    threshold: float,
) -> dict[str, tuple[str | None, float]]:
    """Cosine each cluster vs each person centroid. Returns
    {cluster: (best_person, score)}; (None, best_score) when below threshold
    or no fingerprints exist (best_score 0.0 for an empty store)."""
    centroids = get_centroids(slug)
    out: dict[str, tuple[str | None, float]] = {}
    for cid, emb in cluster_embeddings.items():
        q = _normalize(emb)
        best_person: str | None = None
        best_score = 0.0
        for person, cen in centroids.items():
            score = float(q @ cen)  # both L2-normalized -> cosine
            if score > best_score:
                best_person, best_score = person, score
        out[cid] = (best_person, best_score) if best_score >= threshold else (None, best_score)
    return out
