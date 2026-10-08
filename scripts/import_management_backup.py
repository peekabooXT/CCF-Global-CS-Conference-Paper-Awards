"""Move a server management SQLite backup into a local workbench, once only.

Existing local records and coverage decisions win conflicts. Backups are kept.
Usage: python scripts/import_management_backup.py BACKUP.sqlite3 LOCAL.sqlite3
"""
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from global_cs_paper_awards_agent.db import Database
from global_cs_paper_awards_agent.public_data import publication_time


def migrate(source,target):
    source,target=Path(source).resolve(),Path(target).resolve()
    if source==target:raise ValueError('备份与目标不能相同')
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    db=Database(target);db.init()
    db.conn.execute('CREATE TABLE IF NOT EXISTS management_imports (source_sha TEXT PRIMARY KEY,imported_at TEXT,summary TEXT)')
    if db.conn.execute('SELECT 1 FROM management_imports WHERE source_sha=?',(digest,)).fetchone():
        existing=json.loads(db.conn.execute('SELECT summary FROM management_imports WHERE source_sha=?',(digest,)).fetchone()[0])
        if 'copied_revisions' not in existing:
            old=sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True)
            try:
                with db.conn:
                    rows=old.execute('SELECT record_id,snapshot,archived_at FROM revisions').fetchall()
                    db.conn.executemany('INSERT INTO revisions(record_id,snapshot,archived_at) VALUES (?,?,?)',rows)
                    existing['copied_revisions']=len(rows)
                    db.conn.execute('UPDATE management_imports SET summary=? WHERE source_sha=?',(json.dumps(existing,ensure_ascii=False),digest))
            finally:old.close()
        db.close();return {'already_imported':True,**existing}
    backup=target.parent/'backups'/('before-management-import-'+publication_time().replace(':','-')+'.sqlite3')
    backup.parent.mkdir(parents=True,exist_ok=True)
    conn=sqlite3.connect(backup);db.conn.backup(conn);conn.close()
    old=sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True);old.row_factory=sqlite3.Row
    summary={'inserted_records':0,'existing_records_preserved':0,'copied_runs':0,'seeds':0,'coverage':0,'backup':str(backup)}
    try:
        for row in old.execute('SELECT * FROM records'):
            if db.conn.execute('SELECT 1 FROM records WHERE id=?',(row['id'],)).fetchone():
                summary['existing_records_preserved']+=1;continue
            result=db.ingest({'conference_id':row['conference_id'],'year':row['year'],
                'records':[json.loads(row['payload'])],'sources':json.loads(row['sources'])})
            if result['rejected']:raise ValueError('服务器备份数据证据校验失败，请保留备份并人工处理')
            summary['inserted_records']+=result['inserted']
            rid=result['record_ids'][0]
            db.conn.execute('UPDATE records SET status=?,reviewer=?,review_note=?,created_at=?,updated_at=? WHERE id=?',
                (row['status'],row['reviewer'],row['review_note'],row['created_at'],row['updated_at'],rid));db.conn.commit()
        with db.conn:
            for table,key in [('seeds','seeds'),('coverage','coverage')]:
                for row in old.execute('SELECT * FROM '+table):
                    fields=list(row.keys())
                    summary[key]+=db.conn.execute(f"INSERT OR IGNORE INTO {table} ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})",tuple(row)).rowcount
            for row in old.execute('SELECT * FROM runs'):
                data=dict(row);data.pop('id')
                details=json.loads(data['details'] or '{}');details['migrated_from_server_run_id']=row['id'];details['migration_source_sha']=digest
                data['details']=json.dumps(details,ensure_ascii=False)
                if data['status']=='running':data['status']='failed';data['finished_at']=publication_time()
                fields=list(data)
                db.conn.execute(f"INSERT INTO runs ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})",list(data.values()))
                summary['copied_runs']+=1
            for table in ('award_events','award_papers','award_event_papers','source_listings','source_listing_records'):
                for row in old.execute('SELECT * FROM '+table):
                    fields=list(row.keys())
                    db.conn.execute(f"INSERT OR IGNORE INTO {table} ({','.join(fields)}) VALUES ({','.join('?' for _ in fields)})",tuple(row))
            revisions=old.execute('SELECT record_id,snapshot,archived_at FROM revisions').fetchall()
            db.conn.executemany('INSERT INTO revisions(record_id,snapshot,archived_at) VALUES (?,?,?)',revisions)
            summary['copied_revisions']=len(revisions)
            db.conn.execute('INSERT INTO management_imports VALUES (?,?,?)',(digest,publication_time(),json.dumps(summary,ensure_ascii=False)))
        return summary
    finally:old.close();db.close()


if __name__=='__main__':print(json.dumps(migrate(sys.argv[1],sys.argv[2]),ensure_ascii=False))
