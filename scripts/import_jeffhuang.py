"""Import the JeffHuang source snapshot into the local SQLite DB."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from global_cs_paper_awards_agent.db import Database
from global_cs_paper_awards_agent.source_listings import import_jeffhuang


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot")
    parser.add_argument("database")
    args = parser.parse_args()
    db = Database(args.database)
    try:
        db.init()
        result = import_jeffhuang(db.conn, json.loads(Path(args.snapshot).read_text(encoding="utf-8")))
        print(json.dumps(result, ensure_ascii=False))
    finally:
        db.close()
