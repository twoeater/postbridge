from __future__ import annotations

import gc
import importlib
import os
from pathlib import Path
import tempfile
import unittest


db_module = importlib.import_module("app.db")


class DatabaseConnectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_path = db_module.DB_PATH
        db_module.DB_PATH = Path(self.tmp.name) / "test.db"
        db_module.init_db()

    def tearDown(self):
        db_module.DB_PATH = self.old_path
        self.tmp.cleanup()

    def test_connection_is_closed_after_context_exit(self):
        with db_module.get_db() as db:
            self.assertEqual(db.execute("SELECT 1").fetchone()[0], 1)
            connection = db

        with self.assertRaises(db_module._dbapi.ProgrammingError):
            connection.execute("SELECT 1")

    def test_write_transaction_commits_and_closes(self):
        with db_module.get_db(False) as db:
            db.execute(
                """
                INSERT INTO posts(
                    slug,title,summary,body_markdown,body_html,tags,
                    published_at,updated_at,source_file
                ) VALUES(?,?,?,?,?,?,?,?,?)
                """,
                ("closed-test", "test", "", "body", "<p>body</p>", "", "2026-09-17T00:00:00Z", "2026-09-17T00:00:00Z", "test"),
            )
            connection = db

        with db_module.get_db() as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM posts WHERE slug = ?", ("closed-test",)).fetchone()[0],
                1,
            )
        with self.assertRaises(db_module._dbapi.ProgrammingError):
            connection.execute("SELECT 1")

    @unittest.skipUnless(Path("/proc/self/fd").exists(), "requires /proc fd accounting")
    def test_repeated_connections_do_not_accumulate_db_file_descriptors(self):
        db_real = str(db_module.DB_PATH.resolve())

        def count_db_fds():
            count = 0
            for fd in Path("/proc/self/fd").iterdir():
                try:
                    if os.path.realpath(fd) == db_real:
                        count += 1
                except OSError:
                    pass
            return count

        was_enabled = gc.isenabled()
        gc.disable()
        try:
            before = count_db_fds()
            for _ in range(100):
                with db_module.get_db() as db:
                    db.execute("SELECT 1").fetchone()
            after = count_db_fds()
        finally:
            if was_enabled:
                gc.enable()

        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
