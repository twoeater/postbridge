from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "ntfy-publisher.py"
spec = importlib.util.spec_from_file_location("postbridge_ntfy_queue", SCRIPT)
ntfy = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(ntfy)


class NtfyQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.old_state_file = ntfy.STATE_FILE
        self.old_retry_file = ntfy.RETRY_STATE_FILE
        self.old_dead_file = ntfy.DEAD_LETTER_FILE
        self.old_max_retries = ntfy.MAX_EVENT_RETRIES
        ntfy.STATE_FILE = root / "cursor"
        ntfy.RETRY_STATE_FILE = root / "retry.json"
        ntfy.DEAD_LETTER_FILE = root / "dead-letter.jsonl"
        ntfy.MAX_EVENT_RETRIES = 2

    def tearDown(self):
        ntfy.STATE_FILE = self.old_state_file
        ntfy.RETRY_STATE_FILE = self.old_retry_file
        ntfy.DEAD_LETTER_FILE = self.old_dead_file
        ntfy.MAX_EVENT_RETRIES = self.old_max_retries
        self.tmp.cleanup()

    def read_dead_letters(self):
        if not ntfy.DEAD_LETTER_FILE.exists():
            return []
        return [json.loads(line) for line in ntfy.DEAD_LETTER_FILE.read_text().splitlines() if line]

    def test_option_like_title_is_passed_as_one_argparse_value(self):
        completed = subprocess.CompletedProcess([], 0, stdout="published", stderr="")
        with patch.object(ntfy.subprocess, "run", return_value=completed) as run:
            ntfy.publish_event({"title": "--slug", "message": "body"})
        argv = run.call_args.args[0]
        self.assertIn("--title=--slug", argv)
        self.assertNotIn("--title", argv)

    def test_permanent_message_is_dead_lettered_without_retry(self):
        event = {"id": "bad1", "event": "message", "message": "body without title"}
        self.assertTrue(ntfy.process_message_event(event, "bad1"))
        records = self.read_dead_letters()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["event"]["id"], "bad1")
        self.assertEqual(records[0]["attempts"], 1)
        self.assertFalse(ntfy.RETRY_STATE_FILE.exists())

    def test_unknown_failure_retries_then_dead_letters(self):
        event = {"id": "bad2", "event": "message", "title": "title", "message": "body"}
        with patch.object(ntfy, "publish_event", side_effect=RuntimeError("publish failed")):
            with self.assertRaises(RuntimeError):
                ntfy.process_message_event(event, "bad2")
            retry = ntfy.read_retry_state()
            self.assertEqual(retry["event_id"], "bad2")
            self.assertEqual(retry["attempts"], 1)

            self.assertTrue(ntfy.process_message_event(event, "bad2"))

        records = self.read_dead_letters()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["event"]["id"], "bad2")
        self.assertEqual(records[0]["attempts"], 2)
        self.assertFalse(ntfy.RETRY_STATE_FILE.exists())

    def test_success_clears_retry_state(self):
        event = {"id": "ok1", "event": "message", "title": "ok", "message": "body"}
        ntfy.write_retry_state("ok1", 1, RuntimeError("old failure"))
        with patch.object(ntfy, "publish_event", return_value=None):
            self.assertTrue(ntfy.process_message_event(event, "ok1"))
        self.assertFalse(ntfy.RETRY_STATE_FILE.exists())
        self.assertEqual(self.read_dead_letters(), [])

    def test_poison_message_does_not_block_following_message(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def __iter__(self):
                events = [
                    {"id": "bad3", "event": "message", "message": "missing title"},
                    {"id": "ok2", "event": "message", "title": "ok", "message": "body"},
                ]
                return iter((json.dumps(item) + "\n").encode() for item in events)

        published = []

        def fake_publish(event):
            if event.get("id") == "bad3":
                raise ntfy.PermanentMessageError("malformed")
            published.append(event["id"])

        with patch.object(ntfy, "open_auth_request", return_value=FakeResponse()), \
             patch.object(ntfy, "publish_event", side_effect=fake_publish):
            cursor, processed = ntfy.poll_once("start")

        self.assertEqual(cursor, "ok2")
        self.assertEqual(processed, 2)
        self.assertEqual(published, ["ok2"])
        self.assertEqual(ntfy.STATE_FILE.read_text().strip(), "ok2")
        records = self.read_dead_letters()
        self.assertEqual([record["event"]["id"] for record in records], ["bad3"])


if __name__ == "__main__":
    unittest.main()
