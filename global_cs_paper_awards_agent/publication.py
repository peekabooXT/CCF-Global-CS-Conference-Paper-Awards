"""Local human confirmation, reproducible public snapshots and publication journal."""
import json
import os
import re
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path

from .db import Database
from .github_publish import PUBLISHED_JSON, verified_snapshot
from .markdown_export import render_markdown
from .paper_search import search_papers
from .public_data import review_preview, confirm_review, public_snapshot, write_public_database, publication_time
from .public_release import ServerPublisher, release_bytes
from .deduplication import duplicate_preview, apply_resolutions

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "data/local-publish-config.json"
LOCK = threading.Lock()


def load_config():
    config = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.is_file() else {}
    config.setdefault("repository", "peekabooXT/Global-CS-Paper-Awards-Agent")
    config.setdefault("branch", "main")
    return config


def configuration_status():
    config = load_config()
    return {"repository": config["repository"], "server": config.get("server_host", ""),
            "configured": bool(config.get("server_host") and Path(config.get("server_key", "")).is_file()),
            "public_frontend_ready": (ROOT / "frontend/dist-public/index.html").is_file()}


class GitDataPublisher:
    """Use the computer's existing Git credential manager in an isolated checkout."""
    def __init__(self, config, root=ROOT):
        self.repository = config["repository"]
        self.branch = config["branch"]
        self.root = Path(root)
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", self.repository) or not re.fullmatch(r"[\w./-]+", self.branch):
            raise ValueError("GitHub 仓库或分支配置不正确")
        self.url = "https://github.com/" + self.repository + ".git"

    def _git(self, args, cwd=None, timeout=180):
        try:
            result = subprocess.run(["git", *args], cwd=cwd or self.root, capture_output=True,
                text=True, encoding="utf-8", errors="replace", timeout=timeout,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "Never"})
        except (OSError, subprocess.TimeoutExpired):
            raise ValueError("GitHub 发布失败：Git 不可用或连接超时") from None
        if result.returncode:
            raise ValueError("GitHub 发布失败；请确认本机 Git 登录、仓库写权限与分支状态。数据审核结果已保留，可重试。")
        return result.stdout.strip()

    def check(self):
        self._git(["ls-remote", "--exit-code", self.url, "refs/heads/" + self.branch])

    def publish(self, files, release_id):
        with tempfile.TemporaryDirectory() as temp:
            work = Path(temp) / "repository"
            self._git(["clone", "--quiet", "--depth", "1", "--single-branch", "--branch", self.branch, self.url, str(work)])
            for name, data in files.items():
                path = work / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            self._git(["add", "-f", "--", *files], work)
            self._git(["-c", "user.name=Global CS Awards Publisher", "-c", "user.email=awards-publisher@users.noreply.github.com",
                       "commit", "-m", "data: publish reviewed awards " + release_id[:8]], work)
            self._git(["push", "origin", "HEAD:refs/heads/" + self.branch], work)
            commit = self._git(["rev-parse", "HEAD"], work)
        return {"commit_sha": commit, "commit_url": f"https://github.com/{self.repository}/commit/{commit}",
                "files": list(files)}

    def sync_local_checkout(self, commit, files):
        """Fast-forward only; never overwrite local edits or reset the workbench."""
        if self._git(['branch','--show-current']) != self.branch:
            return {'updated':False,'warning':'当前本地分支不是发布分支，未改动本地索引；生成文件保存在 data/publications。'}
        if self._git(['status','--porcelain','--ignored','--untracked-files=all','--',*files]):
            return {'updated':False,'warning':'本地索引或快照有未提交文件，已保留；生成文件保存在 data/publications。'}
        try:
            self._git(['fetch','origin',self.branch])
            self._git(['merge','--ff-only',commit])
        except ValueError:
            return {'updated':False,'warning':'本地 Git 无法快进，未覆盖本地改动；可核对后同步发布提交。'}
        return {'updated':True}


