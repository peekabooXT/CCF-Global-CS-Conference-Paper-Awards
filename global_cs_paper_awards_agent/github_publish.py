"""Build and publish a reviewed-data snapshot to GitHub."""
import hashlib
import hmac
import json
import os
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

from .markdown_export import render_markdown


PUBLISHED_JSON = "data/exports/verified-records.json"


def verify_publish_password(password, expected_hash=None):
    """Verify a password without storing or comparing the plaintext secret."""
    expected = expected_hash if expected_hash is not None else os.getenv("PUBLISH_PASSWORD_SHA256", "")
    expected = str(expected or "").strip().lower()
    if len(expected) != 64 or any(ch not in "0123456789abcdef" for ch in expected):
        return False
    actual = hashlib.sha256(str(password or "").encode("utf-8")).hexdigest()
    return hmac.compare_digest(actual, expected)


def _snapshot_entry(record):
    payload_fields = (
        "title", "award_name", "track", "award_evidence", "title_evidence",
        "authors", "publication_date", "publication_date_evidence", "paper_url", "doi",
    )
    return {
        "conference_id": record["conference_id"],
        "year": record["year"],
        "status": "verified",
        "reviewer": record.get("reviewer") or "",
        "review_note": record.get("review_note") or "",
        "sources": record["sources"],
        "record": {field: record.get(field) for field in payload_fields},
    }


def verified_snapshot(db):
    records = db.search(status="verified")
    return {
        "schema_version": 1,
        "generated_at": max((record.get("updated_at") or "" for record in records), default=None),
        "record_count": len(records),
        "records": [_snapshot_entry(record) for record in records],
    }


def build_publish_files(db):
    """Return the versioned files generated from currently verified records."""
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        rendered = render_markdown(db, root, status="verified")
        files = {
            Path(path).relative_to(root).as_posix(): Path(path).read_bytes()
            for path in rendered["files"]
        }
    snapshot = verified_snapshot(db)
    files[PUBLISHED_JSON] = (
        json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    return files


def import_verified_snapshot(db, path):
    """Import a published snapshot and restore its human-review decisions."""
    db.init()
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("records"), list):
        raise ValueError("已核验快照格式不受支持")
    result = {"records": 0, "inserted": 0, "updated": 0, "unchanged": 0, "reviewed": 0}
    for entry in data["records"]:
        bundle = {
            "conference_id": entry.get("conference_id"),
            "year": entry.get("year"),
            "sources": entry.get("sources"),
            "records": [entry.get("record")],
        }
        change = db.ingest(bundle)
        if change["rejected"]:
            raise ValueError("已核验快照包含无法导入的记录：" + change["rejected"][0]["error"])
        for key in ("inserted", "updated", "unchanged"):
            result[key] += change[key]
        rid = change["record_ids"][0]
        current = next(item for item in db.search(status="all") if item["id"] == rid)
        reviewer = str(entry.get("reviewer") or "GitHub verified snapshot")
        note = str(entry.get("review_note") or "从已核验 GitHub 快照恢复")
        if (current["status"], current.get("reviewer"), current.get("review_note")) != ("verified", reviewer, note):
            db.review(rid, "verified", reviewer, note)
            result["reviewed"] += 1
        result["records"] += 1
    return result


def git_blob_sha(content):
    header = f"blob {len(content)}\0".encode("ascii")
    return hashlib.sha1(header + content).hexdigest()


class GitHubPublisher:
    """Create one atomic commit with generated reviewed-data files."""

    def __init__(self, token=None, repository=None, branch=None, api_url=None):
        self.token = token if token is not None else os.getenv("GITHUB_TOKEN", os.getenv("GH_TOKEN", ""))
        self.repository = repository or os.getenv("GITHUB_REPOSITORY", "peekabooXT/Global-CS-Paper-Awards-Agent")
        self.branch = branch or os.getenv("GITHUB_BRANCH", "main")
        self.api_url = (api_url or os.getenv("GITHUB_API_URL", "https://api.github.com")).rstrip("/")
        if not self.token:
            raise ValueError("服务器未配置 GITHUB_TOKEN；请在服务器环境变量中配置具有 Contents 写权限的令牌")
        parts = self.repository.split("/")
        if len(parts) != 2 or not all(parts):
            raise ValueError("GITHUB_REPOSITORY 必须是 owner/repository 格式")
        if not self.branch or any(ch in self.branch for ch in "\r\n"):
            raise ValueError("GITHUB_BRANCH 无效")

    def _request(self, method, path, body=None):
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.api_url + path, data=data, method=method,
            headers={
                "Authorization": "Bearer " + self.token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
                "User-Agent": "global-cs-paper-awards-agent",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.loads(response.read(8 * 1024 * 1024).decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise ValueError(f"GitHub API HTTP {exc.code}；请检查令牌权限、仓库名和分支保护规则") from None
        except (urllib.error.URLError, TimeoutError):
            raise ValueError("GitHub API 网络失败或超时") from None

    def publish(self, files, message=None):
        repo = "/repos/" + self.repository
        branch = quote(self.branch, safe="")
        ref = self._request("GET", f"{repo}/git/ref/heads/{branch}")
        parent_sha = ref["object"]["sha"]
        commit = self._request("GET", f"{repo}/git/commits/{parent_sha}")
        base_tree = commit["tree"]["sha"]
        current = self._request("GET", f"{repo}/git/trees/{base_tree}?recursive=1")
        existing = {item["path"]: item.get("sha") for item in current.get("tree", []) if item.get("type") == "blob"}
        changed = {
            path: content for path, content in files.items()
            if existing.get(path) != git_blob_sha(content)
        }
        if not changed:
            return {"changed": False, "files": [], "commit_sha": parent_sha,
                    "commit_url": f"https://github.com/{self.repository}/commit/{parent_sha}"}
        entries = []
        for path, content in sorted(changed.items()):
            blob = self._request("POST", f"{repo}/git/blobs", {
                "content": content.decode("utf-8"), "encoding": "utf-8",
            })
            entries.append({"path": path, "mode": "100644", "type": "blob", "sha": blob["sha"]})
        tree = self._request("POST", f"{repo}/git/trees", {"base_tree": base_tree, "tree": entries})
        created = self._request("POST", f"{repo}/git/commits", {
            "message": message or "data: publish reviewed award records",
            "tree": tree["sha"], "parents": [parent_sha],
        })
        self._request("PATCH", f"{repo}/git/refs/heads/{branch}", {"sha": created["sha"], "force": False})
        return {"changed": True, "files": sorted(changed), "commit_sha": created["sha"],
                "commit_url": f"https://github.com/{self.repository}/commit/{created['sha']}"}


def publish_verified(db, publisher=None):
    publisher = publisher or GitHubPublisher()
    files = build_publish_files(db)
    result = publisher.publish(files)
    result["verified_records"] = len(db.search(status="verified"))
    return result
