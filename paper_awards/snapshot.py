import hashlib
import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone, timedelta
from pathlib import Path
PUBLIC_TABLES = ('conferences', 'records', 'award_events', 'award_papers', 'award_event_papers', 'source_listings', 'source_listing_records')

def write_public_database(snapshot, path):
    path = Path(path)
    if path.exists():
        raise ValueError('公开数据库目标已存在，不能覆盖现有文件')
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(path)) as conn:
        for table in PUBLIC_TABLES:
            conn.execute(snapshot['schema'][table])
            for row in snapshot['tables'][table]:
                columns = list(row)
                if any((not c.replace('_', '').isalnum() for c in columns)):
                    raise ValueError('无效数据库字段')
                conn.execute(f'INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join(('?' for _ in columns))})', [row[c] for c in columns])
        if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or conn.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('公开数据库完整性校验失败')
        conn.commit()
