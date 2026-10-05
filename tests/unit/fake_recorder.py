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
            guilds=[{"id": "10", "name": "G", "channels": [{"id": "20", "name": "voice"}]}],
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
    # record_ok
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
