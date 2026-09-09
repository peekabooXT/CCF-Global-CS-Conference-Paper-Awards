"""Parse the supplied DOCX without requiring Microsoft Word or python-docx."""
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

DEFAULT_CATALOG = Path(__file__).resolve().parent.parent / "data" / "conferences.json"


def parse_docx(path):
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    lines = ["".join(t.text or "" for t in p.findall(".//w:t", ns)).strip()
             for p in root.findall(".//w:p", ns)]
    area, rank, rows, expected = None, None, [], Counter()
    for line in lines:
        if line.startswith("【"):
            area = line.split("】", 1)[1].strip()
        match = re.search(r"---\s*([AB])\s*类[（(](\d+)[）)]", line)
        if match:
            rank = match[1]
            expected[rank] += int(match[2])
            continue
        match = re.match(r"^\d+\.\s+(.+)", line)
        if not match:
            continue
        if not area or not rank:
            raise ValueError("会议缺少所属领域或等级")
        cells = re.split(r"\s{2,}", match[1])
        if len(cells) != 3:
            raise ValueError(f"无法解析会议行，请检查文档格式：{line}")
        short, full, publisher = cells
        aliases = [short]
        if "原 USENIX ATC" in short:
            short = "ACM SIGOPS ATC"
            aliases += [short, "USENIX ATC", "ATC"]
        if short == "SIGKDD":
            aliases.append("KDD")
        if short == "NeurIPS":
            aliases.append("NIPS")
        slug = re.sub(r"[^a-z0-9]+", "-", short.lower()).strip("-")
        uid = slug + "-" + hashlib.sha256(full.encode()).hexdigest()[:6]
        rows.append(dict(id=uid, acronym=short, full_name=full, rank=rank,
                         area=area, publisher=publisher, aliases=aliases,
                         catalog_version="user-supplied-2026", source=Path(path).name))
    actual = Counter(r["rank"] for r in rows)
    if not rows or actual != expected:
        raise ValueError(f"行数校验不通过：解析 {dict(actual)}，文档分组 {dict(expected)}")
    if len({r["id"] for r in rows}) != len(rows):
        raise ValueError("会议完整名称存在重复，请人工处理")
    return rows


def load_catalog(path=None):
    return json.loads(Path(path or DEFAULT_CATALOG).read_text(encoding="utf-8"))
