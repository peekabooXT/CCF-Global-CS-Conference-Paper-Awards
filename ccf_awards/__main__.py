import argparse
import csv
import datetime as dt
import json
import os
import sqlite3
import sys
from pathlib import Path
from .catalog import DEFAULT_CATALOG, parse_docx
from .db import Database
from .model import require_text, url_syntax

AWARD_LABELS = {"best_paper": "最佳论文奖", "best_student_paper": "最佳学生论文奖"}
STATUS_LABELS = {"pending": "待核验", "verified": "已核验", "rejected": "已排除"}


def dump(value):
    print(json.dumps(value, ensure_ascii=False, indent=2))


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def show_records(records):
    if not records:
        print("没有匹配记录。请检查筛选条件、待核验记录和 coverage 采集覆盖情况。")
        return
    print(f"找到 {len(records)} 条获奖记录（同一论文可获得两种奖项）。")
    for idx, r in enumerate(records, 1):
        precision = {"day": "日", "month": "月", "year": "年", "unknown": "未知"}[r["date_precision"]]
        print(f'\n{idx}. {r["title"]}')
        print(f'   {r["acronym"]} {r["year"]} · CCF {r["rank"]} · {AWARD_LABELS[r["award_type"]]} · {STATUS_LABELS[r["status"]]}')
        print(f'   发表日期：{r["publication_date"] or "未知"}（精度：{precision}）')
        for author in r["authors"]:
            aff = "；".join(a["name"] for a in author["affiliations"]) or "单位未知"
            print(f'   作者：{author["name"]} — {aff}')
        if not r["authors"]:
            print("   作者：未知")
        source = next(s for s in r["sources"] if s["id"] == r["award_evidence"]["source_id"])
        print(f'   获奖来源：{source["url"]}')
        if r["paper_url"]:
            print(f'   论文链接：{r["paper_url"]}')
        print(f'   记录编号：{r["id"]}')


def export_csv(path, records):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = ["id", "title", "conference", "ccf_rank", "conference_year", "award", "track",
              "publication_date", "date_precision", "authors_and_affiliations", "status", "paper_url", "doi", "award_source"]
    # Excel-safe text, also preserve UTF-8 Chinese names.
    def safe(value):
        value = str(value or "")
        return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in records:
            source = next(s["url"] for s in r["sources"] if s["id"] == r["award_evidence"]["source_id"])
            row = dict(id=r["id"], title=r["title"], conference=r["acronym"], ccf_rank=r["rank"],
                       conference_year=r["year"], award=r["award_name"], track=r["track"],
                       publication_date=r["publication_date"], date_precision=r["date_precision"],
                       authors_and_affiliations="; ".join(a["name"] + " [" + ", ".join(x["name"] for x in a["affiliations"]) + "]" for a in r["authors"]),
                       status=r["status"], paper_url=r["paper_url"], doi=r["doi"], award_source=source)
            writer.writerow({k: safe(v) for k, v in row.items()})


def collect_one(db, conference, year, urls, extra_urls=(), max_pages=4, output=None,
                local_sources=None, llm=None, notify=None, strict_urls=True,
                run_id=None, run_details=None):
    from .llm import LLM
    from .network import crawl
    llm = llm if llm is not None else LLM()
    notify = notify or (lambda msg: print(msg, file=sys.stderr))
    if not local_sources and not urls:
        raise ValueError("没有入口 URL，请用 source-add 或 collect --url 配置")
    run = run_id or db.start_run(conference["id"], year)
    try:
        sources, warnings = (local_sources, []) if local_sources else crawl(
            urls, extra_urls, max_pages, notify=notify, strict_seeds=strict_urls)
        source_chars = sum(len(source["text"]) for source in sources)
        notify(f"已读取 {len(sources)} 个来源（{source_chars:,} 字符），正在按目标年度提取…")
        bundle = llm.extract(conference, year, sources)
        extraction_usage = getattr(llm, "last_usage", None)
        if extraction_usage:
            bundle["api_usage"] = {"extraction": extraction_usage}
        target = output or str(Path(db.conn.execute("PRAGMA database_list").fetchone()[2]).parent / "runs" / f"{run:06d}.json")
        save_json(target, bundle)  # Preserve evidence even when individual records fail validation.
        summary = db.ingest(bundle)
        summary.update(run_id=run, raw_bundle=target, warnings=warnings)
        if run_details:
            summary.update(run_details)
        token_usage = dict((run_details or {}).get("token_usage") or {})
        if extraction_usage:
            token_usage["extraction"] = extraction_usage
        if token_usage:
            summary["token_usage"] = token_usage
            totals = [item.get("total_tokens") for item in token_usage.values() if isinstance(item, dict)]
            summary["total_tokens"] = sum(value for value in totals if isinstance(value, int))
        run_status = "partial" if warnings or summary["rejected"] else "extracted" if bundle["records"] else "no_results"
        summary["status"] = run_status
        db.finish_run(run, run_status, summary)
        return summary
    except Exception as exc:
        details = {"error": str(exc)}
        if getattr(llm, "last_usage", None):
            details["token_usage"] = {"extraction": llm.last_usage}
            details["total_tokens"] = llm.last_usage.get("total_tokens")
        db.finish_run(run, "failed", details)
        raise

