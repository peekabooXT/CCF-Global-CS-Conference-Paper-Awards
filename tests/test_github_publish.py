import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from global_cs_paper_awards_agent.db import Database
from global_cs_paper_awards_agent.github_publish import (
    GitHubPublisher, PUBLISHED_JSON, build_publish_files, git_blob_sha,
    import_verified_snapshot, verify_publish_password,
)
from global_cs_paper_awards_agent.web_helpers import import_demo


class FakePublisher(GitHubPublisher):
    def __init__(self, existing=None):
        super().__init__(token="test-token", repository="owner/repo", branch="main")
        self.existing = existing or {}
        self.calls = []
        self.blobs = 0

    def _request(self, method, path, body=None):
        self.calls.append((method, path, body))
        if method == "GET" and "/git/ref/" in path:
            return {"object": {"sha": "parent"}}
        if method == "GET" and "/git/commits/" in path:
            return {"tree": {"sha": "base-tree"}}
        if method == "GET" and "/git/trees/" in path:
            return {"tree": [
                {"path": key, "type": "blob", "sha": value}
                for key, value in self.existing.items()
            ]}
        if method == "POST" and path.endswith("/git/blobs"):
            self.blobs += 1
            return {"sha": f"blob-{self.blobs}"}
        if method == "POST" and path.endswith("/git/trees"):
            return {"sha": "new-tree"}
        if method == "POST" and path.endswith("/git/commits"):
            return {"sha": "new-commit"}
        if method == "PATCH":
            return {"object": {"sha": "new-commit"}}
        raise AssertionError((method, path, body))


class PublishPasswordTest(unittest.TestCase):
    def test_password_is_verified_against_hash_without_plaintext_storage(self):
        expected = hashlib.sha256(b"test-secret").hexdigest()
        self.assertTrue(verify_publish_password("test-secret", expected))
        self.assertFalse(verify_publish_password("wrong-secret", expected))
        self.assertFalse(verify_publish_password("test-secret", "not-a-valid-hash"))


class GitHubPublishTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.tmp.name) / "awards.sqlite3")
        self.db.init()
        import_demo(self.db)
        first = self.db.search(status="pending")[0]
        self.db.review(first["id"], "verified", "Reviewer", "Checked official award page")
        self.verified_title = first["title"]
        self.pending_title = next(r["title"] for r in self.db.search(status="pending"))

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_build_files_include_only_verified_records_and_snapshot_round_trips(self):
        files = build_publish_files(self.db)
        self.assertEqual(set(files), {
            "AWARDS.md", "docs/awards/BY_CATEGORY.md", "docs/awards/BY_YEAR.md",
            "docs/awards/BY_AWARD.md", PUBLISHED_JSON,
        })
        main = files["AWARDS.md"].decode("utf-8")
        self.assertIn(self.verified_title, main)
        self.assertNotIn(self.pending_title, main)
        snapshot = json.loads(files[PUBLISHED_JSON])
        self.assertEqual(snapshot["record_count"], 1)

        path = Path(self.tmp.name) / "verified.json"
        path.write_bytes(files[PUBLISHED_JSON])
        restored = Database(Path(self.tmp.name) / "restored.sqlite3")
        try:
            result = import_verified_snapshot(restored, path)
            records = restored.search(status="verified")
            self.assertEqual(result["records"], 1)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["reviewer"], "Reviewer")
        finally:
            restored.close()

    def test_publisher_skips_unchanged_files(self):
        files = {"AWARDS.md": b"same"}
        publisher = FakePublisher({"AWARDS.md": git_blob_sha(files["AWARDS.md"])})
        result = publisher.publish(files)
        self.assertFalse(result["changed"])
        self.assertFalse(any(method == "POST" for method, _, _ in publisher.calls))

    def test_publisher_creates_one_commit_for_changed_files(self):
        publisher = FakePublisher()
        result = publisher.publish({"AWARDS.md": b"new", PUBLISHED_JSON: b"{}\n"})
        self.assertTrue(result["changed"])
        self.assertEqual(result["commit_sha"], "new-commit")
        self.assertEqual(publisher.blobs, 2)
        self.assertEqual(sum(method == "POST" and path.endswith("/git/commits")
                             for method, path, _ in publisher.calls), 1)
        self.assertEqual(sum(method == "PATCH" for method, _, _ in publisher.calls), 1)


if __name__ == "__main__":
    unittest.main()
