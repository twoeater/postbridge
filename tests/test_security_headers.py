from pathlib import Path
import importlib
import re
import tempfile
import unittest

from app import app


db_module = importlib.import_module("app.db")


class SecurityHeadersTests(unittest.TestCase):
    def setUp(self):
        self._old_db_path = db_module.DB_PATH
        self._tmp = tempfile.TemporaryDirectory()
        db_module.DB_PATH = Path(self._tmp.name) / "blog.db"
        db_module.init_db()
        with db_module.get_db(False) as db:
            db.execute(
                """
                INSERT INTO posts(
                    slug,title,summary,body_markdown,body_html,tags,
                    published_at,updated_at,source_file
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                (
                    "security-test",
                    "Security test",
                    "",
                    "safe",
                    "<p>safe</p>",
                    "",
                    "2026-09-17T00:00:00Z",
                    "2026-09-17T00:00:00Z",
                    "test",
                ),
            )
        self.client = app.test_client()

    def tearDown(self):
        db_module.DB_PATH = self._old_db_path
        self._tmp.cleanup()

    def test_csp_blocks_inline_code_and_allows_data_images(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        policy = response.headers["Content-Security-Policy"]
        self.assertIn("default-src 'self'", policy)
        self.assertIn("script-src 'self' 'nonce-", policy)
        self.assertIn("style-src 'self'", policy)
        self.assertIn("img-src 'self' data:", policy)
        self.assertNotIn("'unsafe-inline'", policy)
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(
            response.headers["Referrer-Policy"],
            "strict-origin-when-cross-origin",
        )

    def test_json_ld_nonce_matches_csp_and_post_js_is_external(self):
        response = self.client.get("/post/security-test")
        self.assertEqual(response.status_code, 200)
        body = response.get_data(as_text=True)
        policy = response.headers["Content-Security-Policy"]
        header_nonce = re.search(r"'nonce-([^']+)'", policy)
        html_nonce = re.search(
            r'<script nonce="([^"]+)" type="application/ld\+json">',
            body,
        )
        self.assertIsNotNone(header_nonce)
        self.assertIsNotNone(html_nonce)
        self.assertEqual(header_nonce.group(1), html_nonce.group(1))
        self.assertIn('/static/post.js?v=20260917-1', body)
        self.assertNotRegex(body, r"\sstyle=")


if __name__ == "__main__":
    unittest.main()
