"""Run validated Shorts jobs and publish their output without shell interpolation."""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from latest_video import latest_video_id
from resolve_job import parse_dispatch, parse_issue


ROOT = Path(__file__).resolve().parents[1]
def github_request(method: str, path: str, payload: dict | None = None):
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is unavailable; workflow permissions are missing")
    request = urllib.request.Request(
        "https://api.github.com" + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "kila-shorts-actions",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read()) if response.status != 204 else None
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return None
        raise RuntimeError(f"GitHub API {method} failed ({error.code}): {error.read().decode(errors='replace')[:300]}") from error


def repo_name() -> str:
    return os.environ["GITHUB_REPOSITORY"]


def update_repository_file(path: str, text: str, message: str) -> None:
    """Update a repository file with optimistic SHA checks and bounded retries."""
    encoded_path = urllib.parse.quote(path, safe="/")
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    for attempt in range(4):
        existing = github_request(
            "GET", f"/repos/{repo_name()}/contents/{encoded_path}?ref={urllib.parse.quote(branch)}"
        )
        payload = {
            "message": message,
            "content": base64.b64encode(text.encode()).decode(),
            "branch": branch,
        }
        if existing:
            payload["sha"] = existing["sha"]
        try:
            github_request("PUT", f"/repos/{repo_name()}/contents/{encoded_path}", payload)
            return
        except RuntimeError as error:
            if attempt == 3 or not any(code in str(error) for code in ("409", "422")):
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError(f"Could not update {path} after concurrent-write retries")


def read_repository_file(path: str) -> str:
    local = ROOT / path
    if local.exists():
        return local.read_text(encoding="utf-8")
    remote = github_request("GET", f"/repos/{repo_name()}/contents/{path}")
    if not remote:
        return ""
    return base64.b64decode(remote["content"]).decode("utf-8")


def issue_comment(issue_number: int, message: str) -> None:
    github_request("POST", f"/repos/{repo_name()}/issues/{issue_number}/comments", {"body": message})


def close_issue(issue_number: int) -> None:
    github_request("PATCH", f"/repos/{repo_name()}/issues/{issue_number}", {"state": "closed"})


def create_release(output_dir: Path) -> str:
    assets = sorted(output_dir.glob("*"))
    videos = [asset for asset in assets if asset.suffix == ".mp4"]
    if not videos:
        raise RuntimeError("Chopify completed without producing any MP4 clips")
    tag = f"shorts-{os.environ['GITHUB_RUN_ID']}-{os.environ['GITHUB_RUN_ATTEMPT']}"
    command = [
        "gh", "release", "create", tag, *[str(path) for path in assets],
        "--repo", repo_name(), "--title", f"Shorts {tag}",
        "--notes", f"Generated Shorts from {len(videos)} clip(s).",
    ]
    environment = os.environ.copy()
    environment["GH_TOKEN"] = os.environ["GITHUB_TOKEN"]
    subprocess.run(command, check=True, env=environment)
    return f"https://github.com/{repo_name()}/releases/tag/{tag}"


def normalize_clip_names(output_dir: Path) -> list[Path]:
    generated = sorted(output_dir.glob("*.mp4"), key=lambda path: path.stat().st_mtime_ns)
    for index, source in enumerate(generated, 1):
        stem = source.stem
        for suffix in (".mp4", ".png", ".meta.json"):
            sidecar = output_dir / f"{stem}{suffix}"
            if sidecar.exists():
                sidecar.rename(output_dir / f"clip_{index}{suffix}")
    return [output_dir / f"clip_{index}.mp4" for index in range(1, len(generated) + 1)]



def youtube_access_preflight(url: str) -> None:
    """Verify yt-dlp can resolve the requested video before expensive transcription/rendering."""
    command = [
        sys.executable, "-m", "yt_dlp",
        "--simulate", "--no-playlist",
        "--print", "%(id)s",
        url,
    ]
    result = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=240,
        check=False,
        env=os.environ.copy(),
    )
    output = result.stdout or ""
    if output:
        print("yt-dlp preflight:", flush=True)
        print(output[-6000:], flush=True)
    if result.returncode == 0:
        return

    lowered = output.lower()
    if "sign in to confirm you're not a bot" in lowered or "sign in to confirm you’re not a bot" in lowered:
        reason = (
            "YouTube bot check blocked this GitHub runner even after the PO-token provider "
            "was enabled. Re-running may obtain a different runner IP; optionally configure the "
            "repository YOUTUBE_COOKIES secret with your own Netscape-format YouTube cookies."
        )
    elif "http error 403" in lowered or "403 forbidden" in lowered:
        reason = (
            "YouTube returned HTTP 403 after the PO-token flow. This normally means the current "
            "runner IP/session is still being rejected by YouTube."
        )
    elif "http error 429" in lowered or "too many requests" in lowered:
        reason = "YouTube rate-limited the GitHub runner (HTTP 429). Try a later run."
    else:
        tail = " ".join(line.strip() for line in output.splitlines()[-8:] if line.strip())[:900]
        reason = f"yt-dlp could not resolve the video: {tail or 'unknown extraction error'}"
    raise RuntimeError(reason)

