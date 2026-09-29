"""Reclassify stored Award Events under the current broad ontology."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ccf_awards.award_events import reclassify_events
from ccf_awards.db import Database
from ccf_awards.ontology import CATEGORIES


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("database")
    args = parser.parse_args()
    db = Database(args.database)
    try:
        changed = reclassify_events(db.conn)
        counts = dict(db.conn.execute("SELECT category,COUNT(*) FROM award_events GROUP BY category"))
        print(json.dumps({"changed": changed, "categories": counts,
                          "category_limit": len(CATEGORIES)}, ensure_ascii=False))
    finally:
        db.close()
