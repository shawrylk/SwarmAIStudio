"""
Security regression tests.

Covers the LAN-facing HTTP surface: the artifact-read endpoint must never
disclose files outside the artifact vault, since the server binds 0.0.0.0.
"""

import json
import tempfile
import threading
import urllib.parse
import urllib.request
import unittest
from http.server import HTTPServer
from pathlib import Path

from swarm.config import resolve_within, ARTIFACTS_DIR
from swarm.server import SwarmHandler


class TestResolveWithin(unittest.TestCase):
    def test_rejects_absolute_escape(self):
        self.assertIsNone(resolve_within("/etc/passwd", ARTIFACTS_DIR))

    def test_rejects_dotdot_traversal(self):
        self.assertIsNone(resolve_within("../../etc/passwd", ARTIFACTS_DIR))

    def test_allows_file_inside_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "report.md").write_text("hello", encoding="utf-8")
            resolved = resolve_within("report.md", base)
            self.assertIsNotNone(resolved)
            self.assertEqual(resolved.name, "report.md")

    def test_allows_absolute_inside_base(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            target = base / "sub" / "doc.md"
            target.parent.mkdir(parents=True)
            target.write_text("x", encoding="utf-8")
            self.assertIsNotNone(resolve_within(str(target), base))


class TestServerSecurity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = HTTPServer(("127.0.0.1", 0), SwarmHandler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _get(self, path):
        url = f"http://127.0.0.1:{self.port}{path}"
        with urllib.request.urlopen(url) as r:
            return r.status, json.loads(r.read().decode())

    def test_artifact_read_rejects_path_traversal(self):
        enc = urllib.parse.quote("/etc/passwd")
        try:
            status, body = self._get(f"/api/artifacts/read?path={enc}")
        except urllib.error.HTTPError as e:
            status, body = e.code, json.loads(e.read().decode())
        self.assertEqual(status, 403)
        self.assertNotIn("root:", json.dumps(body))

    def test_artifact_read_rejects_dotdot(self):
        enc = urllib.parse.quote("../../../../etc/passwd")
        try:
            status, body = self._get(f"/api/artifacts/read?path={enc}")
        except urllib.error.HTTPError as e:
            status, body = e.code, json.loads(e.read().decode())
        self.assertEqual(status, 403)


if __name__ == "__main__":
    unittest.main()
