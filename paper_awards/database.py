"""Read-only public repository. No collection, review or coverage operations."""
import json
import sqlite3
from pathlib import Path
from .model import norm

class Database:

    def __init__(self, path):
        self.conn = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
        self.conn.row_factory = sqlite3.Row
        self.conn.create_function('fold', 1, lambda x: norm(x or ''), deterministic=True)
        self.conn.execute('PRAGMA query_only=ON')

    def close(self):
        self.conn.close()

    def conferences(self):
        return [json.loads(r[0]) for r in self.conn.execute('SELECT data FROM conferences ORDER BY area,rank,acronym')]

    def search(self, conference=None, rank=None, year_from=None, year_to=None, author=None, affiliation=None, title=None, award=None, status='verified', published_from=None, published_to=None):
        where, args = (["r.status='verified'"], [])
        for field, value, op in [('r.conference_id', conference, '='), ('c.rank', rank, '='), ('r.year', year_from, '>='), ('r.year', year_to, '<='), ('r.award_type', award, '='), ('r.date_end', published_from, '>='), ('r.date_start', published_to, '<=')]:
            if value is not None:
                where.append(f'{field} {op} ?')
                args.append(value)
        if title:
            where.append('instr(fold(r.title),?)>0')
            args.append(norm(title))
        sql = 'SELECT r.*,c.acronym,c.rank,c.area FROM records r JOIN conferences c ON c.id=r.conference_id WHERE '
        sql += ' AND '.join(where) + ' ORDER BY r.year DESC,fold(c.acronym),fold(r.title),r.award_type'
        result = []
        for row in self.conn.execute(sql, args):
            item = json.loads(row['payload'])
            if author or affiliation:
                if not any(((not author or norm(author) in norm(a['name'])) and (not affiliation or any((norm(affiliation) in norm(b['name']) for b in a['affiliations']))) for a in item['authors'])):
                    continue
            item.update(acronym=row['acronym'], rank=row['rank'], area=row['area'], status='verified', sources=json.loads(row['sources']), updated_at=row['updated_at'])
            result.append(item)
        return result
