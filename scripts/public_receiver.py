"""Root-owned forced SSH command; accepts public-only releases, never a shell.

Install at /opt/Global-CS-Paper-Awards-Agent/bin/public_receiver.py.
The deploy user may restart ONLY the public systemd service via scoped sudo.
"""
import hashlib
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import tarfile
import time
import uuid
from contextlib import closing
from pathlib import Path, PurePosixPath
from urllib.request import urlopen

ROOT = Path('/opt/Global-CS-Paper-Awards-Agent')
SERVICE = 'global-cs-paper-awards-agent.service'
MAX_ARCHIVE = 128 * 1024 * 1024
MAX_CONTENT = 256 * 1024 * 1024
TABLES = {'conferences','records','award_events','award_papers','award_event_papers','source_listings','source_listing_records'}
MODULES = {'__init__.py','public_db.py','model.py','ontology.py','award_events.py','source_listings.py','paper_search.py','web_helpers.py'}


def allowed(name):
    path = PurePosixPath(name)
    if path.is_absolute() or '..' in path.parts or '\\' in name or str(path) != name:
        return False
    if name in {'public_api.py','requirements-public.txt','AWARDS.md','data/conferences.json','data/public.sqlite3','data/publication.json'}:
        return True
    if name.startswith('global_cs_paper_awards_agent/'):
        return name.split('/',1)[1] in MODULES
    if name.startswith('docs/awards/'):
        return name.split('/')[-1] in {'BY_AWARD.md','BY_YEAR.md','BY_CATEGORY.md'} and len(path.parts)==3
    return bool(re.fullmatch(r'frontend/dist/(?:assets/)?[A-Za-z0-9_.-]+\.(?:html|js|css|svg|ico|png|woff2?)', name))


def unpack(data, destination):
    """Manual regular-file extraction: no traversal, links, special files or extras."""
    size = 0
    seen = set()
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
        for entry in archive:
            if not entry.isfile() or entry.name in seen or not allowed(entry.name):
                raise ValueError('发布包包含禁止文件或路径')
            seen.add(entry.name); size += entry.size
            if len(seen)>2000 or size>MAX_CONTENT or entry.size<0:
                raise ValueError('发布包超过安全大小')
            path = destination / entry.name
            path.parent.mkdir(parents=True,exist_ok=True)
            with archive.extractfile(entry) as source, path.open('xb') as target:
                while chunk := source.read(1024*1024): target.write(chunk)
            path.chmod(0o644)
    required = {'public_api.py','frontend/dist/index.html','data/public.sqlite3','data/publication.json'}
    if not required.issubset(seen): raise ValueError('发布包不完整')
    for path in destination.rglob('*.py'):
        compile(path.read_text(encoding='utf-8'),str(path),'exec')


def validate_database(path):
    with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as conn:
        conn.execute('PRAGMA query_only=ON')
        conn.execute('PRAGMA trusted_schema=OFF')
        objects = conn.execute("SELECT name,type FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'").fetchall()
        if {name for name,kind in objects if kind=='table'} != TABLES or any(kind not in {'table','index'} for _,kind in objects):
            raise ValueError('公开数据库包含管理表或非法对象')
        if conn.execute('PRAGMA integrity_check').fetchone()[0]!='ok' or conn.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('公开数据库完整性检查失败')
        for table in ('records','award_events','award_event_papers','source_listings'):
            if conn.execute(f"SELECT COUNT(*) FROM {table} WHERE status IS NULL OR status!='verified'").fetchone()[0]:
                raise ValueError('公开数据库不能包含未经核验数据')


def restart():
    subprocess.run(['/usr/bin/sudo','-n','/usr/bin/systemctl','restart',SERVICE],check=True,capture_output=True,timeout=30)


def switch(target):
    link = ROOT / ('.current-' + uuid.uuid4().hex)
    link.symlink_to(target, target_is_directory=True)
    os.replace(link, ROOT / 'current')


def wait_ready(release_id):
    for _ in range(30):
        try:
            with urlopen('http://127.0.0.1:8000/api/meta',timeout=2) as response:
                meta = json.load(response)
            if meta.get('mode')=='public' and meta.get('publication',{}).get('release_id')==release_id:
                return
        except Exception:
            pass
        time.sleep(.5)
    raise ValueError('公开网站未通过启动检查')


def publish(data, checksum):
    if len(data)>MAX_ARCHIVE or hashlib.sha256(data).hexdigest()!=checksum:
        raise ValueError('发布包校验失败')
    destination = ROOT / 'releases' / ('release-'+uuid.uuid4().hex)
    destination.mkdir(mode=0o755)
    unpack(data,destination)
    validate_database(destination/'data/public.sqlite3')
    manifest = json.loads((destination/'data/publication.json').read_text(encoding='utf-8'))
    release_id = manifest.get('release_id','')
    if not re.fullmatch(r'[a-f0-9]{32}',release_id) or not manifest.get('published_at'):
        raise ValueError('发布版本号或时间无效')
    old = (ROOT/'current').resolve() if (ROOT/'current').exists() else None
    if old and not old.is_relative_to(ROOT/'releases'): raise ValueError('旧版本路径不符合发布规范')
    switch(destination)
    try:
        restart(); wait_ready(release_id)
    except Exception:
        if old:
            switch(old)
            restart()
        raise ValueError('服务器启动失败，已恢复上一版；请查看服务器服务日志') from None
    return {'ok':True,'release_id':release_id,'published_at':manifest['published_at'],'github_commit':manifest.get('github_commit','')}


def main():
    import fcntl
    os.umask(0o022)
    command = os.getenv('SSH_ORIGINAL_COMMAND','')
    if command=='check':
        if not (ROOT/'releases').is_dir() or not os.access(ROOT/'releases',os.W_OK):
            raise ValueError('服务器发布目录未准备好')
        result = {'ok':True,'mode':'public-only-receiver'}
    else:
        match = re.fullmatch(r'publish ([a-f0-9]{64})',command)
        if not match: raise ValueError('此密钥只允许公开数据发布，不提供登录或命令执行')
        with (ROOT/'releases/.publication.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            result = publish(sys.stdin.buffer.read(MAX_ARCHIVE+1),match.group(1))
    print(json.dumps(result,ensure_ascii=False))


if __name__=='__main__':
    try: main()
    except Exception as exc:
        print(json.dumps({'ok':False,'error':str(exc)},ensure_ascii=False));sys.exit(1)
