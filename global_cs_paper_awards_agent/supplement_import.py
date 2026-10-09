"""Import explicitly reviewed award/link supplements without duplicating papers.

Workbook exports preserve original titles and row locations. A canonical_title
is only used for the exact, manually reviewed spelling variants in the export.
No fuzzy matches or bulk review of the workbench are performed here.
"""
import json
from collections import defaultdict
from urllib.parse import urlsplit

from .model import keytext, norm, url_syntax, now
from .ontology import classify_award
from .award_events import _id
from .source_listings import _alias_map


def external_address(value):
    if not value:
        return None
    url_syntax(value)
    host = urlsplit(value).hostname.lower().rstrip('.')
    import ipaddress
    if host in {'localhost', '47.107.172.42'} or host.endswith(('.localhost', '.local')):
        raise ValueError('补充地址必须指向外部公开网站')
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return value
    if not address.is_global:
        raise ValueError('补充地址不能指向本地或内网')
    return value


def import_supplement(db, document):
    if document.get('format') != 'reviewed-public-link-supplement-v1':
        raise ValueError('不支持的补充数据格式')
    if document.get('review_status') != 'verified' or not document.get('verification_note'):
        raise ValueError('补充数据必须有明确的已核验确认依据')
    rows = document.get('records')
    if not isinstance(rows, list):
        raise ValueError('records 必须是列表')
    stamp = document.get('imported_at') or now()
    stats = dict(rows=len(rows), new_papers=0, new_events=0, new_award_links=0,
                 annotations=0, paper_urls_updated=0, core_records_updated=0)
    conferences = {r['id']: r['acronym'] for r in db.conn.execute('SELECT id,acronym FROM conferences')}
    aliases = _alias_map(db.conn)
    papers = defaultdict(list)
    for p in db.conn.execute('SELECT * FROM award_papers'):
        papers[(aliases.get(norm(p['venue']), norm(p['venue'])), p['year'], keytext(p['title']))].append(dict(p))
    core = defaultdict(list)
    for r in db.conn.execute("SELECT * FROM records WHERE status='verified'"):
        core[(r['conference_id'], r['year'], keytext(r['title']))].append(dict(r))
    seen = set()
    preferred_urls = {}
    for row in rows:
        if row.get('paper_url') and row.get('conference_id') in conferences:
            identity = (row['conference_id'], row['year'],
                        keytext(str(row.get('canonical_title') or row['title']).strip()))
            preferred_urls[identity] = external_address(row['paper_url'])
    # Atomic validation and import; a later invalid row rolls back earlier changes.
    with db.conn:
        for row in rows:
            cid, year = row['conference_id'], row['year']
            if cid not in conferences or type(year) is not int or not 1900 <= year <= 2200:
                raise ValueError('会议或年份无效')
            venue = conferences[cid]
            title = str(row.get('canonical_title') or row['title']).strip()
            name = str(row['award_name']).strip()
            if not title or not name:
                raise ValueError('论文题名或奖项原名为空')
            source = external_address(row['source_url'])
            if not source:
                raise ValueError('缺少获奖来源')
            supplied_url = external_address(row.get('paper_url'))
            category = classify_award(name)
            identity = (cid, year, keytext(title))
            paper_url = preferred_urls.get(identity)
            source_identity = (row['sheet'], row['row'])
            if source_identity in seen:
                raise ValueError('补充表行号重复')
            seen.add(source_identity)
            matches = papers[identity]
            if len(matches) > 1:
                exact_titles = [p for p in matches if norm(p['title']) == norm(title)]
                if exact_titles:
                    matches = exact_titles
            if len(matches) > 1:
                canonical_venues = [p for p in matches if norm(p['venue']) == norm(venue)]
                if len(canonical_venues) == 1:
                    matches = canonical_venues
            # Multiple IDs are ambiguous; never silently rewrite their identities.
            if len(matches) > 1:
                raise ValueError(f'同一论文存在多个 ID，需要先核对：{title}')
            original_core = core[identity]
            if matches:
                paper = matches[0]
                pid = paper['id']
            else:
                pid = _id(venue, year, norm(title))
                paper = dict(id=pid, venue=venue, year=year, title=title,
                             authors_raw=row.get('authors_raw'), paper_url=None)
                db.conn.execute('INSERT INTO award_papers VALUES (?,?,?,?,?,?)', tuple(paper.values()))
                papers[identity].append(paper)
                if not original_core:
                    stats['new_papers'] += 1
            previous_url = paper['paper_url']
            if paper_url and paper_url != previous_url:
                db.conn.execute('UPDATE award_papers SET paper_url=? WHERE id=?', (paper_url, pid))
                paper['paper_url'] = paper_url
                stats['paper_urls_updated'] += 1
            if not paper['authors_raw'] and row.get('authors_raw'):
                db.conn.execute('UPDATE award_papers SET authors_raw=? WHERE id=?', (row['authors_raw'], pid))
                paper['authors_raw'] = row['authors_raw']

            candidates = [dict(e) for e in db.conn.execute('''SELECT DISTINCT e.* FROM award_events e
                JOIN award_event_papers x ON x.event_id=e.id
                WHERE x.paper_id=? AND x.status='verified' ORDER BY e.id''', (pid,))
                if classify_award(e['official_award_name'])['category'] == category['category']]
            exact = [e for e in candidates if norm(e['official_award_name']) == norm(name)]
            # Generic workbook labels supplement existing specific track names.
            selected = (exact or candidates)
            if selected:
                event = selected[0]
                eid = event['id']
            else:
                same_category_core = [r for r in original_core
                    if classify_award(json.loads(r['payload']).get('award_name'))['category'] == category['category']]
                if same_category_core:
                    name = json.loads(same_category_core[0]['payload']).get('award_name') or name
                eid = _id(venue, year, norm(name))
                if not db.conn.execute('SELECT 1 FROM award_events WHERE id=?', (eid,)).fetchone():
                    label = classify_award(name)
                    db.conn.execute('INSERT INTO award_events VALUES (?,?,?,?,?,?,?,?,?)',
                        (eid, venue, cid, year, name, label['category'], int(label['student_only']), 'verified', stamp))
                    stats['new_events'] += 1
            linked = db.conn.execute('SELECT 1 FROM award_event_papers WHERE event_id=? AND paper_id=?', (eid, pid)).fetchone()
            if not linked and not original_core:
                stats['new_award_links'] += 1
            aid = 'supplement:' + _id(document['source_sha256'], row['sheet'], row['row'])
            evidence = [{'kind': 'reviewed_workbook_row', 'quote': f"{row['award_name']}: {row['title']}",
                'workbook': document['source_workbook'], 'sheet': row['sheet'], 'row': row['row'],
                'verification_note': document['verification_note'], 'source_url': source,
                'paper_url': supplied_url, 'original_title': row['title']}]
            if previous_url and previous_url != paper_url:
                evidence[0]['previous_paper_url'] = previous_url
            # Stable evidence on reimport: keep the original pre-import URL history.
            old = db.conn.execute('SELECT * FROM award_event_papers WHERE annotation_id=?', (aid,)).fetchone()
            if old:
                prior = json.loads(old['evidence'])
                evidence[0].pop('previous_paper_url', None)
                if prior and prior[0].get('previous_paper_url'):
                    evidence[0]['previous_paper_url'] = prior[0]['previous_paper_url']
            values = (aid, eid, pid, source, f"{row['sheet']}:{row['row']}",
                      json.dumps(evidence, ensure_ascii=False, sort_keys=True), document['verification_note'], 'verified')
            if not old or tuple(old) != values:
                db.conn.execute('''INSERT INTO award_event_papers VALUES (?,?,?,?,?,?,?,?)
                    ON CONFLICT(annotation_id) DO UPDATE SET evidence=excluded.evidence,note=excluded.note''', values)
                stats['annotations'] += 1
            for record in original_core:
                payload = json.loads(record['payload'])
                sources = json.loads(record['sources'])
                old_payload, old_sources = record['payload'], record['sources']
                # Supplement metadata only; keep title, original awards and review decisions.
                if paper_url:
                    if not payload.get('paper_url') or urlsplit(payload['paper_url']).hostname == 'scholar.google.com':
                        payload['paper_url'] = paper_url
                    if not any(s['url'] == paper_url for s in sources):
                        sources.append({'id': 'supplement-' + _id(paper_url), 'role': 'paper', 'url': paper_url})
                if not any(s['url'] == source for s in sources):
                    sources.append({'id': 'supplement-' + _id(source), 'role': 'award', 'url': source})
                new_payload = json.dumps(payload, ensure_ascii=False, sort_keys=True)
                new_sources = json.dumps(sources, ensure_ascii=False, sort_keys=True)
                if json.loads(old_payload) != payload or json.loads(old_sources) != sources:
                    db.conn.execute('INSERT INTO revisions(record_id,snapshot,archived_at) VALUES (?,?,?)',
                                    (record['id'], json.dumps(record, ensure_ascii=False), stamp))
                    db.conn.execute('UPDATE records SET payload=?,sources=?,updated_at=? WHERE id=?',
                                    (new_payload, new_sources, stamp, record['id']))
                    record.update(payload=new_payload, sources=new_sources, updated_at=stamp)
                    stats['core_records_updated'] += 1
        if db.conn.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('补充数据关联完整性错误')
    return stats
