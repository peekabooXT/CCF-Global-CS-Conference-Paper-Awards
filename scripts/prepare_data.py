"""Build a local read-only database from the versioned, reviewed data snapshot."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from paper_awards.snapshot import write_public_database

snapshot = json.loads((ROOT / 'data/exports/public-data.json').read_text(encoding='utf-8'))
destination = ROOT / 'data/public.sqlite3'
if destination.exists():
    raise SystemExit('Database already exists; preserve or move it before preparing a newer snapshot.')
write_public_database(snapshot, destination)
(ROOT / 'data/publication.json').write_text(json.dumps(snapshot['publication'], ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('Prepared read-only display database.')
