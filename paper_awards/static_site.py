"""Freeze the reviewed reader data into cacheable files at publication time."""
import hashlib
import base64
import gzip
import json
import re
from collections import defaultdict
from pathlib import Path

from .model import norm
from .ontology import CATEGORIES, classify_award
from .paper_search import (search_paper_records, merge_paper_results, conference_aliases,
                           paper_identity, _record_provenance, _with_discovery_urls, award_names)
from .award_events import list_events, event_detail
from .web_helpers import AWARDS

SCRIPT_ID = 'awards-static-data'
SUMMARY_FIELDS = ('id','source_kind','event_id','title','acronym','rank','area','year',
                  'conference_id','award_name','award_type','category','category_label',
                  'student_only','status','authors','authors_raw','publication_date',
                  'date_precision','date_start','date_end','paper_url','doi','sources',
                  'discovery_url','_group','_duplicate_key','_legacy')


def compact(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def write_static_site(db, publication, destination):
    """Use only the public read-only database; never inspect the workbench."""
    destination = Path(destination)
    index = destination / 'index.html'
    if not index.is_file():
        raise ValueError('Build the reader frontend before generating static data.')
    db.conn.execute('PRAGMA temp_store=MEMORY')
    for table in ('records','award_events','award_event_papers','source_listings'):
        if db.conn.execute(f"SELECT 1 FROM {table} WHERE status IS NULL OR status!='verified' LIMIT 1").fetchone():
            raise ValueError('Static reader input must contain only verified public data.')

    aliases = conference_aliases(db.conn)
    rows = search_paper_records(db, {'status':'verified'})
    merged = merge_paper_results(rows, aliases)
    if publication.get('paper_results') != len(merged):
        raise ValueError('Static paper count differs from the publication manifest.')

    # Retain source-level variants so filtering precedes merging, just as in SQL.
    # An event suppressed by a structured record can still match an author query.
    class EventsOnly:
        conn = db.conn
        def search(self, **filters):return []
    core = db.search(status='verified')
    for row in core:row.update(classify_award(row.get('award_name')))
    core = _with_discovery_urls(db.conn, core)
    atoms = [*core, *search_paper_records(EventsOnly(), {'status':'verified'})]
    atoms.sort(key=lambda r:(-r['year'],norm(r['acronym']),norm(r['title']),norm(r.get('award_name') or '')))
    group_index = {paper_identity(aliases,r['acronym'],r['year'],r['title'],r.get('conference_id')):i for i,r in enumerate(merged)}
    core_ids = {r['id'] for r in core}
    for row in atoms:
        key = paper_identity(aliases,row['acronym'],row['year'],row['title'],row.get('conference_id'))
        row['_group'] = group_index[key]
        row['_legacy'] = row['id'] in core_ids
        row['_duplicate_key'] = compact([row.get('conference_id') or norm(row['acronym']),row['year'],norm(row['title']),norm(row.get('award_name') or '')])

    assets = destination / 'assets';assets.mkdir(exist_ok=True)
    generated = []
    def module(label, data):
        raw = compact(data).encode('utf-8')
        content = b'export default '+raw+b';\n'
        plain = f'static-{label}-plain-{hashlib.sha256(content).hexdigest()[:16]}.js'
        (assets/plain).write_bytes(content);generated.append((plain,len(content)))
        packed = {'gzip':base64.b64encode(gzip.compress(raw,mtime=0)).decode('ascii'),'fallback':'assets/'+plain}
        content = ('export default '+compact(packed)+';\n').encode('utf-8')
        name = f'static-{label}-{hashlib.sha256(content).hexdigest()[:16]}.js'
        (assets/name).write_bytes(content);generated.append((name,len(content)))
        return 'assets/'+name

    catalog = module('papers', {'columns':SUMMARY_FIELDS,'rows':[[r.get(k) for k in SUMMARY_FIELDS] for r in atoms]})
    paper_chunks = {}
    provenance_cache = {}
    def provenance(identifier):
        if identifier not in provenance_cache:
            provenance_cache[identifier] = _record_provenance(db.conn,identifier) or {'listings':[]}
        return provenance_cache[identifier]
    for start in range(0,len(merged),48):
        chunk = {}
        for group,row in enumerate(merged[start:start+48],start):
            listings = {listing['id']:listing for identifier in row['related_record_ids'] for listing in provenance(identifier)['listings']}
            chunk[group] = {'record':row,'listings':list(listings.values()),'awards':row['awards']}
        paper_chunks[start//48] = module(f'papers-detail-{start//48}',chunk)

    events=[]
    offset=0
    while True:
        page=list_events(db.conn,limit=500,offset=offset)
        events.extend(page['events']);offset+=len(page['events'])
        if offset>=page['total']:break
    event_chunks={}
    for start in range(0,len(events),32):
        chunk={}
        for event in events[start:start+32]:
            detail=event_detail(db.conn,event['id']);chunk[event['id']]=detail
            event['_query']=[norm(event['official_award_name']),*[norm(p['title']) for p in detail['papers']]]
            event['_chunk']=start//32
        event_chunks[start//32]=module(f'events-detail-{start//32}',chunk)
    event_catalog=module('events',events)
    bootstrap={'schema_version':1,'meta':{'mode':'public','delivery':'static','awards':AWARDS,'statuses':{'verified':'已核验'},
               'conferences':db.conferences(),'award_categories':CATEGORIES,'award_names':award_names(db.conn),'publication':publication},
               'catalog':catalog,'events':event_catalog,'paper_chunks':paper_chunks,'event_chunks':event_chunks,'paper_chunk_size':48}
    html=index.read_text(encoding='utf-8')
    html=re.sub(r'<script\b[^>]*\bid=["\']'+SCRIPT_ID+r'["\'][^>]*>.*?</script>\s*','',html,flags=re.S)
    payload=compact(bootstrap).replace('<','\\u003c').replace('\u2028','\\u2028').replace('\u2029','\\u2029')
    html=html.replace('</head>',f'<script id="{SCRIPT_ID}" type="application/json">{payload}</script>\n</head>')
    index.write_bytes(html.encode('utf-8'))
    current = {name for name,_ in generated}
    for old in assets.glob('static-*.js'):
        if old.name not in current:old.unlink()
    return {'papers':len(merged),'source_rows':len(atoms),'events':len(events),'files':len(generated),
            'catalog_bytes':next(size for name,size in generated if catalog.endswith(name)),
            'total_data_bytes':sum(size for _,size in generated)}
