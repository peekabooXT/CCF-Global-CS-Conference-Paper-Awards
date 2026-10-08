"""Read-only CI check; collection and human review happen on the local computer."""
import json
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from global_cs_paper_awards_agent.public_data import PUBLIC_TABLES, write_public_database

root = Path(__file__).resolve().parents[1]
path = root / 'data/exports/public-data.json'
if not path.is_file():
    print('No v2 public publication yet; the local publication button will create it.')
else:
    data = json.loads(path.read_text(encoding='utf-8'))
    assert data['schema_version'] == 2
    assert set(data['tables']) == set(PUBLIC_TABLES)
    for table in ('records', 'award_events', 'award_event_papers', 'source_listings'):
        assert all(row['status'] == 'verified' for row in data['tables'][table])
    manifest = json.loads((root / 'data/exports/publication.json').read_text(encoding='utf-8'))
    assert manifest == data['publication']
    for name in ('AWARDS.md', 'docs/awards/BY_AWARD.md', 'docs/awards/BY_CATEGORY.md', 'docs/awards/BY_YEAR.md'):
        assert manifest['published_at'] in (root / name).read_text(encoding='utf-8')
    with tempfile.TemporaryDirectory() as temp:
        write_public_database(data, Path(temp) / 'public.sqlite3')
    print('Public snapshot and all four index timestamps are consistent.')