def auto_collect_one(db, conference, year, output_dir="data/records", max_pages=4,
                     candidate_limit=3, search=None, llm=None, notify=None):
    from .discovery import ResponsesWebSearch
    search = search or ResponsesWebSearch()
    run = db.start_run(conference["id"], year)
    try:
        discovery = search.discover(conference, year, min(candidate_limit, max_pages))
        urls = [item["url"] for item in discovery["candidates"]]
        if not urls:
            raise ValueError("网页搜索没有返回候选官方页面")
    except Exception as exc:
        details = {"stage": "discovery", "error": str(exc)}
        if getattr(search, "last_usage", None):
            details["token_usage"] = {"search": search.last_usage}
            details["total_tokens"] = search.last_usage.get("total_tokens")
        db.finish_run(run, "failed", details)
        raise
    output = Path(output_dir) / f'{conference["id"]}-{year}.json'
    search_usage = discovery.get("token_usage")
    return collect_one(
        db, conference, year, urls, max_pages=max_pages, output=str(output),
        llm=llm, notify=notify, strict_urls=False, run_id=run,
        run_details={
            "discovery": discovery,
            "token_usage": {"search": search_usage} if search_usage else {},
        },
    )

def year_value(value):
    year = int(value)
    if not 1900 <= year <= 2200:
        raise argparse.ArgumentTypeError("年份应在 1900–2200")
    return year