def render(job: dict) -> str:
    chopify_dir = Path(os.environ["CHOPIFY_DIR"])
    output_dir = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "kila-shorts-output"
    work_dir = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "kila-shorts-work"
    shutil.rmtree(output_dir, ignore_errors=True)
    shutil.rmtree(work_dir, ignore_errors=True)
    output_dir.mkdir(parents=True)
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "patch_chopify.py"), str(chopify_dir)],
        check=True,
    )
    youtube_access_preflight(job["url"])
    command = [
        sys.executable, str(chopify_dir / "chopify.py"), job["url"],
        "--workdir", str(work_dir), "--out", str(output_dir),
        "--aspect", "9:16", "--style", job["style"],
        "--max-clips", str(job["max_clips"]),
        "--min-len", str(job["min_duration"]),
        "--max-len", str(job["max_duration"]),
        "--whisper-model", "small",
    ]
    if job.get("tighten", True):
        command.append("--tighten")
    if job.get("loudnorm", True):
        command.append("--loudnorm")
    if not job.get("face_reframe", True):
        command.append("--no-face-reframe")
    if not job.get("complete_thought", True):
        command.append("--allow-incomplete-thoughts")
    subprocess.run(command, check=True, cwd=chopify_dir, env=os.environ.copy())

    generated = normalize_clip_names(output_dir)
    if not generated:
        raise RuntimeError("Chopify returned successfully but created no MP4 output")
    release_url = create_release(output_dir)
    if job["mode"] == "channel" and job.get("video_id"):
        update_repository_file("state/last_video.txt", job["video_id"] + "\n", "Record processed channel upload")
    return release_url


def fail_issue(issue_number: int | None, error: Exception) -> None:
    if not issue_number:
        return
    detail = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", " ", str(error))
    detail = detail.replace("```", "'''")[:700]
    issue_comment(issue_number, f"Render failed: {detail}")


def process_event() -> int:
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
    issue = event.get("issue") if event_name == "issues" else None
    issue_number = issue.get("number") if issue else None

    try:
        if event_name == "issues":
            association = issue.get("author_association", "")
            if association not in {"OWNER", "MEMBER", "COLLABORATOR"}:
                print(f"Ignoring Issue from untrusted author association: {association}")
                return 0
            job = parse_issue(issue, association)
            if job["mode"] == "channel":
                config = {key: value for key, value in job.items() if key != "mode"}
                update_repository_file("state/channel.json", json.dumps(config, indent=2) + "\n", "Configure channel auto-shorts")
                issue_comment(issue_number, "Channel configuration saved. Scheduled checks run every six hours.")
                close_issue(issue_number)
                return 0
        elif event_name == "workflow_dispatch":
            job = parse_dispatch(event.get("inputs", {}))
        elif event_name == "schedule":
            raw_config = read_repository_file("state/channel.json")
            if not raw_config.strip():
                print("No channel configuration; nothing to do.")
                return 0
            config = json.loads(raw_config)
            if not config.get("enabled"):
                print("Channel auto mode is disabled; nothing to do.")
                return 0
            video_id = latest_video_id(config["url"])
            previous_id = read_repository_file("state/last_video.txt").strip()
            if video_id == previous_id:
                print(f"Latest video {video_id} was already processed.")
                return 0
            job = {**config, "mode": "channel", "video_id": video_id,
                   "url": f"https://www.youtube.com/watch?v={video_id}"}
        else:
            print(f"No handler for event {event_name}; exiting successfully.")
            return 0

        release_url = render(job)
    except Exception as error:
        fail_issue(issue_number, error)
        raise
    if issue_number:
        issue_comment(issue_number, f"Render finished. Your Shorts are ready.\n\n{release_url}")
        close_issue(issue_number)
    print(f"Published Shorts release: {release_url}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(process_event())
    except Exception as error:
        print(f"Shorts job failed: {error}", file=sys.stderr)
        raise SystemExit(1)