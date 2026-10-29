"""Validate reviewed data, index timestamps and the independently runnable viewer."""
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from paper_awards.database import Database
from paper_awards.paper_search import search_papers
from paper_awards.snapshot import PUBLIC_TABLES, write_public_database

snapshot = json.loads((ROOT / 'data/exports/public-data.json').read_text(encoding='utf-8'))
assert snapshot['schema_version'] == 2
assert set(snapshot['tables']) == set(PUBLIC_TABLES)
assert snapshot['publication'] == json.loads((ROOT / 'data/exports/publication.json').read_text(encoding='utf-8'))
for table in ('records', 'award_events', 'award_event_papers', 'source_listings'):
    assert all(row['status'] == 'verified' for row in snapshot['tables'][table])
for name in ('AWARDS.md', 'docs/awards/BY_AWARD.md', 'docs/awards/BY_CATEGORY.md', 'docs/awards/BY_YEAR.md'):
    assert snapshot['publication']['published_at'] in (ROOT / name).read_text(encoding='utf-8')
with tempfile.TemporaryDirectory() as temp:
    path = Path(temp) / 'public.sqlite3'
    write_public_database(snapshot, path)
    db = Database(path)
    try:
        rows = search_papers(db, {'status': 'verified'})
        assert len(rows) == snapshot['publication']['paper_results']
        try:
            db.conn.execute('DELETE FROM records')
            raise AssertionError('Database accepted a write')
        except sqlite3.OperationalError:
            pass
    finally:
        db.close()
print(f'Validated {len(rows):,} reviewed papers and four index timestamps; database is read-only.')
