"""Read-only conversion of the supplied JeffHuang workbook to a source snapshot."""

import argparse
import hashlib
import json
from pathlib import Path

from openpyxl import load_workbook


def export(source, target):
    source = Path(source)
    book = load_workbook(source, read_only=True, data_only=True)
    header = list(book["Papers"].values)[3]
    expected = ("序号", "年份", "会议", "领域", "获奖论文题目", "作者及单位（网页列示）", "页面来源")
    if tuple(header[:7]) != expected:
        raise ValueError("JeffHuang 论文表字段与预期不符")
    source_url = "https://jeffhuang.com/best_paper_awards/"
    rows = []
    for values in list(book["Papers"].values)[4:]:
        if not values or values[0] is None:
            continue
        number, year, venue, area, title, authors, discovery_url = values[:7]
        if not all((number, year, venue, title)):
            raise ValueError(f"第 {len(rows)+5} 行缺少必要数据")
        rows.append({"source_row": int(number), "year": int(year), "venue": str(venue).strip(),
                     "area_raw": area, "title": str(title).strip(),
                     "authors_raw": authors, "discovery_url": discovery_url})
    if len({r["source_row"] for r in rows}) != len(rows):
        raise ValueError("网站收录序号重复")
    document = {"format": "jeffhuang-listings-v1", "source_name": "jeffhuang",
                "source_url": source_url, "source_workbook": source.name,
                "source_workbook_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "provenance_note": "网站聚合收录；逐条官方奖项名称和授奖证据未在本表提供。页面来源列是 Google Scholar 检索链接，不是论文正文或官方奖项证据。",
                "rows": rows}
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"rows": len(rows), "years": [min(r["year"] for r in rows), max(r["year"] for r in rows)],
            "venues": len({r["venue"] for r in rows})}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("target")
    args = parser.parse_args()
    print(json.dumps(export(args.source, args.target), ensure_ascii=False))