def build_files(db, snapshot):
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        path = root / "public.sqlite3"
        write_public_database(snapshot, path)
        public = Database(path, read_only=True)
        try:
            snapshot["publication"]["paper_results"] = len(search_papers(public, {"status": "verified"}))
            rendered = render_markdown(public, root, status="verified", generated_at=snapshot["publication"]["published_at"])
            files = {Path(p).relative_to(root).as_posix(): Path(p).read_bytes() for p in rendered["files"]}
        finally:
            public.close()
    legacy = verified_snapshot(db)
    legacy["generated_at"] = snapshot["publication"]["published_at"]
    files[PUBLISHED_JSON] = (json.dumps(legacy, ensure_ascii=False, indent=2) + "\n").encode()
    files["data/exports/public-data.json"] = (json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n").encode()
    files["data/exports/publication.json"] = (json.dumps(snapshot["publication"], ensure_ascii=False, indent=2) + "\n").encode()
    return files


def init_journal(db):
    db.conn.execute("""CREATE TABLE IF NOT EXISTS publication_runs (
        id TEXT PRIMARY KEY, status TEXT NOT NULL, started_at TEXT NOT NULL,
        finished_at TEXT, details TEXT NOT NULL)""")
    db.conn.commit()


def history(db, limit=15):
    init_journal(db)
    if not LOCK.locked():
        rows = db.conn.execute("SELECT id,details FROM publication_runs WHERE status IN ('preflight','github','server')").fetchall()
        for row in rows:
            details = json.loads(row['details'])
            details['error'] = '本地进程已中断；请先核对两端状态再重试。'
            db.conn.execute('UPDATE publication_runs SET status=?,finished_at=?,details=? WHERE id=?',
                ('partial' if details.get('github') else 'failed',publication_time(),json.dumps(details,ensure_ascii=False),row['id']))
        db.conn.commit()
    return [{**dict(row), "details": json.loads(row["details"])} for row in db.conn.execute(
        "SELECT * FROM publication_runs ORDER BY started_at DESC,id DESC LIMIT ?", (limit,))]


def _journal(path, job_id, status, details, finished=False):
    db = Database(path)
    try:
        init_journal(db)
        db.conn.execute("UPDATE publication_runs SET status=?,details=?,finished_at=? WHERE id=?",
                        (status, json.dumps(details, ensure_ascii=False), publication_time() if finished else None, job_id))
        db.conn.commit()
    finally:
        db.close()


def start_publication(database_path, request):
    if not LOCK.acquire(blocking=False):
        raise ValueError("已有发布任务正在运行，请等待完成")
    job_id = uuid.uuid4().hex
    db = None
    try:
        db = Database(database_path)
        init_journal(db)
        db.conn.execute("INSERT INTO publication_runs VALUES (?,?,?,NULL,?)",
                        (job_id, "preflight", publication_time(), json.dumps({"reviewer": request["reviewer"]}, ensure_ascii=False)))
        db.conn.commit()
    except Exception:
        LOCK.release()
        raise
    finally:
        if db: db.close()
    threading.Thread(target=_publish, args=(database_path, job_id, request), daemon=True).start()
    return {"id": job_id}


def _publish(path, job_id, request):
    details = {"reviewer": request["reviewer"]}
    github_done = False
    try:
        config = load_config()
        github = GitDataPublisher(config)
        private = GitDataPublisher({**config, "repository": config["private_repository"]}) if config.get("private_repository") else None
        server = ServerPublisher(config)
        server.check()
        github.check()
        if private:
            private.check()
        if not (ROOT / "frontend/dist-public/index.html").is_file():
            raise ValueError("公开前端构建缺失，请先执行 npm run build:public")
        db = Database(path)
        try:
            db.conn.execute("BEGIN IMMEDIATE")
            details["reviewed"] = confirm_review(db, request["digest"], request["reviewer"], request.get("note", ""))
            duplicates = duplicate_preview(db)
            if duplicates['auto_safe_groups']:
                if not request.get('cleanup_duplicates'):
                    raise ValueError('发现重复论文，请先使用本地重复排查，或勾选发布前一键合并重复数据')
                details['duplicate_cleanup'] = apply_resolutions(db,duplicates['digest'],auto=True,reviewer=request['reviewer'])
            snapshot = public_snapshot(db, release_id=job_id)
            if not any(snapshot["tables"][t] for t in ("records", "award_event_papers", "source_listings")) and not request.get("allow_empty"):
                raise ValueError("本次发布内容为空；请在预览中明确确认空数据发布")
            files = build_files(db, snapshot)
            db.conn.commit()
        except Exception:
            db.conn.rollback()
            raise
        finally:
            db.close()
        output = ROOT / "data/publications" / job_id
        output.mkdir(parents=True, exist_ok=False)
        for name, data in files.items():
            target = output / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        details["publication"] = snapshot["publication"]
        _journal(path, job_id, "github", details)
        details["github"] = github.publish(files, job_id)
        github_done = True
        _journal(path, job_id, "server", details)
        details["server"] = server.publish(release_bytes(ROOT, snapshot, files, details["github"]["commit_sha"]))
        private_failed = False
        if private:
            try:
                details["private_github"] = private.publish(files, job_id)
            except ValueError as exc:
                private_failed = True
                details["error"] = "公开数据已发布；私有维护仓库同步失败：" + str(exc)
        details['local_sync'] = github.sync_local_checkout(details['github']['commit_sha'],files)
        _journal(path, job_id, "partial" if private_failed else "completed", details, finished=True)
    except Exception as exc:
        details["error"] = str(exc)
        _journal(path, job_id, "partial" if github_done else "failed", details, finished=True)
    finally:
        LOCK.release()
