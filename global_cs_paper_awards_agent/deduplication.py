"""Local-only, reviewed duplicate resolution with immutable SQLite backups."""
import hashlib
import json
import sqlite3
import uuid
from collections import defaultdict
from pathlib import Path

from .paper_search import conference_aliases, paper_identity, title_identity
from .model import now

TABLES = ('records', 'award_papers', 'award_events', 'award_event_papers',
          'source_listings', 'source_listing_records')


def duplicate_preview(db):
    tables = {table: [dict(r) for r in db.conn.execute('SELECT * FROM '+table+' ORDER BY 1')]
              for table in TABLES}
    digest = hashlib.sha256(json.dumps(tables,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    aliases = conference_aliases(db.conn)
    conference_names={r['id']:r['acronym'] for r in db.conn.execute('SELECT id,acronym FROM conferences')}
    grouped = defaultdict(list)
    links_by_paper=defaultdict(list)
    listings_by_paper=defaultdict(list)
    events_by_id={r['id']:r for r in tables['award_events']}
    for row in tables['award_event_papers']:
        links_by_paper[row['paper_id']].append(row)
    for row in tables['source_listings']:
        listings_by_paper[row['paper_id']].append(row)
    for row in tables['award_papers']:
        key = ('paper', *paper_identity(aliases,row['venue'],row['year'],row['title']))
        links = links_by_paper[row['id']]
        listings = listings_by_paper[row['id']]
        statuses = {r['status'] for r in [*links,*listings]}
        grouped[key].append({**row,'statuses':sorted(statuses),
            'awards':[events_by_id[identifier] for identifier in sorted({r['event_id'] for r in links})],
            'sources':sorted({r['source_url'] for r in [*links,*listings]}),
            'references':len(links)+len(listings)})
    for row in tables['records']:
        payload=json.loads(row['payload'])
        key=('record',row['conference_id'],row['year'],title_identity(row['title']),
             title_identity(payload.get('award_name') or row['award_type']))
        grouped[key].append({**row,'venue':conference_names.get(row['conference_id'],row['conference_id']),'statuses':[row['status']],
            'authors_raw':'; '.join(a['name'] for a in payload.get('authors',[])),
            'paper_url':payload.get('paper_url'),'sources':[s['url'] for s in json.loads(row['sources'])],
            'awards':[{'official_award_name':payload.get('award_name')}],'references':0})
    groups=[]
    for key,members in grouped.items():
        if len(members)<2:
            continue
        preferred=sorted(members,key=lambda r:(-int('verified' in r['statuses']),
            -int(bool(r.get('paper_url'))),-r['references'],-int(bool(r.get('authors_raw'))),r['id']))[0]
        groups.append({'id':hashlib.sha256(json.dumps(key).encode()).hexdigest()[:24],
            'kind':key[0],'title':preferred['title'],'venue':preferred['venue'],'year':preferred['year'],
            'recommended_id':preferred['id'],'members':members,
            'auto_safe':all(set(r['statuses'])=={'verified'} for r in members)})
    groups.sort(key=lambda g:(g['venue'].casefold(),-g['year'],g['title'].casefold(),g['kind']))
    return {'digest':digest,'groups':groups,'group_count':len(groups),
            'extra_rows':sum(len(g['members'])-1 for g in groups),
            'auto_safe_groups':sum(g['auto_safe'] for g in groups)}


def _backup(db):
    database=Path(db.conn.execute('PRAGMA database_list').fetchone()['file']).resolve()
    if not database.is_file():
        raise ValueError('查重处理需要文件数据库')
    folder=database.parent/'backups'
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/('before-duplicate-cleanup-'+uuid.uuid4().hex+'.sqlite3')
    # A separate reader is necessary while the management transaction holds a
    # reserved write lock. It sees the last committed state and cannot overwrite.
    source=sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)
    target=sqlite3.connect(path)
    try:
        source.backup(target)
    finally:
        target.close();source.close()
    return str(path)


def _merge_paper(conn,keep,removed):
    primary=dict(conn.execute('SELECT * FROM award_papers WHERE id=?',(keep,)).fetchone())
    for identifier in removed:
        other=dict(conn.execute('SELECT * FROM award_papers WHERE id=?',(identifier,)).fetchone())
        for field in ('authors_raw','paper_url'):
            if not primary.get(field) and other.get(field):
                conn.execute('UPDATE award_papers SET '+field+'=? WHERE id=?',(other[field],keep))
                primary[field]=other[field]
        conn.execute('UPDATE award_event_papers SET paper_id=? WHERE paper_id=?',(keep,identifier))
        for listing in conn.execute('SELECT * FROM source_listings WHERE paper_id=?',(identifier,)).fetchall():
            collision=conn.execute('SELECT id FROM source_listings WHERE paper_id=? AND source_name=?',
                                   (keep,listing['source_name'])).fetchone()
            if collision:
                # Keep the original source row and URL, including linked record
                # evidence. Only the internal provenance label is disambiguated.
                conn.execute('UPDATE source_listings SET source_name=? WHERE id=?',
                    (listing['source_name']+' [来源副本 '+listing['id']+']',listing['id']))
            conn.execute('UPDATE source_listings SET paper_id=? WHERE id=?',(keep,listing['id']))
        conn.execute('DELETE FROM award_papers WHERE id=?',(identifier,))


def _merge_record(conn,keep,removed):
    primary=dict(conn.execute('SELECT * FROM records WHERE id=?',(keep,)).fetchone())
    payload=json.loads(primary['payload'])
    sources=json.loads(primary['sources'])
    conn.execute('INSERT INTO revisions(record_id,snapshot,archived_at) VALUES (?,?,?)',
                 (keep,json.dumps(primary,ensure_ascii=False),now()))
    for identifier in removed:
        other=dict(conn.execute('SELECT * FROM records WHERE id=?',(identifier,)).fetchone())
        secondary=json.loads(other['payload'])
        source_ids={}
        for source in json.loads(other['sources']):
            equivalent=next((s for s in sources if
                {k:v for k,v in s.items() if k!='id'}=={k:v for k,v in source.items() if k!='id'}),None)
            if equivalent:
                source_ids[source['id']]=equivalent['id']
            else:
                original_id=source['id']
                source={**source,'id':'merged:'+identifier+':'+source['id']}
                sources.append(source)
                source_ids[original_id]=source['id']
        def remap(value):
            if isinstance(value,dict):
                return {k:source_ids.get(v,v) if k=='source_id' else remap(v) for k,v in value.items()}
            if isinstance(value,list):
                return [remap(v) for v in value]
            return value
        for field in ('paper_url','doi','publication_date','authors'):
            if not payload.get(field) and secondary.get(field):
                payload[field]=remap(secondary[field])
                evidence=field+'_evidence'
                if secondary.get(evidence):
                    payload[evidence]=remap(secondary[evidence])
        for mapping in conn.execute('SELECT listing_id FROM source_listing_records WHERE record_id=?',(identifier,)):
            conn.execute('INSERT OR IGNORE INTO source_listing_records VALUES (?,?)',(mapping['listing_id'],keep))
        conn.execute('INSERT INTO revisions(record_id,snapshot,archived_at) VALUES (?,?,?)',
                     (identifier,json.dumps(other,ensure_ascii=False),now()))
        conn.execute('DELETE FROM source_listing_records WHERE record_id=?',(identifier,))
        conn.execute('DELETE FROM records WHERE id=?',(identifier,))
    conn.execute('UPDATE records SET payload=?,sources=?,updated_at=? WHERE id=?',
                 (json.dumps(payload,ensure_ascii=False),json.dumps(sources,ensure_ascii=False),now(),keep))


def _delete(conn,kind,identifiers):
    for identifier in identifiers:
        if kind=='paper':
            conn.execute('DELETE FROM source_listing_records WHERE listing_id IN (SELECT id FROM source_listings WHERE paper_id=?)',(identifier,))
            conn.execute('DELETE FROM source_listings WHERE paper_id=?',(identifier,))
            conn.execute('DELETE FROM award_event_papers WHERE paper_id=?',(identifier,))
            conn.execute('DELETE FROM award_papers WHERE id=?',(identifier,))
        else:
            row=dict(conn.execute('SELECT * FROM records WHERE id=?',(identifier,)).fetchone())
            conn.execute('INSERT INTO revisions(record_id,snapshot,archived_at) VALUES (?,?,?)',
                         (identifier,json.dumps(row,ensure_ascii=False),now()))
            conn.execute('DELETE FROM source_listing_records WHERE record_id=?',(identifier,))
            conn.execute('DELETE FROM records WHERE id=?',(identifier,))


def apply_resolutions(db,expected_digest,decisions=None,auto=False,reviewer=''):
    """Caller owns the transaction. Backup before any mutation; no pending promotion."""
    preview=duplicate_preview(db)
    if preview['digest']!=expected_digest:
        raise ValueError('数据已变化，请重新扫描重复数据')
    groups={g['id']:g for g in preview['groups']}
    if auto:
        decisions=[{'group_id':g['id'],'mode':'merge','keep_id':g['recommended_id'],
                    'delete_ids':[r['id'] for r in g['members'] if r['id']!=g['recommended_id']]}
                   for g in groups.values() if g['auto_safe']]
    if not str(reviewer).strip():
        raise ValueError('请填写处理人')
    if not decisions:
        return {'removed':0,'groups':0,'backup':None}
    validated=[]
    seen=set()
    for decision in decisions:
        group=groups.get(decision.get('group_id'))
        if not group or group['id'] in seen:
            raise ValueError('重复组不存在或重复提交，请重新扫描')
        seen.add(group['id'])
        ids={r['id'] for r in group['members']}
        removed=decision.get('delete_ids',[])
        keep=decision.get('keep_id')
        mode=decision.get('mode')
        if not isinstance(removed,list) or not removed or len(removed)!=len(set(removed)) or not set(removed)<=ids:
            raise ValueError('请选择当前重复组中需要移除的有效记录')
        if mode not in ('merge','delete') or mode=='merge' and (keep not in ids or keep in removed):
            raise ValueError('请选择要保留的记录，不能同时将其删除')
        if mode=='merge':
            # A pending or rejected variant cannot silently gain a verified
            # identity via a merge. Require explicit review before merging.
            selected=[r for r in group['members'] if r['id'] in {keep,*removed}]
            if len({tuple(r['statuses']) for r in selected})>1:
                raise ValueError('核验状态不同，请先核验，或选择单独删除，不可直接合并')
        validated.append((group,decision))
    backup=_backup(db)
    db.conn.execute('CREATE TABLE IF NOT EXISTS duplicate_actions (id TEXT PRIMARY KEY,created_at TEXT,reviewer TEXT,backup TEXT,details TEXT)')
    removed_count=0
    for group,decision in validated:
        identifiers=decision['delete_ids']
        if decision['mode']=='merge':
            (_merge_paper if group['kind']=='paper' else _merge_record)(db.conn,decision['keep_id'],identifiers)
        else:
            _delete(db.conn,group['kind'],identifiers)
        removed_count+=len(identifiers)
    if db.conn.execute('PRAGMA foreign_key_check').fetchall():
        raise ValueError('关联完整性检查失败，本次处理已取消')
    db.conn.execute('INSERT INTO duplicate_actions VALUES (?,?,?,?,?)',
        (uuid.uuid4().hex,now(),reviewer,backup,json.dumps([d for _,d in validated],ensure_ascii=False)))
    return {'removed':removed_count,'groups':len(validated),'backup':backup}