def parser():
    p = argparse.ArgumentParser(description="Global CS Paper Awards：顶级计算机会议与期刊论文奖采集检索系统")
    p.add_argument("--db", default=os.getenv("CCF_AWARDS_DB", "data/awards.sqlite3"), help="SQLite 路径；放在子命令前")
    sub = p.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="导入 190 个会议，不会删除论文")
    init.add_argument("--docx", help="可选：从同格式 DOCX 重新导入")
    conf = sub.add_parser("conferences", help="查会议、等级、领域及唯一编号")
    conf.add_argument("--query", default="")
    conf.add_argument("--rank", choices=["A", "B"])
    conf.add_argument("--json", action="store_true")
    for name in ("source-add", "sources", "suggest", "collect", "extract-file"):
        c = sub.add_parser(name, help={"source-add": "登记会议年度官网/获奖页", "sources": "列出已登记入口", "suggest": "LLM 建议候选网址（未验证）", "collect": "从网站采集并入库", "extract-file": "从手动保存的正文/PDF 提取"}[name])
        c.add_argument("--conference", required=True)
        c.add_argument("--year", required=True, type=year_value)
        if name == "source-add":
            c.add_argument("--url", required=True)
        if name == "collect":
            c.add_argument("--url", action="append", default=[])
            c.add_argument("--extra-url", action="append", default=[], help="论文详情/PDF 元数据来源，可重复")
            c.add_argument("--max-pages", type=int, default=4)
            c.add_argument("--output", help="保存原始提取及证据 JSON")
        if name == "extract-file":
            c.add_argument("--file", required=True)
            c.add_argument("--source-url", required=True)
            c.add_argument("--metadata-file", help="可选：论文元数据正文或 PDF")
            c.add_argument("--metadata-url", help="metadata-file 的实际来源 URL")
            c.add_argument("--output")
    b = sub.add_parser("batch", help="采集指定年份内已经登记入口的所有会议，失败后继续其他任务")
    b.add_argument("--from-year", required=True, type=year_value)
    b.add_argument("--to-year", required=True, type=year_value)
    b.add_argument("--max-pages", type=int, default=4)
    imp = sub.add_parser("import-json", help="无需 API，导入人工整理或离线提取 JSON")
    imp.add_argument("file")
    excel = sub.add_parser("import-excel", help="把核验整理版 Excel 幂等导入 SQLite")
    excel.add_argument("file")
    published = sub.add_parser("import-verified", help="导入 GitHub 上发布的已核验快照")
    published.add_argument("file")
    discover = sub.add_parser("discover", help="使用 OpenAI web_search 查找候选官方获奖页")
    discover.add_argument("--conference", required=True)
    discover.add_argument("--year", required=True, type=year_value)
    discover.add_argument("--limit", type=int, default=5)
    discover.add_argument("--save", action="store_true", help="把候选网址登记为待采集入口")
    auto = sub.add_parser("autocollect", help="自动发现官网、抓取、提取并保存证据 JSON")
    auto.add_argument("--conference", required=True)
    auto.add_argument("--year", required=True, type=year_value)
    auto.add_argument("--max-pages", type=int, default=4)
    auto.add_argument("--candidate-limit", type=int, default=3)
    auto.add_argument("--output-dir", default="data/records")
    agent = sub.add_parser("agent-run", help="无人值守执行一批尚未处理的会议年度任务")
    agent.add_argument("--year", required=True, type=year_value)
    agent.add_argument("--limit", type=int, default=3)
    agent.add_argument("--max-pages", type=int, default=4)
    agent.add_argument("--candidate-limit", type=int, default=3)
    agent.add_argument("--output-dir", default="data/records")
    render = sub.add_parser("render-markdown", help="从数据库生成 GitHub 可浏览的获奖论文索引")
    render.add_argument("--root", default=".")
    render.add_argument("--status", choices=["all", "active", "pending", "verified", "rejected"], default="all")
    demo = sub.add_parser("demo", help="离线导入两条真实获奖样例；默认仍为待核验")
    s = sub.add_parser("search", help="多个条件按 AND 组合检索")
    s.add_argument("--conference")
    s.add_argument("--rank", choices=["A", "B"])
    s.add_argument("--year-from", type=year_value)
    s.add_argument("--year-to", type=year_value)
    s.add_argument("--published-from", help="论文发表日起点 YYYY-MM-DD，按日期区间相交匹配")
    s.add_argument("--published-to", help="论文发表日终点 YYYY-MM-DD，包含端点")
    s.add_argument("--author")
    s.add_argument("--affiliation")
    s.add_argument("--title")
    s.add_argument("--award", choices=list(AWARD_LABELS))
    s.add_argument("--status", choices=["active", "all", "pending", "verified", "rejected"], default="active", help="默认 active：待核验和已核验，排除已否定记录")
    s.add_argument("--format", choices=["text", "json"], default="text")
    s.add_argument("--csv", help="同时将匹配记录导出 CSV")
    show = sub.add_parser("show", help="显示一条记录的完整 JSON 及来源证据")
    show.add_argument("id")
    rev = sub.add_parser("review", help="核对原网页后，人工改变状态并记录依据")
    rev.add_argument("id")
    rev.add_argument("--status", required=True, choices=["verified", "pending", "rejected"])
    rev.add_argument("--reviewer", required=True)
    rev.add_argument("--note", required=True)
    cov = sub.add_parser("coverage", help="按会议、年份、奖项检查采集覆盖，不把零结果当作未设奖")
    cov.add_argument("--conference")
    cov.add_argument("--year-from", type=year_value, required=True)
    cov.add_argument("--year-to", type=year_value, required=True)
    cov.add_argument("--json", action="store_true")
    mark = sub.add_parser("coverage-mark", help="人工标记某会议年度奖项的覆盖结论")
    mark.add_argument("--conference", required=True)
    mark.add_argument("--year", required=True, type=year_value)
    mark.add_argument("--award", required=True, choices=list(AWARD_LABELS))
    mark.add_argument("--state", required=True, choices=["partial", "checked", "not_offered", "not_found"])
    mark.add_argument("--url", required=True)
    mark.add_argument("--note", required=True)
    sub.add_parser("runs", help="查看采集日志")
    return p


