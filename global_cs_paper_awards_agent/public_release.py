"""Create public-only releases and send them through a restricted SSH receiver."""
import hashlib
import ast
import io
import json
import os
import re
import subprocess
import tarfile
import tempfile
from pathlib import Path

from .public_data import write_public_database

PUBLIC_MODULES = ("__init__.py", "public_db.py", "model.py", "ontology.py",
                  "award_events.py", "source_listings.py", "paper_search.py", "web_helpers.py")

READ_FUNCTIONS = {'award_events.py': {'list_events', 'event_detail'},
                  'source_listings.py': {'list_source_listings', 'source_listing_detail'},
                  'web_helpers.py': {'validate_filters', 'export_rows', 'csv_bytes'}}


def public_module_bytes(root, name):
    source = (Path(root) / 'global_cs_paper_awards_agent' / name).read_text(encoding='utf-8')
    if name in READ_FUNCTIONS:
        tree = ast.parse(source)
        tree.body = [node for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom)) or
                     isinstance(node, ast.Assign) and name == 'web_helpers.py' and
                     any(isinstance(t, ast.Name) and t.id in {'AWARDS', 'STATUSES'} for t in node.targets) or
                     isinstance(node, ast.FunctionDef) and node.name in READ_FUNCTIONS[name]]
        tree.body = [node for node in tree.body if not isinstance(node, ast.ImportFrom) or
                     node.module not in {'award_events', 'source_listings', 'db', 'catalog'}]
        source = ast.unparse(tree) + '\n'
    return source.encode('utf-8')


def release_bytes(root, snapshot, files, github_commit=""):
    root = Path(root)
    frontend = root / "frontend/dist-public"
    if not (frontend / "index.html").is_file():
        raise ValueError("公开前端尚未构建，请先在 frontend 执行 npm run build:public")
    with tempfile.TemporaryDirectory() as temp:
        database = Path(temp) / "public.sqlite3"
        write_public_database(snapshot, database)
        content = {"public_api.py": (root / "public_api.py").read_bytes(),
                   "requirements-public.txt": (root / "requirements-public.txt").read_bytes(),
                   "data/conferences.json": (root / "data/conferences.json").read_bytes(),
                   "data/public.sqlite3": database.read_bytes(),
                   "data/publication.json": json.dumps({**snapshot["publication"], "github_commit": github_commit},
                       ensure_ascii=False, indent=2).encode()}
        for name in PUBLIC_MODULES:
            content["global_cs_paper_awards_agent/" + name] = public_module_bytes(root, name)
        for path in frontend.rglob("*"):
            if path.is_file():
                content["frontend/dist/" + path.relative_to(frontend).as_posix()] = path.read_bytes()
        content.update({path: value for path, value in files.items() if path == "AWARDS.md" or path.startswith("docs/awards/")})
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
            for name, value in sorted(content.items()):
                entry = tarfile.TarInfo(name)
                entry.size, entry.mode = len(value), 0o644
                archive.addfile(entry, io.BytesIO(value))
        return buffer.getvalue()


class ServerPublisher:
    def __init__(self, config):
        self.host = config.get("server_host", "")
        self.user = config.get("server_user", "awardsdeploy")
        self.key = Path(config.get("server_key", "")).expanduser()
        if not re.fullmatch(r"[A-Za-z0-9.-]+", self.host) or not re.fullmatch(r"[a-z_][a-z0-9_-]*", self.user):
            raise ValueError("本地发布配置中的服务器地址或用户无效")
        if not self.key.is_file():
            raise ValueError("本地服务器发布密钥尚未配置")

    def _run(self, command, data=None):
        args = ["ssh", "-T", "-i", str(self.key), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
                "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=15", f"{self.user}@{self.host}", command]
        try:
            result = subprocess.run(args, input=data, capture_output=True, timeout=180)
        except (OSError, subprocess.TimeoutExpired):
            raise ValueError("服务器发布连接失败或超时") from None
        try:
            payload = json.loads(result.stdout.decode("utf-8").strip())
        except (ValueError, UnicodeError):
            raise ValueError("服务器发布连接未返回有效结果，请检查密钥与接收程序") from None
        if result.returncode or not payload.get("ok"):
            raise ValueError(payload.get("error") or "服务器发布失败")
        return payload

    def check(self):
        return self._run("check")

    def publish(self, archive):
        return self._run("publish " + hashlib.sha256(archive).hexdigest(), archive)
