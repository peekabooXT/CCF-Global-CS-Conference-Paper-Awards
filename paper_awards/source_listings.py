import hashlib
import json
from .model import keytext, norm, url_syntax

def list_source_listings(conn, venue='', query='', relation='', limit=50, offset=0):
    if relation not in ('', 'event', 'record', 'new'):
        raise ValueError('未知关联筛选')
    if not 1 <= limit <= 500 or offset < 0:
        raise ValueError('分页参数不正确')
    where, args = ([], [])
    if venue:
        where.append('instr(fold(l.source_venue),?)>0')
        args.append(norm(venue))
    if query:
        where.append('(instr(fold(p.title),?)>0 OR instr(fold(l.authors_raw),?)>0)')
        args.extend([norm(query), norm(query)])
    has_event = 'EXISTS (SELECT 1 FROM award_event_papers x WHERE x.paper_id=l.paper_id)'
    has_record = 'EXISTS (SELECT 1 FROM source_listing_records z WHERE z.listing_id=l.id)'
    if relation == 'event':
        where.append(has_event)
    elif relation == 'record':
        where.append(has_record)
    elif relation == 'new':
        where.append('NOT ' + has_event + ' AND NOT ' + has_record)
    clause = ' WHERE ' + ' AND '.join(where) if where else ''
    total = conn.execute('SELECT COUNT(*) FROM source_listings l JOIN award_papers p ON p.id=l.paper_id' + clause, args).fetchone()[0]
    sql = 'SELECT l.*,p.title,p.year,p.paper_url,c.rank,\n      (SELECT COUNT(DISTINCT x.event_id) FROM award_event_papers x WHERE x.paper_id=l.paper_id) AS event_count,\n      (SELECT COUNT(*) FROM source_listing_records z WHERE z.listing_id=l.id) AS record_count\n      FROM source_listings l JOIN award_papers p ON p.id=l.paper_id\n      LEFT JOIN conferences c ON c.id=l.conference_id' + clause + ' ORDER BY p.year DESC,l.source_venue,l.source_row LIMIT ? OFFSET ?'
    return {'total': total, 'listings': [dict(r) for r in conn.execute(sql, [*args, limit, offset])]}

def source_listing_detail(conn, listing_id):
    row = conn.execute('SELECT l.*,p.title,p.year,p.paper_url FROM source_listings l\n        JOIN award_papers p ON p.id=l.paper_id WHERE l.id=?', (listing_id,)).fetchone()
    if row is None:
        return None
    item = dict(row)
    item['events'] = [dict(r) for r in conn.execute('SELECT DISTINCT e.id,e.official_award_name,e.category,e.status\n        FROM award_events e JOIN award_event_papers x ON x.event_id=e.id\n        WHERE x.paper_id=? ORDER BY e.official_award_name', (item['paper_id'],))]
    item['records'] = [dict(r) for r in conn.execute('SELECT r.id,r.award_type,r.status\n        FROM records r JOIN source_listing_records z ON z.record_id=r.id\n        WHERE z.listing_id=? ORDER BY r.id', (listing_id,))]
    return item
