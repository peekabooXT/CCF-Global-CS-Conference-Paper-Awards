import hashlib
import json
import re
from .model import norm
from .ontology import CATEGORIES, classify_award

def list_events(conn, venue='', category='', query='', limit=100, offset=0):
    if category and category not in CATEGORIES:
        raise ValueError('未知奖项分类')
    if not 1 <= limit <= 500 or offset < 0:
        raise ValueError('分页参数不正确')
    clauses, args = ([], [])
    if venue:
        clauses.append('instr(fold(e.venue),?)>0')
        args.append(norm(venue))
    if category:
        conn.create_function('award_category', 1, lambda name: classify_award(name)['category'])
        clauses.append("(CASE WHEN e.category IN ('paper','student','other') THEN e.category ELSE award_category(e.official_award_name) END)=?")
        args.append(category)
    if query:
        clauses.append('(instr(fold(e.official_award_name),?)>0 OR EXISTS (SELECT 1 FROM award_event_papers x JOIN award_papers p ON p.id=x.paper_id WHERE x.event_id=e.id AND instr(fold(p.title),?)>0))')
        args.extend([norm(query), norm(query)])
    where = ' WHERE ' + ' AND '.join(clauses) if clauses else ''
    total = conn.execute('SELECT COUNT(*) FROM award_events e' + where, args).fetchone()[0]
    sql = 'SELECT e.*,c.rank,COUNT(x.annotation_id) AS annotation_count,\n      COUNT(DISTINCT x.paper_id) AS paper_count FROM award_events e\n      LEFT JOIN conferences c ON c.id=e.conference_id\n      LEFT JOIN award_event_papers x ON x.event_id=e.id' + where + ' GROUP BY e.id ORDER BY e.year DESC,e.venue,e.official_award_name LIMIT ? OFFSET ?'
    rows = [dict(r) for r in conn.execute(sql, [*args, limit, offset])]
    for event in rows:
        if event['category'] not in CATEGORIES:
            event.update(classify_award(event['official_award_name']))
        event['category_label'] = CATEGORIES[event['category']]
    return {'total': total, 'events': rows}

def event_detail(conn, event_id):
    row = conn.execute('SELECT e.*,c.rank FROM award_events e LEFT JOIN conferences c ON c.id=e.conference_id WHERE e.id=?', (event_id,)).fetchone()
    if not row:
        return None
    event = dict(row)
    if event['category'] not in CATEGORIES:
        event.update(classify_award(event['official_award_name']))
    event['category_label'] = CATEGORIES[event['category']]
    event['papers'] = []
    for r in conn.execute('SELECT p.*,x.annotation_id,x.source_url,x.source_page_id,x.evidence,x.note,x.status\n        FROM award_event_papers x JOIN award_papers p ON p.id=x.paper_id\n        WHERE x.event_id=? ORDER BY p.title,x.annotation_id', (event_id,)):
        paper = dict(r)
        paper['evidence'] = json.loads(paper['evidence'])
        event['papers'].append(paper)
    return event
