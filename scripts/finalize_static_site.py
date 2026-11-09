"""Generate static reader assets from the versioned reviewed snapshot."""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
if (ROOT/'paper_awards').is_dir():
    from paper_awards.database import Database
    from paper_awards.snapshot import write_public_database
    from paper_awards.static_site import write_static_site
else:
    from global_cs_paper_awards_agent.public_db import Database
    from global_cs_paper_awards_agent.public_data import write_public_database
    from global_cs_paper_awards_agent.static_site import write_static_site

def main():
    destination=Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory() as temp:
        if os.getenv('AWARDS_STATIC_DB'):
            database=Path(os.environ['AWARDS_STATIC_DB'])
            publication=json.loads(Path(os.environ['AWARDS_STATIC_PUBLICATION']).read_text(encoding='utf-8'))
        else:
            snapshot=json.loads((ROOT/'data/exports/public-data.json').read_text(encoding='utf-8'))
            publication=snapshot['publication']
            database=Path(temp)/'public.sqlite3';write_public_database(snapshot,database)
        db=Database(database)
        try:result=write_static_site(db,publication,destination)
        finally:db.close()
    print(json.dumps(result,ensure_ascii=True),flush=True)

if __name__=='__main__':main()
