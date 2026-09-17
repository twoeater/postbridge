from __future__ import annotations

import importlib.util
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
import unittest
from urllib.error import HTTPError


SCRIPT = Path(__file__).resolve().parents[1] / "bin" / "ntfy-publisher.py"
spec = importlib.util.spec_from_file_location("postbridge_ntfy_publisher", SCRIPT)
ntfy = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(ntfy)


class RedirectSourceHandler(BaseHTTPRequestHandler):
    target_url = ""
    received_authorization = None

    def do_GET(self):
        type(self).received_authorization = self.headers.get("Authorization")
        self.send_response(302)
        self.send_header("Location", type(self).target_url)
        self.end_headers()

    def log_message(self, *_args):
        pass


class RedirectTargetHandler(BaseHTTPRequestHandler):
    request_count = 0
    received_authorization = None

    def do_GET(self):
        type(self).request_count += 1
        type(self).received_authorization = self.headers.get("Authorization")
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"unexpected")

    def log_message(self, *_args):
        pass


class NtfyRedirectTests(unittest.TestCase):
    def setUp(self):
        self.target = ThreadingHTTPServer(("127.0.0.1", 0), RedirectTargetHandler)
        self.target_thread = Thread(target=self.target.serve_forever, daemon=True)
        self.target_thread.start()

        self.source = ThreadingHTTPServer(("127.0.0.1", 0), RedirectSourceHandler)
        self.source_thread = Thread(target=self.source.serve_forever, daemon=True)
        self.source_thread.start()

        RedirectSourceHandler.target_url = (
            f"http://127.0.0.1:{self.target.server_address[1]}/stolen"
        )
        RedirectSourceHandler.received_authorization = None
        RedirectTargetHandler.request_count = 0
        RedirectTargetHandler.received_authorization = None
        self.old_token = ntfy.TOKEN
        ntfy.TOKEN = "redirect-test-secret"

    def tearDown(self):
        ntfy.TOKEN = self.old_token
        self.source.shutdown()
        self.target.shutdown()
        self.source.server_close()
        self.target.server_close()
        self.source_thread.join(timeout=2)
        self.target_thread.join(timeout=2)

    def test_cross_origin_redirect_is_refused_before_token_forwarding(self):
        url = f"http://127.0.0.1:{self.source.server_address[1]}/attachment"
        with self.assertRaises(HTTPError) as error:
            with ntfy.open_auth_request(url, timeout=5):
                pass

        self.assertEqual(error.exception.code, 302)
        self.assertEqual(
            RedirectSourceHandler.received_authorization,
            "Bearer redirect-test-secret",
        )
        self.assertEqual(RedirectTargetHandler.request_count, 0)
        self.assertIsNone(RedirectTargetHandler.received_authorization)


if __name__ == "__main__":
    unittest.main()
