"""Stand-alone stand-in for recorder.mjs; behaviour chosen by FAKE_MODE. Never prints the token."""

from __future__ import annotations

import json
import os
import sys
import time


def emit(event: str, **fields) -> None:
    print(json.dumps({"event": event, **fields}), flush=True)


def arg(flag: str) -> str | None:
    a = sys.argv
    return a[a.index(flag) + 1] if flag in a and a.index(flag) + 1 < len(a) else None


def main() -> int:
    mode = os.environ.get("FAKE_MODE", "record_ok")
    if mode == "garbage":
        print("not json", flush=True)
        emit("ready")
        return 0
    if mode == "list_ok":
        emit("ready")
        emit(
            "inventory",
            guilds=[{"id": "10", "name": "G", "voice_channels": [{"id": "20", "name": "voice"}]}],
            owner={"id": "5", "name": "mike"},
            owner_voice=None,
            application_id="99",
        )
        return 0
    if mode == "list_error":
        emit("ready")
        emit("error", code="bad_token", message="Invalid token")
        return 1
    if mode == "owner_absent":
        emit("ready")
        emit("error", code="owner_not_in_voice", message="Join a voice channel first")
        return 2
    if mode == "hang":
        emit("ready")
        while True:
            time.sleep(0.2)
    if mode == "flood":
        emit("ready")
        line = json.dumps({"event": "telemetry", "pad": "x" * 1000}) + "\n"
        for _ in range(1500):  # ~1.5 MB each way, far above pipe buffers
            sys.stdout.write(line)
            sys.stderr.write("e" * 1000 + "\n")
        sys.stdout.flush()
        sys.stderr.flush()
        for _ in sys.stdin:
            pass
        emit("stopped", seconds=1)
        return 0
    if mode == "leak_probe":
        outdir = arg("--out") or os.getcwd()
        os.makedirs(outdir, exist_ok=True)
        with open(os.path.join(outdir, "env_seen.txt"), "w", encoding="utf-8") as f:
            f.write(os.environ.get("DISCORD_TOKEN") or "")
    # record_ok / leak_probe
    out = arg("--out") or os.getcwd()
    os.makedirs(out, exist_ok=True)
    emit("ready")
    emit("joined", channel="voice")
    emit("user", id="1", name="Mi/ke")
    emit("speaking", id="1", speaking=True)
    with open(os.path.join(out, "1.pcm"), "wb") as f:
        f.write(b"\x00\x00" * 48000)
    with open(os.path.join(out, "tracks.json"), "w", encoding="utf-8") as f:
        json.dump({"1": "Mi/ke"}, f)
    for line in sys.stdin:  # ends on EOF too
        try:
            if json.loads(line).get("cmd") == "stop":
                break
        except ValueError:
            pass
    emit("stopped", seconds=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
