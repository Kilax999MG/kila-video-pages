import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from resolve_job import JobError, parse_dispatch, parse_issue
from patch_chopify import patch_downloader
import run_workflow


def clip_issue(**overrides):
    values = {
        "mode": "clip",
        "url": "https://www.youtube.com/watch?v=abcdefghijk",
        "style": "hormozi",
        "max_clips": "3",
        "min_duration": "20",
        "max_duration": "60",
        "tighten": "true",
        "loudnorm": "true",
        "face_reframe": "true",
        "complete_thought": "true",
    }
    values.update(overrides)
    return {"title": "[SHORT JOB] Auto clip", "body": "\n".join(f"{key}={value}" for key, value in values.items())}


class IssueValidationTests(unittest.TestCase):
    def test_valid_owner_job(self):
        job = parse_issue(clip_issue(), "OWNER")
        self.assertEqual(job["max_clips"], 3)
        self.assertTrue(job["complete_thought"])

    def test_external_author_is_rejected(self):
        with self.assertRaisesRegex(JobError, "Only repository owners"):
            parse_issue(clip_issue(), "CONTRIBUTOR")

    def test_non_youtube_host_is_rejected(self):
        with self.assertRaisesRegex(JobError, "Only youtube.com"):
            parse_issue(clip_issue(url="https://example.com/watch?v=abcdefghijk"), "OWNER")

    def test_invalid_caption_style_is_rejected(self):
        with self.assertRaisesRegex(JobError, "style must be"):
            parse_issue(clip_issue(style="unsafe"), "OWNER")

    def test_numeric_bounds_are_enforced(self):
        for values in ({"max_clips": "6"}, {"max_clips": "0"}, {"min_duration": "14"}, {"max_duration": "90"}, {"min_duration": "60"}):
            with self.subTest(values=values), self.assertRaises(JobError):
                parse_issue(clip_issue(**values), "OWNER")

    def test_duplicate_or_unknown_fields_are_rejected(self):
        issue = clip_issue()
        issue["body"] += "\nurl=https://youtu.be/abcdefghijk"
        with self.assertRaisesRegex(JobError, "one key=value"):
            parse_issue(issue, "OWNER")

    def test_dispatch_accepts_boolean_json_inputs(self):
        job = parse_dispatch({
            "url": "https://youtu.be/abcdefghijk",
            "style": "default",
            "max_clips": "2",
            "min_duration": "15",
            "max_duration": "30",
            "tighten": False,
            "loudnorm": True,
        })
        self.assertFalse(job["tighten"])
        self.assertTrue(job["loudnorm"])

    def test_channel_configuration_accepts_channel_videos_url(self):
        issue = {
            "title": "[CHANNEL WATCH] Configure",
            "body": "mode=channel\nurl=https://youtube.com/@example/videos\n"
                    "style=podcast\nmax_clips=2\nmin_duration=15\n"
                    "max_duration=45\nenabled=false",
        }
        job = parse_issue(issue, "MEMBER")
        self.assertFalse(job["enabled"])
        self.assertEqual(job["mode"], "channel")


class ScheduledJobTests(unittest.TestCase):
    def run_schedule(self, file_contents):
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8") as event_file:
            json.dump({}, event_file)
            event_file.flush()
            with patch.dict(os.environ, {"GITHUB_EVENT_NAME": "schedule", "GITHUB_EVENT_PATH": event_file.name}):
                return run_workflow.process_event()

    def test_missing_channel_configuration_exits_successfully(self):
        with patch.object(run_workflow, "read_repository_file", return_value=""):
            self.assertEqual(self.run_schedule(""), 0)

    def test_disabled_channel_configuration_exits_successfully(self):
        config = json.dumps({"enabled": False})
        with patch.object(run_workflow, "read_repository_file", return_value=config):
            self.assertEqual(self.run_schedule(config), 0)

    def test_duplicate_channel_video_exits_successfully(self):
        config = json.dumps({"url": "https://www.youtube.com/@example/videos", "enabled": True})
        with patch.object(run_workflow, "read_repository_file", side_effect=[config, "abcdefghijk\n"]), patch.object(
            run_workflow, "latest_video_id", return_value="abcdefghijk"
        ), patch.object(run_workflow, "render") as render:
            self.assertEqual(self.run_schedule(config), 0)
            render.assert_not_called()


class OutputTests(unittest.TestCase):
    def test_outputs_and_sidecars_receive_clip_names(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            for name in ("great-hook.mp4", "great-hook.png", "great-hook.meta.json"):
                (output / name).write_text("fixture", encoding="utf-8")
            clips = run_workflow.normalize_clip_names(output)
            self.assertEqual([clip.name for clip in clips], ["clip_1.mp4"])
            self.assertTrue((output / "clip_1.png").exists())
            self.assertTrue((output / "clip_1.meta.json").exists())


class ChopifyPatchTests(unittest.TestCase):
    def test_downloader_uses_optional_cookie_file_without_embedding_cookie_data(self):
        with tempfile.TemporaryDirectory() as directory:
            downloader = Path(directory) / "download_and_transcribe.py"
            downloader.write_text(
                'import sys\n'
                'cmd = [\n'
                '        "--no-playlist",\n'
                ']\n',
                encoding="utf-8",
            )

            patch_downloader(downloader)
            patched = downloader.read_text(encoding="utf-8")

            compile(patched, str(downloader), "exec")
            self.assertIn('"--cookies", os.environ["YOUTUBE_COOKIES_FILE"]', patched)
            self.assertIn('os.environ.get("YOUTUBE_COOKIES_FILE")', patched)
            self.assertNotIn("cookie-content", patched)


if __name__ == "__main__":
    unittest.main()