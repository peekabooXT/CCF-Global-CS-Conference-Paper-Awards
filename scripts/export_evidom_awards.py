"""Convert the EviDOM annotation workbook into a review-pending JSON snapshot.

Usage: python scripts/export_evidom_awards.py INPUT.xlsx OUTPUT.json
The source workbook is never modified.  This is an annotation import, not
proof that any award has passed this project's independent verification.
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

from openpyxl import load_workbook


def export(source, target):
    workbook = load_workbook(source, read_only=True, data_only=True)
    pages = {row[0]: row for row in list(workbook["页面判断"].values)[1:] if row[0]}
    evidence = defaultdict(list)
    for row in list(workbook["证据"].values)[1:]:
        if not row[0] or row[1] is None:
            continue
        evidence[(row[0], int(row[1]))].append({
            "relation": row[3], "value": row[4], "alternative_group": row[5],
            "fragment": row[6], "node_id": row[7], "kind": row[8],
            "start": row[9], "end": row[10], "link_index": row[11], "quote": row[12],
        })
    records = []
    seen = set()
    for row in list(workbook["论文记录"].values)[1:]:
        if not row[0] or row[1] is None:
            continue
        page_id, index = row[0], int(row[1])
        annotation_id = row[2] or f"{page_id}-r{index:03d}"
        if annotation_id in seen:
            raise ValueError(f"重复记录编号: {annotation_id}")
        seen.add(annotation_id)
        if page_id not in pages or pages[page_id][11] != "有目标记录":
            raise ValueError(f"来源页不是目标记录页: {annotation_id}")
        records.append({
            "annotation_id": annotation_id, "page_id": page_id,
            "year": int(row[3]), "official_award_name": row[4], "title": row[5],
            "authors_raw": row[6], "paper_url": row[7], "note": row[8],
            "source_url": pages[page_id][7], "evidence": evidence[(page_id, index)],
        })
    if not records:
        raise ValueError("未找到论文标注记录")
    payload = {
        "format": "evidom-award-annotations-v1", "review_status": "pending",
        "source_workbook": Path(source).name,
        "provenance_note": "标注者 A 的研究标注；未经过本项目 B 侧独立核验，不得视为已核验获奖论文。",
        "records": records,
    }
    Path(target).parent.mkdir(parents=True, exist_ok=True)
    Path(target).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"records": len(records), "evidence_fragments": sum(len(r["evidence"]) for r in records),
            "pages": len({r["page_id"] for r in records})}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("target")
    args = parser.parse_args()
    print(json.dumps(export(args.source, args.target), ensure_ascii=False))
