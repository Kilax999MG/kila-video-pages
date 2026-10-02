"""Resolve the newest upload from a validated YouTube channel URL."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time

from resolve_job import validate_youtube_url


def latest_video_id(url: str, attempts: int = 3, runner=subprocess.run) -> str:
    validate_youtube_url(url, channel=True)
    command = [
        "yt-dlp", "--flat-playlist", "--playlist-items", "1", "--no-warnings",
        "--print", "%(id)s", url,
    ]
    last_error = "No video was returned by YouTube"
    for attempt in range(attempts):
        try:
            result = runner(command, capture_output=True, text=True, check=True, timeout=180)
            video_id = result.stdout.strip().splitlines()[0]
            if re.fullmatch(r"[A-Za-z0-9_-]{6,20}", video_id):
                return video_id
            last_error = "yt-dlp returned an invalid video ID"
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError, IndexError) as error:
            last_error = str(error)[:240]
        if attempt + 1 < attempts:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Could not resolve latest channel upload: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("channel_url")
    args = parser.parse_args()
    print(latest_video_id(args.channel_url))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1)