def run(args, db):
    cmd = args.command
    if cmd == "init":
        print(f"已导入 {db.init(parse_docx(args.docx) if args.docx else None)} 个会议；名单依据用户提供的 2026 文档。")
    elif cmd == "conferences":
        rows = db.conferences(args.query, args.rank)
        if args.json:
            dump(rows)
        else:
            print(f"{len(rows)} 个会议")
            for r in rows:
                print(f'{r["id"]}\t{r["rank"]}\t{r["acronym"]}\t{r["area"]}\t{r["full_name"]}')
    elif cmd == "demo":
        db.init()
        for path in sorted(DEFAULT_CATALOG.parent.parent.joinpath("examples").glob("sample-*.json")):
            print(path.name)
            dump(db.ingest(json.loads(path.read_text(encoding="utf-8"))))
        print("两条样例只用于试跑，并非完整年度获奖名单；请用 search 查看。")
    elif cmd == "import-json":
        result = db.ingest(json.loads(Path(args.file).read_text(encoding="utf-8")))
        dump(result)
        return 2 if result["rejected"] else 0
    elif cmd == "import-excel":
        from .excel_import import import_excel
        db.init()
        dump(import_excel(db, args.file))
    elif cmd == "import-verified":
        from .github_publish import import_verified_snapshot
        db.init()
        dump(import_verified_snapshot(db, args.file))
    elif cmd == "discover":
        from .discovery import ResponsesWebSearch
        conference = db.resolve(args.conference)
        result = ResponsesWebSearch().discover(conference, args.year, args.limit)
        if args.save:
            for candidate in result["candidates"]:
                db.add_seed(conference["id"], args.year, candidate["url"])
        dump(result)
    elif cmd == "autocollect":
        conference = db.resolve(args.conference)
        dump(auto_collect_one(db, conference, args.year, args.output_dir,
                              args.max_pages, args.candidate_limit))
    elif cmd == "agent-run":
        if not 1 <= args.limit <= 50:
            raise ValueError("limit 应在 1–50 之间")
        from .discovery import ResponsesWebSearch
        from .llm import LLM
        search, llm, tasks = ResponsesWebSearch(), LLM(), []
        output_dir = Path(args.output_dir)
        for conference in db.conferences():
            if len(tasks) >= args.limit:
                break
            output = output_dir / f'{conference["id"]}-{args.year}.json'
            if output.exists() or db.search(conference=conference["id"], year_from=args.year,
                                            year_to=args.year, status="active"):
                continue
            try:
                result = auto_collect_one(db, conference, args.year, output_dir,
                                          args.max_pages, args.candidate_limit, search, llm)
                tasks.append({"conference_id": conference["id"], "status": result["status"], **result})
            except Exception as exc:
                tasks.append({"conference_id": conference["id"], "status": "failed", "error": str(exc)})
        dump({"year": args.year, "tasks": tasks})
        return 2 if any(task["status"] == "failed" for task in tasks) else 0
    elif cmd == "render-markdown":
        from .markdown_export import render_markdown
        dump(render_markdown(db, args.root, status=args.status))
    elif cmd in ("source-add", "sources", "suggest", "collect", "extract-file"):
        conf = db.resolve(args.conference)
        if cmd == "source-add":
            db.add_seed(conf["id"], args.year, args.url)
            print("已登记年度入口。登记表示用户选定来源，不代表程序已验证其官方身份。")
        elif cmd == "sources":
            dump(db.seeds(conf["id"], args.year))
        elif cmd == "suggest":
            from .llm import LLM
            print("以下为 LLM 候选网址和查询词；没有执行联网搜索，使用前需核实。", file=sys.stderr)
            dump(LLM().suggest(conf, args.year))
        else:
            if cmd == "extract-file":
                from .network import read_local_source
                if bool(args.metadata_file) != bool(args.metadata_url):
                    raise ValueError("metadata-file 和 metadata-url 必须同时提供")
                sources = [read_local_source(args.file, args.source_url)]
                if args.metadata_file:
                    sources.append(read_local_source(args.metadata_file, args.metadata_url, "metadata", "s2"))
                result = collect_one(db, conf, args.year, [], output=args.output, local_sources=sources)
            else:
                result = collect_one(db, conf, args.year, args.url or db.seeds(conf["id"], args.year),
                                     args.extra_url, args.max_pages, args.output)
            dump(result)
            return 2 if result["rejected"] else 0
    elif cmd == "batch":
        if args.from_year > args.to_year:
            raise ValueError("起始年份不能晚于结束年份")
        from .llm import LLM
        LLM()
        summary, skipped = [], 0
        for conf in db.conferences():
            for year in range(args.from_year, args.to_year + 1):
                urls = db.seeds(conf["id"], year)
                if not urls:
                    skipped += 1
                    continue
                try:
                    result = collect_one(db, conf, year, urls, max_pages=args.max_pages)
                except Exception as exc:
                    result = {"status": "failed", "error": str(exc)}
                summary.append({"conference_id": conf["id"], "year": year, **result})
        dump({"tasks": summary, "skipped_without_url": skipped})
        return 2 if any(x["status"] in ("failed", "partial") for x in summary) else 0
    elif cmd == "search":
        if args.year_from and args.year_to and args.year_from > args.year_to:
            raise ValueError("起始年份不能晚于结束年份")
        for value in (args.published_from, args.published_to):
            if value:
                if dt.date.fromisoformat(value).isoformat() != value:
                    raise ValueError("发表日期筛选需要 YYYY-MM-DD")
        if args.published_from and args.published_to and args.published_from > args.published_to:
            raise ValueError("起始发表日期不能晚于结束日期")
        fields = ("rank", "year_from", "year_to", "author", "affiliation", "title", "award", "status", "published_from", "published_to")
        kwargs = {k: getattr(args, k) for k in fields}
        if args.conference:
            kwargs["conference"] = db.resolve(args.conference)["id"]
        results = db.search(**kwargs)
        if args.format == "json":
            dump(results)
        else:
            show_records(results)
        if args.csv:
            export_csv(args.csv, results)
            print(f"已导出 {len(results)} 条记录到 {args.csv}", file=sys.stderr)
    elif cmd == "show":
        results = [r for r in db.search(status="all") if r["id"] == args.id]
        if not results:
            raise ValueError("记录不存在")
        dump(results[0])
    elif cmd == "review":
        db.review(args.id, args.status, require_text(args.reviewer, "reviewer"), require_text(args.note, "note"))
        print("已记录核验状态，历史版本已保留。")
    elif cmd == "coverage":
        if args.year_from > args.year_to:
            raise ValueError("起始年份不能晚于结束年份")
        rows = db.coverage(args.year_from, args.year_to, db.resolve(args.conference)["id"] if args.conference else None)
        if args.json:
            dump(rows)
        else:
            for r in rows:
                print(f'{r["conference_id"]}\t{r["year"]}\t{r["award_type"]}\t{r["state"]}\t{r["counts"]}')
    elif cmd == "coverage-mark":
        conf = db.resolve(args.conference)
        db.mark_coverage(conf["id"], args.year, args.award, args.state, args.url, require_text(args.note, "note"))
        print("已记录覆盖结论。")
    elif cmd == "runs":
        dump([dict(r) for r in db.conn.execute("SELECT * FROM runs ORDER BY id DESC")])
    return 0


def main(argv=None):
    args = parser().parse_args(argv)
    db = None
    try:
        db = Database(args.db)
        return run(args, db)
    except (ValueError, OSError, sqlite3.Error) as exc:
        print("错误：" + str(exc), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("已中断。已完成的记录仍保存在本地。", file=sys.stderr)
        return 130
    finally:
        if db:
            db.close()


if __name__ == "__main__":
    raise SystemExit(main())
