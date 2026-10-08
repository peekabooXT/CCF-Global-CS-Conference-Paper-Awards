"""Generate GitHub-browsable award indexes from SQLite."""
import datetime as dt
from collections import Counter, defaultdict
from pathlib import Path
from .paper_search import search_papers
from .ontology import CATEGORIES, classify_award

AWARDS = {"best_paper": "Best Paper", "best_student_paper": "Best Student Paper"}
STATUSES = {"pending": "待核验", "verified": "已核验", "rejected": "已排除"}


def _cell(value):
    return str(value or "—").replace("|", "\\|").replace("\r", " ").replace("\n", "<br>")


def _link(label, url):
    label = _cell(label)
    return f"[{label}]({url})" if url else label


def _award_source(record):
    source_id = (record.get("award_evidence") or {}).get("source_id")
    return next((source.get("url") for source in record.get("sources", []) if source.get("id") == source_id),
                next((source.get("url") for source in record.get("sources", []) if source.get("role") in ("award", "listing")), None))


def _table(records):
    lines = [
        "| 会议/期刊 | 类型 | CCF | 类别 | 获奖年 | 奖项原名 | 论文 | 作者及单位 | 发表时间 | 状态 | 来源（官网／聚合） |",
        "| --- | --- | --- | --- | ---: | --- | --- | --- | --- | --- | --- |",
    ]
    for record in records:
        authors = "; ".join(
            author["name"] + (
                "（" + "、".join(item["name"] for item in author.get("affiliations", [])) + "）"
                if author.get("affiliations") else "（单位未知）"
            )
            for author in record.get("authors", [])
        ) or record.get("authors_raw") or "—"
        title = _link(record["title"], record.get("paper_url"))
        source = _link("来源", _award_source(record))
        lines.append("| " + " | ".join(map(_cell, [
            record["acronym"], record.get("venue_type", "会议"), record.get("rank"), record.get("area"),
            record["year"], record.get("award_name") or "来源未提供奖项原名", title, authors,
            record.get("publication_date") or "未知", STATUSES.get(record["status"], record["status"]), source,
        ])) + " |")
    return "\n".join(lines)


def _nav(prefix=""):
    return " · ".join([
        f"[会议/期刊字母排序]({prefix}AWARDS.md)",
        f"[会议/期刊类别分类检索]({prefix}docs/awards/BY_CATEGORY.md)",
        f"[年份分类检索]({prefix}docs/awards/BY_YEAR.md)",
        f"[奖项分类检索]({prefix}docs/awards/BY_AWARD.md)",
    ])


def _header(title, records, prefix="", generated_at=None):
    counts = Counter(record.get("category") or classify_award(record.get("award_name"))["category"] for record in records)
    stamp = generated_at or dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec="seconds")
    return "\n".join([
        f"# {title}", "", _nav(prefix), "",
        f"> 更新于 **{stamp}**（Asia/Shanghai）。共 **{len(records)}** 条：最佳论文奖 **{counts['paper']}** 条，最佳学生论文奖 **{counts['student']}** 条，其他获奖 **{counts['other']}** 条。奖项原名保留在下表；通过本地“审核与发布”统一更新。",
        "",
    ]) + "\n"


def acknowledgements_markdown():
    """Keep acknowledgements in every index, including future local publications."""
    return (
        "\n## 致谢\n\n"
        "感谢[湖南科技大学](https://www.hnust.edu.cn/)、"
        "[湖南科技大学计算机科学与工程学院](https://computer.hnust.edu.cn/)以及"
        "服务计算与软件服务新技术湖南省重点实验室提供的学习与科研环境。\n\n"
        "特别感谢[刘建勋](https://faculty.hnust.edu.cn/pubtphp/jsjkxygcxy/1050037/chinese/index.html)教授、"
        "[王焕宇](https://faculty.hnust.edu.cn/pubtphp/jsjkxygcxy/1050148/chinese/index.html)教授、"
        "[黄晶](https://faculty.hnust.edu.cn/pubtphp/jsjkxygcxy/1050135/chinese/index.html)教授"
        "在本项目建设过程中的帮助、指导与把关。谨向三位老师致以诚挚的谢意。\n"
    )


def render_markdown(db, repository_root, status="all", generated_at=None):
    root = Path(repository_root)
    docs = root / "docs" / "awards"
    docs.mkdir(parents=True, exist_ok=True)
    records = search_papers(db, {"status": status})

    alphabetical = sorted(records, key=lambda r: (r["acronym"].casefold(), -r["year"], r["title"].casefold(), r["award_type"]))
    main = _header("Global CS Paper Awards Agent：获奖论文索引", alphabetical, generated_at=generated_at)
    main += "## 会议/期刊字母排序检索\n\n"
    main += "当前数据源以 CCF A/B 会议为主；期刊接入后将使用同一字段和索引。\n\n"
    main += _table(alphabetical) + "\n"
    (root / "AWARDS.md").write_text(main + acknowledgements_markdown(), encoding="utf-8")

    by_category = defaultdict(list)
    for record in records:
        by_category[record.get("area") or "未分类"].append(record)
    page = _header("按会议/期刊类别检索", records, "../../", generated_at)
    page += "## 类别目录\n\n" + "\n".join(f"- [{_cell(category)}](#{category.replace(' ', '-').lower()})" for category in sorted(by_category)) + "\n\n"
    for category in sorted(by_category):
        page += f"## {category}\n\n" + _table(sorted(by_category[category], key=lambda r: (r["acronym"].casefold(), -r["year"], r["title"].casefold()))) + "\n\n"
    (docs / "BY_CATEGORY.md").write_text(page + acknowledgements_markdown(), encoding="utf-8")

    by_year = defaultdict(list)
    for record in records:
        by_year[record["year"]].append(record)
    page = _header("按获奖年份检索", records, "../../", generated_at)
    page += "## 年份目录\n\n" + " · ".join(f"[{year}](#{year})" for year in sorted(by_year, reverse=True)) + "\n\n"
    for year in sorted(by_year, reverse=True):
        page += f"## {year}\n\n" + _table(sorted(by_year[year], key=lambda r: (r["acronym"].casefold(), r["title"].casefold()))) + "\n\n"
    (docs / "BY_YEAR.md").write_text(page + acknowledgements_markdown(), encoding="utf-8")

    by_award = defaultdict(list)
    for record in records:
        by_award[record.get("category") or classify_award(record.get("award_name"))["category"]].append(record)
    page = _header("按奖项类型检索", records, "../../", generated_at)
    for award_type in CATEGORIES:
        group = sorted(by_award[award_type], key=lambda r: (r["acronym"].casefold(), -r["year"], r["title"].casefold()))
        page += f"## {CATEGORIES[award_type]}\n\n" + _table(group) + "\n\n"
    (docs / "BY_AWARD.md").write_text(page + acknowledgements_markdown(), encoding="utf-8")

    return {"records": len(records), "files": [str(root / "AWARDS.md"), str(docs / "BY_CATEGORY.md"), str(docs / "BY_YEAR.md"), str(docs / "BY_AWARD.md")]}
