"""Import an annotation snapshot with its recorded review status into SQLite."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ccf_awards.award_events import import_annotations
from ccf_awards.db import Database


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("snapshot")
    parser.add_argument("database")
    args = parser.parse_args()
    db = Database(args.database)
    try:
        db.init()
        result = import_annotations(db.conn, json.loads(Path(args.snapshot).read_text(encoding="utf-8")))
        print(json.dumps(result, ensure_ascii=False))
    finally:
        db.close()
