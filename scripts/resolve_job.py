"""Validate machine-readable GitHub Issue and workflow-dispatch jobs."""

from __future__ import annotations

import json
import re
import sys
from urllib.parse import parse_qsl, urlparse


TRUSTED_ASSOCIATIONS = {"OWNER", "MEMBER", "COLLABORATOR"}
STYLES = {"default", "hormozi", "mrbeast", "podcast"}
MIN_DURATIONS = {15, 20, 30}
MAX_DURATIONS = {30, 45, 60}
CLIP_TITLE = "[SHORT JOB] Auto clip"
CHANNEL_TITLE = "[CHANNEL WATCH] Configure"
FIELDS = {
    "clip": {
        "mode", "url", "style", "max_clips", "min_duration", "max_duration",
        "tighten", "loudnorm", "face_reframe", "complete_thought",
    },
    "channel": {
        "mode", "url", "style", "max_clips", "min_duration", "max_duration",
        "enabled",
    },
}


class JobError(ValueError):
    """An untrusted or malformed job request."""


def validate_youtube_url(value: str, channel: bool = False) -> str:
    if not isinstance(value, str) or len(value) > 500:
        raise JobError("url must be a YouTube URL")
    value = value.strip()
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError as exc:
        raise JobError("Malformed YouTube URL") from exc
    if parsed.scheme not in {"https", "http"} or parsed.hostname not in {
        "youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be",
    }:
        raise JobError("Only youtube.com, www.youtube.com, m.youtube.com and youtu.be URLs are allowed")
    if parsed.username or parsed.password or port:
        raise JobError("Credentials and custom ports are not allowed in URLs")
    if parsed.fragment:
        raise JobError("URL fragments are not allowed")
    if channel:
        if parsed.hostname == "youtu.be" or not re.fullmatch(r"/@[^/]+(?:/videos)?/?", parsed.path):
            raise JobError("Channel URL must use the format youtube.com/@channel/videos")
    else:
        video_id = next((value for key, value in parse_qsl(parsed.query) if key == "v"), "")
        is_watch = parsed.path == "/watch" and bool(re.fullmatch(r"[A-Za-z0-9_-]{6,20}", video_id))
        is_short = parsed.hostname == "youtu.be" and bool(re.fullmatch(r"/[A-Za-z0-9_-]{6,20}", parsed.path))
        is_embed = bool(re.fullmatch(r"/(?:embed|shorts)/[A-Za-z0-9_-]{6,20}/?", parsed.path))
        if not (is_watch or is_short or is_embed):
            raise JobError("URL must point to a public YouTube video")
    return value


def parse_bool(value: str, name: str) -> bool:
    if value not in {"true", "false"}:
        raise JobError(f"{name} must be true or false")
    return value == "true"


def validate_job(fields: dict[str, str], expected_mode: str) -> dict:
    if set(fields) != FIELDS[expected_mode]:
        missing = sorted(FIELDS[expected_mode] - set(fields))
        unknown = sorted(set(fields) - FIELDS[expected_mode])
        details = []
        if missing:
            details.append("missing fields: " + ", ".join(missing))
        if unknown:
            details.append("unknown fields: " + ", ".join(unknown))
        raise JobError("Invalid job fields (" + "; ".join(details) + ")")
    if fields["mode"] != expected_mode:
        raise JobError("mode does not match the Issue title")
    style = fields["style"]
    if style not in STYLES:
        raise JobError("style must be default, hormozi, mrbeast or podcast")
    try:
        max_clips = int(fields["max_clips"])
        min_duration = int(fields["min_duration"])
        max_duration = int(fields["max_duration"])
    except (TypeError, ValueError) as exc:
        raise JobError("clip count and durations must be integers") from exc
    if not 1 <= max_clips <= 5:
        raise JobError("max_clips must be between 1 and 5")
    if min_duration not in MIN_DURATIONS or max_duration not in MAX_DURATIONS or min_duration >= max_duration:
        raise JobError("durations must use the supported ranges and minimum must be below maximum")

    job = {
        "mode": expected_mode,
        "url": validate_youtube_url(fields["url"], channel=expected_mode == "channel"),
        "style": style,
        "max_clips": max_clips,
        "min_duration": min_duration,
        "max_duration": max_duration,
    }
    if expected_mode == "clip":
        for name in ("tighten", "loudnorm", "face_reframe", "complete_thought"):
            job[name] = parse_bool(fields[name], name)
    else:
        job["enabled"] = parse_bool(fields["enabled"], "enabled")
    return job


def parse_issue(issue: dict, author_association: str) -> dict:
    if author_association not in TRUSTED_ASSOCIATIONS:
        raise JobError("Only repository owners, members and collaborators may submit processing jobs")
    title = issue.get("title", "")
    if title == CLIP_TITLE:
        mode = "clip"
    elif title == CHANNEL_TITLE:
        mode = "channel"
    else:
        raise JobError("Issue title is not a supported Shorts job")
    fields: dict[str, str] = {}
    for line in (issue.get("body") or "").splitlines():
        if not line.strip():
            continue
        key, separator, value = line.partition("=")
        if not separator or not re.fullmatch(r"[a-z_]+", key) or key in fields:
            raise JobError("Issue body must contain one key=value field per line")
        fields[key] = value.strip()
    return validate_job(fields, mode)


def parse_dispatch(inputs: dict[str, str]) -> dict:
    def normalized_boolean(name: str, default: str) -> str:
        value = inputs.get(name, default)
        return str(value).lower() if isinstance(value, bool) else value

    fields = {
        "mode": "clip",
        "url": inputs.get("url", ""),
        "style": inputs.get("style", "default"),
        "max_clips": inputs.get("max_clips", "3"),
        "min_duration": inputs.get("min_duration", "20"),
        "max_duration": inputs.get("max_duration", "60"),
        "tighten": normalized_boolean("tighten", "true"),
        "loudnorm": normalized_boolean("loudnorm", "true"),
        "face_reframe": "true",
        "complete_thought": "true",
    }
    return validate_job(fields, "clip")


def main() -> int:
    event_path = sys.argv[1]
    with open(event_path, encoding="utf-8") as event_file:
        event = json.load(event_file)
    if event.get("issue"):
        job = parse_issue(event["issue"], event["issue"].get("author_association", ""))
    else:
        job = parse_dispatch(event.get("inputs", {}))
    print(json.dumps(job, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (JobError, OSError, json.JSONDecodeError) as error:
        print(f"Invalid Shorts job: {error}", file=sys.stderr)
        raise SystemExit(2)