"""Run from this folder: python -m streamlit run streamlit_app.py

This file only builds the UI. Database.search, collect_one, and Database.review
continue to own the underlying behavior used by both the web app and the CLI.
"""
import datetime as dt
import inspect
import json
import os
import tempfile
import time
from pathlib import Path

import streamlit as st

from ccf_awards.__main__ import auto_collect_one, collect_one
from ccf_awards.db import Database
from ccf_awards.discovery import ResponsesWebSearch
from ccf_awards.excel_import import import_excel
from ccf_awards.github_publish import GitHubPublisher, publish_verified
from ccf_awards.llm import LLM
from ccf_awards.model import require_text, url_syntax
from ccf_awards.network import read_local_source
from ccf_awards.providers import PROVIDER_PROFILES, provider_profile
from ccf_awards.web_helpers import (
    AWARDS, COVERAGE, STATUSES, csv_bytes, database_path, export_rows,
    import_demo, parse_years, urls_from_text, validate_filters,
)

APP_NAME = "Global CS Paper Awards"
APP_SUBTITLE = "Best Paper and Best Student Paper Awards in Top Computer Science Venues"
APP_NAME_ZH = "全球计算机顶级论文奖数据库——收录顶级会议与期刊的最佳论文奖和最佳学生论文奖"

st.set_page_config(page_title=APP_NAME, page_icon="🏆", layout="wide")


def conference_label(cid, conferences):
    if cid is None:
        return "全部会议"
    c = conferences[cid]
    return f'{c["acronym"]} · {c["rank"]} 类 · {c["area"]}'


def make_llm():
    return LLM(api_key=st.session_state.get("api_key") or None,
               base_url=st.session_state.get("base_url") or None,
               model=st.session_state.get("model_name") or None,
               json_mode=st.session_state.get("json_mode", True),
               provider=st.session_state.get("provider_name") or None)


def make_search():
    if st.session_state.get("search_reuse_primary", True):
        _, profile = provider_profile(st.session_state.get("provider_name", "deepseek"))
        return ResponsesWebSearch(
            api_key=st.session_state.get("api_key") or os.getenv("LLM_API_KEY") or os.getenv(profile["key_env"]) or None,
            base_url=st.session_state.get("base_url") or None,
            model=st.session_state.get("model_name") or None,
        )
    return ResponsesWebSearch(
        api_key=st.session_state.get("search_api_key") or None,
        base_url=st.session_state.get("search_base_url") or None,
        model=st.session_state.get("search_model") or None,
    )

def flash(message, kind="success"):
    st.session_state["notice"] = (kind, message)


def safe_error(exc):
    message = str(exc)
    # Defensive redaction in UI; backend already omits provider response bodies.
    for secret in (st.session_state.get("api_key"), os.getenv("LLM_API_KEY"),
                   os.getenv("DEEPSEEK_API_KEY"), os.getenv("OPENAI_API_KEY"),
                   st.session_state.get("search_api_key"), os.getenv("SEARCH_API_KEY"),
                   os.getenv("GITHUB_TOKEN"), os.getenv("GH_TOKEN")):
        if secret:
            message = message.replace(secret, "[已隐藏]")
    st.error(message)


def form_submit(container, label, key, **kwargs):
    """Keep form buttons working on both older and current Streamlit releases."""
    button = container.form_submit_button
    if "key" in inspect.signature(button).parameters:
        kwargs["key"] = key
    return button(label, **kwargs)


def apply_provider_defaults():
    """Update editable connection fields when the named provider changes."""
    _, profile = provider_profile(st.session_state.get("provider_name", "deepseek"))
    st.session_state["base_url"] = profile["base_url"]
    st.session_state["model_name"] = profile["model"]

def render_sidebar(db):
    with st.sidebar:
        st.title(APP_NAME)
        st.caption("全球计算机顶级论文奖数据库")
        section = st.radio("工作区", ["论文检索", "采集与导入", "记录核验", "采集覆盖"], key="section")
        st.divider()
        with st.expander("AI 连接设置"):
            st.caption("结构化提取与联网搜索默认复用同一组 API 地址、模型和密钥；设置只在当前网页会话中使用。")
            provider_names = list(PROVIDER_PROFILES)
            configured_provider = os.getenv("LLM_PROVIDER", "deepseek").lower()
            if configured_provider not in provider_names:
                configured_provider = "deepseek"
            selected_provider = st.selectbox(
                "LLM 提供商", provider_names, index=provider_names.index(configured_provider),
                format_func=lambda name: PROVIDER_PROFILES[name]["label"], key="provider_name",
                on_change=apply_provider_defaults,
            )
            _, profile = provider_profile(selected_provider)
            if "base_url" not in st.session_state:
                st.session_state["base_url"] = os.getenv("LLM_BASE_URL", "") or profile["base_url"]
            if "model_name" not in st.session_state:
                st.session_state["model_name"] = os.getenv("LLM_MODEL", "") or profile["model"]
            st.text_input("API 地址", key="base_url")
            st.text_input("模型名称", key="model_name", placeholder="填写账户可调用的模型")
            st.text_input(
                "API Key", type="password", key="api_key",
                help=f"留空时依次读取 LLM_API_KEY 和 {profile['key_env']}；不会写入数据库。",
            )
            st.checkbox("请求 JSON 模式", value=os.getenv("LLM_JSON_MODE", "1") == "1", key="json_mode")
            available_key = st.session_state.get("api_key") or os.getenv("LLM_API_KEY") or os.getenv(profile["key_env"])
            if st.session_state.get("model_name") and available_key:
                st.caption("连接参数已填写；尚不代表连接测试成功。")
            reuse_default = os.getenv("SEARCH_REUSE_LLM", "1") == "1"
            st.checkbox(
                "联网搜索复用上述连接", value=reuse_default, key="search_reuse_primary",
                help="要求该地址同时兼容 /chat/completions 和带 web_search 工具的 /responses。",
            )
            if st.session_state.get("search_reuse_primary"):
                if selected_provider == "deepseek":
                    st.warning("标准 DeepSeek Chat 接口目前不能执行 Responses web_search。自动搜索请改用同时支持两种接口的端点，或关闭复用并填写高级搜索连接。")
            else:
                st.caption("高级搜索连接：仅当上述端点不支持 Responses web_search 时使用。")
                if "search_base_url" not in st.session_state:
                    st.session_state["search_base_url"] = os.getenv("SEARCH_BASE_URL", "https://api.openai.com/v1")
                if "search_model" not in st.session_state:
                    st.session_state["search_model"] = os.getenv("SEARCH_MODEL", os.getenv("OPENAI_SEARCH_MODEL", ""))
                st.text_input("搜索 API 地址", key="search_base_url")
                st.text_input("搜索模型", key="search_model", placeholder="填写支持 web_search 的模型")
                st.text_input(
                    "搜索 API Key", type="password", key="search_api_key",
                    help="留空时读取 SEARCH_API_KEY 或 OPENAI_API_KEY；不会写入数据库。",
                )
        if st.button("导入两条样例", key="demo", width="stretch"):
            try:
                results = import_demo(db)
                count = sum(x["inserted"] for x in results)
                flash(f"样例已准备好，新增 {count} 条。样例不代表完整年度名单。")
                st.rerun()
            except Exception as exc:
                safe_error(exc)
        st.caption("名单来自上传的 2026 文档。缺失字段保留未知，采集记录需要核验。")
    return section


def render_detail(record):
    st.text(record["title"])
    a, b, c = st.columns(3)
    a.write(f'{record["acronym"]} {record["year"]} · CCF {record["rank"]}')
    b.write(AWARDS[record["award_type"]])
    c.write(STATUSES[record["status"]])
    precision = {"day":"精确到日", "month":"精确到月", "year":"精确到年", "unknown":"未知"}[record["date_precision"]]
    st.write(f'发表日期：{record["publication_date"] or "未知"}（{precision}）')
    author_rows = [{"作者": a["name"], "发表时单位": "；".join(x["name"] for x in a["affiliations"]) or "未知"} for a in record["authors"]]
    if author_rows:
        st.dataframe(author_rows, hide_index=True, width="stretch")
    else:
        st.info("来源尚未提供作者信息。")
    for idx, source in enumerate(record["sources"], 1):
        st.link_button(f'来源 {idx} · {"获奖页面" if source["role"] == "award" else "论文元数据"}', url_syntax(source["url"]))
    if record["paper_url"]:
        st.link_button("打开论文", url_syntax(record["paper_url"]))
    if record.get("review_note"):
        st.text(f'核验人：{record.get("reviewer") or "未知"}\n备注：{record["review_note"]}')
    with st.expander("查看字段证据及原始记录"):
        st.json(record)


def search_page(db, conferences):
    st.header("论文检索")
    st.caption("组合筛选获奖论文，查看作者、发表时间和单位。")
    defaults = st.session_state.get("search_filters", {})
    ids = [None, *conferences]
    with st.form("search_form"):
        a, b, c = st.columns([3, 1, 2])
        cid = a.selectbox("会议", ids, index=ids.index(defaults.get("conference")), format_func=lambda x: conference_label(x, conferences), key="search_conference")
        rank_options = [None, "A", "B"]
        rank = b.selectbox("CCF 等级", rank_options, index=rank_options.index(defaults.get("rank")), format_func=lambda x: "全部" if x is None else x + " 类", key="search_rank")
        award_options = [None, *AWARDS]
        award = c.selectbox("奖项", award_options, index=award_options.index(defaults.get("award")), format_func=lambda x: AWARDS.get(x, "两种奖项"), key="search_award")
        a, b, c, d = st.columns(4)
        start = a.number_input("会议起始年份", min_value=1900, max_value=2200, value=defaults.get("year_from"), step=1, placeholder="不限", key="search_year_from")
        end = b.number_input("会议结束年份", min_value=1900, max_value=2200, value=defaults.get("year_to"), step=1, placeholder="不限", key="search_year_to")
        author = c.text_input("作者姓名", value=defaults.get("author") or "", key="search_author", placeholder="如 Julie")
        affiliation = d.text_input("作者单位", value=defaults.get("affiliation") or "", key="search_affiliation", placeholder="如 Stanford")
        a, b = st.columns([3, 1])
        title = a.text_input("论文标题关键词", value=defaults.get("title") or "", key="search_title")
        status_values = list(STATUSES)
        status = b.selectbox("核验状态", status_values, index=status_values.index(defaults.get("status", "active")), format_func=STATUSES.get, key="search_status")
        with st.expander("按论文发表日期筛选"):
            st.caption("日期缺失的记录不会命中此筛选；只有年月的记录按整月范围匹配，显示仍保留月份精度。")
            a, b = st.columns(2)
            since = a.date_input("发表日期起点", value=dt.date.fromisoformat(defaults["published_from"]) if defaults.get("published_from") else None, key="published_from")
            until = b.date_input("发表日期终点", value=dt.date.fromisoformat(defaults["published_to"]) if defaults.get("published_to") else None, key="published_to")
        submitted = form_submit(st, "搜索论文", "search_submit", type="primary")
    if submitted:
        query = dict(conference=cid, rank=rank, award=award, year_from=start, year_to=end,
                     author=author.strip() or None, affiliation=affiliation.strip() or None,
                     title=title.strip() or None, status=status,
                     published_from=since.isoformat() if since else None,
                     published_to=until.isoformat() if until else None)
        try:
            st.session_state["search_filters"] = validate_filters(query)
        except ValueError as exc:
            st.error(str(exc))
            return
    results = db.search(**st.session_state.get("search_filters", {}))
    st.subheader(f"{len(results)} 条获奖记录")
    if not results:
        st.info("没有匹配结果。首次使用可点击左侧“导入两条样例”；也可调整筛选，或到“采集与导入”添加记录。")
        return
    a, b = st.columns([1, 5])
    a.download_button("下载 CSV", csv_bytes(results), file_name="ccf-awards.csv", mime="text/csv", key="download_csv")
    b.caption("作者与单位同时筛选时，必须对应同一位作者。未知字段不会补猜。")
    rows = export_rows(results)
    keys = ["论文名称", "会议", "CCF", "会议年份", "奖项", "发表日期", "状态"]
    st.dataframe([{k: row[k] for k in keys} for row in rows], hide_index=True, width="stretch")
    by_id = {r["id"]: r for r in results}
    selected = st.selectbox("选择论文查看作者、单位和来源", list(by_id), format_func=lambda x: f'{by_id[x]["acronym"]} {by_id[x]["year"]} · {by_id[x]["title"]}', key="detail_record")
    st.markdown("#### 论文详情")
    render_detail(by_id[selected])


def _records_by_ids(db, record_ids):
    wanted = set(record_ids or [])
    return [record for record in db.search(status="all") if record["id"] in wanted]


def show_import_result(result, db=None):
    st.write(f'新增 {result["inserted"]} 条 · 更新 {result["updated"]} 条 · 重复 {result["unchanged"]} 条')
    if result.get("elapsed_seconds") is not None:
        st.caption(f'本次操作耗时：{result["elapsed_seconds"]:.1f} 秒')
    search_tokens, extraction_tokens, total_tokens = _token_totals(result)
    if total_tokens is not None:
        st.caption(f"API tokens：搜索 {search_tokens or 0:,} · 结构化提取 {extraction_tokens or 0:,} · 合计 {total_tokens:,}")
    if result.get("status") == "no_results":
        st.info("本次未提取到符合条件的记录，不代表该年度未设奖。")
    if result["rejected"]:
        st.warning(f'{len(result["rejected"])} 条记录未通过校验，请查看具体原因。')
        st.json(result["rejected"])
    if result.get("warnings"):
        st.warning("部分相关页面未能读取，本次采集可能不完整。")
        st.json(result["warnings"])
    if db is not None and result.get("record_ids"):
        records = _records_by_ids(db, result["record_ids"])
        st.markdown("#### 本次找到的论文")
        st.dataframe(export_rows(records), hide_index=True, width="stretch")
    if result.get("log_lines"):
        st.markdown("#### 本次操作日志")
        st.code("\n".join(result["log_lines"]), language="text")


def _token_totals(details):
    usage = details.get("token_usage") or {}
    search = (usage.get("search") or {}).get("total_tokens")
    extraction = (usage.get("extraction") or {}).get("total_tokens")
    known = [value for value in (search, extraction) if isinstance(value, int)]
    total = details.get("total_tokens")
    if not isinstance(total, int):
        total = sum(known) if known else None
    return search, extraction, total

def _display_time(value):
    if not value:
        return "—"
    return dt.datetime.fromisoformat(value).astimezone().strftime("%Y-%m-%d %H:%M:%S")


def show_run_history(db):
    rows = []
    for run in db.runs(50):
        details = run["details"]
        search_tokens, extraction_tokens, total_tokens = _token_totals(details)
        rows.append({
            "任务": run["id"], "会议": run["acronym"], "年份": run["year"],
            "开始时间": _display_time(run["started_at"]),
            "结束时间": _display_time(run["finished_at"]),
            "耗时（秒）": round(run["duration_seconds"], 1) if run["duration_seconds"] is not None else "运行中",
            "状态": run["status"], "新增": details.get("inserted", 0),
            "更新": details.get("updated", 0), "重复": details.get("unchanged", 0),
            "搜索 tokens": search_tokens if search_tokens is not None else "—",
            "提取 tokens": extraction_tokens if extraction_tokens is not None else "—",
            "总 tokens": total_tokens if total_tokens is not None else "—",
            "说明": details.get("error", ""),
        })
    if rows:
        st.dataframe(rows, hide_index=True, width="stretch")
    else:
        st.caption("尚无采集运行日志。")

def show_batch_result(db, batch):
    st.markdown("### 本次批量查找结果")
    token_rows = [_token_totals(task) for task in batch["tasks"]]
    search_total = sum(row[0] for row in token_rows if isinstance(row[0], int))
    extraction_total = sum(row[1] for row in token_rows if isinstance(row[1], int))
    a, b, c, d = st.columns(4)
    a.metric("任务数", len(batch["tasks"]))
    b.metric("成功", sum(task["status"] != "failed" for task in batch["tasks"]))
    c.metric("失败", sum(task["status"] == "failed" for task in batch["tasks"]))
    d.metric("总耗时", f'{batch["elapsed_seconds"]:.1f} 秒')
    st.caption(f'开始：{batch["started_at"]} · 结束：{batch["finished_at"]}')
    if any(value is not None for row in token_rows for value in row):
        st.caption(f"API tokens：搜索 {search_total:,} · 结构化提取 {extraction_total:,} · 合计 {search_total + extraction_total:,}")
    task_rows = []
    for task in batch["tasks"]:
        search_tokens, extraction_tokens, total_tokens = _token_totals(task)
        task_rows.append({
            "会议": task["conference"], "年份": task["year"], "状态": task["status"],
            "耗时（秒）": task["elapsed_seconds"], "新增": task.get("inserted", 0),
            "更新": task.get("updated", 0), "重复": task.get("unchanged", 0),
            "找到论文": len(task.get("record_ids", [])),
            "搜索 tokens": search_tokens if search_tokens is not None else "—",
            "提取 tokens": extraction_tokens if extraction_tokens is not None else "—",
            "总 tokens": total_tokens if total_tokens is not None else "—",
            "说明": task.get("error", ""),
        })
    st.dataframe(task_rows, hide_index=True, width="stretch")
    records = _records_by_ids(db, batch.get("record_ids", []))
    st.markdown(f"#### 本次找到的论文（{len(records)} 条）")
    if records:
        st.dataframe(export_rows(records), hide_index=True, width="stretch")
        st.download_button("下载本次结果 CSV", csv_bytes(records), "collection-results.csv", "text/csv", key="batch_csv")
    else:
        st.info("本次任务没有产生可展示的论文记录；请查看任务说明和日志。")
    with st.expander("本次查找日志", expanded=True):
        st.code("\n".join(batch["log_lines"]), language="text")

def run_batch_collection(db, conferences, conference_ids, years, strategy, maximum):
    task_pairs = [(cid, year) for cid in conference_ids for year in years]
    if not task_pairs:
        raise ValueError("请至少选择一个会议和一个年份。")
    if len(task_pairs) > 50:
        raise ValueError("一次最多执行 50 个“会议 × 年份”任务，请缩小选择范围。")
    started_clock = time.perf_counter()
    started_at = dt.datetime.now().astimezone()
    logs, tasks, record_ids = [], [], []
    status = st.status(f"准备执行 {len(task_pairs)} 个采集任务…", expanded=True)
    live_log = st.empty()

    def log(message):
        elapsed = time.perf_counter() - started_clock
        line = f"+{elapsed:7.1f}s  {message}"
        logs.append(line)
        live_log.code("\n".join(logs[-120:]), language="text")

    llm = make_llm()
    search = make_search() if strategy == "自动搜索官网" else None
    for index, (cid, year) in enumerate(task_pairs, 1):
        conference = conferences[cid]
        label = f'{conference["acronym"]} {year}'
        status.update(label=f"[{index}/{len(task_pairs)}] 正在处理 {label}")
        log(f"开始 {label}（{strategy}）")
        task_clock = time.perf_counter()
        try:
            if strategy == "自动搜索官网":
                result = auto_collect_one(
                    db, conference, year, max_pages=int(maximum),
                    candidate_limit=min(3, int(maximum)), search=search, llm=llm, notify=log,
                )
            else:
                urls = db.seeds(cid, year)
                if not urls:
                    run_id = db.start_run(cid, year)
                    db.finish_run(run_id, "failed", {"stage": "saved_sources", "error": "没有已保存入口"})
                    raise ValueError("没有已保存入口；请改用自动搜索或先在单任务模式保存网址。")
                result = collect_one(db, conference, year, urls, max_pages=int(maximum), llm=llm, notify=log)
            ids = result.get("record_ids", [])
            record_ids.extend(ids)
            elapsed = round(time.perf_counter() - task_clock, 1)
            tasks.append({"conference": conference["acronym"], "year": year,
                          "elapsed_seconds": elapsed, **result})
            log(f'完成 {label}：状态 {result["status"]}，找到 {len(ids)} 条，耗时 {elapsed:.1f} 秒')
        except Exception as exc:
            elapsed = round(time.perf_counter() - task_clock, 1)
            tasks.append({"conference": conference["acronym"], "year": year,
                          "status": "failed", "elapsed_seconds": elapsed, "error": str(exc),
                          "record_ids": []})
            log(f"失败 {label}：{exc}（耗时 {elapsed:.1f} 秒）")
    elapsed = round(time.perf_counter() - started_clock, 1)
    failed = sum(task["status"] == "failed" for task in tasks)
    status.update(label=f"批量采集结束：{len(tasks) - failed} 成功，{failed} 失败，总耗时 {elapsed:.1f} 秒",
                  state="error" if failed else "complete", expanded=True)
    return {
        "started_at": started_at.strftime("%Y-%m-%d %H:%M:%S %Z"),
        "finished_at": dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
        "elapsed_seconds": elapsed, "tasks": tasks,
        "record_ids": list(dict.fromkeys(record_ids)), "log_lines": logs,
    }


def collect_page(db, conferences):
    st.header("采集与导入")
    st.caption("一次选择多个会议和多个年份区间，集中查看论文结果、任务状态和耗时日志。新增记录默认待核验。")
    seed_stats = db.seed_stats()
    a, b, c = st.columns(3)
    a.metric("已保存入口覆盖", f'{seed_stats["conferences_with_seed"]}/{seed_stats["total_conferences"]} 个会议')
    b.metric("会议年度网址", seed_stats["seed_rows"])
    c.metric("尚无入口", seed_stats["conferences_without_seed"])
    years = " · ".join(f'{row["year"]}: {row["conferences"]} 个会议/{row["urls"]} 个网址'
                       for row in seed_stats["by_year"])
    st.caption("入口按会议和年份保存，并不等同于永久官网。" + (" 当前分年覆盖：" + years if years else ""))
    if st.session_state.get("last_collection_batch"):
        with st.container(border=True):
            show_batch_result(db, st.session_state["last_collection_batch"])
    if st.session_state.get("last_import"):
        with st.expander("最近一次单项操作结果", expanded=True):
            show_import_result(st.session_state["last_import"], db)
    with st.expander("采集历史日志（最近 50 次）", expanded=False):
        show_run_history(db)

    method = st.radio("数据来源", ["读取网页", "上传正文 / PDF", "导入 JSON"], horizontal=True, key="import_method")
    if method == "导入 JSON":
        with st.form("json_import"):
            upload = st.file_uploader("选择符合样例结构的提取 JSON", type=["json"], key="json_upload")
            submitted = form_submit(st, "导入记录", "json_submit", type="primary")
        if submitted:
            try:
                if upload is None:
                    raise ValueError("请先选择 JSON 文件。")
                started = time.perf_counter()
                result = db.ingest(json.loads(upload.getvalue().decode("utf-8-sig")))
                result["elapsed_seconds"] = time.perf_counter() - started
                st.session_state["last_import"] = result
                flash("文件已处理，可到论文检索页查看有效记录。", "warning" if result["rejected"] else "success")
                st.rerun()
            except Exception as exc:
                safe_error(exc)
        st.caption("不调用 API。文件结构可参考 examples 中的 JSON。")
        return

    if method == "读取网页":
        mode = st.radio(
            "采集方式", ["自动搜索官网（批量）", "使用已保存入口（批量）", "手动网址（单任务）"],
            horizontal=True, key="collection_mode",
        )
        if mode != "手动网址（单任务）":
            strategy = "自动搜索官网" if mode.startswith("自动") else "使用已保存入口"
            with st.form("batch_collect_form"):
                selected_ids = st.multiselect(
                    "采集会议（可多选）", list(conferences),
                    format_func=lambda cid: conference_label(cid, conferences), key="batch_conferences",
                )
                year_text = st.text_input(
                    "会议年份或区间（可填写多个）", value=str(dt.date.today().year),
                    placeholder="例如：2023-2026, 2020, 2017-2018", key="batch_years",
                )
                maximum = st.number_input("每个任务最多读取的页面数", min_value=1, max_value=20, value=4, key="batch_max_pages")
                submit = form_submit(st, "开始批量采集", "batch_collect_submit", type="primary")
            st.caption("任务数量 = 会议数 × 去重后的年份数；一次最多 50 个任务。自动搜索需要在左侧配置搜索 API。")
            if submit:
                try:
                    years = parse_years(year_text)
                    batch = run_batch_collection(db, conferences, selected_ids, years, strategy, int(maximum))
                    st.session_state["last_collection_batch"] = batch
                    flash("批量采集已完成；结果表和日志已保留在本页顶部。",
                          "warning" if any(task["status"] == "failed" for task in batch["tasks"]) else "success")
                    st.rerun()
                except Exception as exc:
                    safe_error(exc)
            return

        a, b = st.columns([3, 1])
        cid = a.selectbox("采集会议", list(conferences), format_func=lambda x: conference_label(x, conferences), key="collect_conference")
        year = b.number_input("会议年份", min_value=1900, max_value=2200, value=dt.date.today().year, step=1, key="collect_year")
        conf = conferences[cid]
        saved = db.seeds(cid, year)
        with st.form("collect_form"):
            raw_urls = st.text_area("官网或获奖页（每行一个网址）", value="\n".join(saved), placeholder="https://会议官网/awards/", key=f"urls_{cid}_{year}")
            extras = st.text_area("论文详情页或 PDF（可选，每行一个网址）", key="extra_urls", help="用来补全作者单位和发表日期；论文元数据 PDF 默认读取前 3 页。")
            maximum = st.number_input("本次最多读取的页面数", min_value=1, max_value=20, value=4, key="max_pages")
            a, b = st.columns(2)
            submit = form_submit(a, "开始采集", "collect_submit", type="primary")
            save = form_submit(b, "仅保存入口", "save_urls")
        if submit or save:
            try:
                urls = urls_from_text(raw_urls)
                extra_urls = urls_from_text(extras)
                if not urls:
                    raise ValueError("请至少填写一个官网或获奖页网址。")
                if submit and len(urls) + len(extra_urls) > maximum:
                    raise ValueError("填写的网址数量超过本次页面上限，请增大上限。")
                if save:
                    for url in urls:
                        db.add_seed(cid, year, url)
                    flash("年度入口已保存，可重复使用。登记不代表已核实官网身份。")
                    st.rerun()
                started = time.perf_counter()
                log_lines = []
                def log(message):
                    log_lines.append(f'+{time.perf_counter() - started:7.1f}s  {message}')
                    st.write(log_lines[-1])
                with st.status("正在读取和提取，请等待本次操作结束。", expanded=True):
                    result = collect_one(db, conf, year, urls, extra_urls, int(maximum), llm=make_llm(), notify=log)
                result["elapsed_seconds"] = time.perf_counter() - started
                result["log_lines"] = log_lines
                st.session_state["last_import"] = result
                flash("采集已结束，请核对本次结果。")
                st.rerun()
            except Exception as exc:
                safe_error(exc)
        with st.expander("还没有找到官网？"):
            st.caption("可让 LLM 建议候选网址；此功能没有搜索引擎，候选需要你打开核实。")
            if st.button("生成网址候选", key="suggest_urls"):
                try:
                    with st.spinner("正在生成候选…"):
                        candidate = make_llm().suggest(conf, year)
                    st.session_state["suggestion"] = (cid, year, candidate)
                except Exception as exc:
                    safe_error(exc)
            suggestion = st.session_state.get("suggestion")
            if suggestion and suggestion[:2] == (cid, year):
                st.json(suggestion[2])
        return

    a, b = st.columns([3, 1])
    cid = a.selectbox("采集会议", list(conferences), format_func=lambda x: conference_label(x, conferences), key="file_conference")
    year = b.number_input("会议年份", min_value=1900, max_value=2200, value=dt.date.today().year, step=1, key="file_year")
    conf = conferences[cid]
    with st.form("file_extract"):
        award_file = st.file_uploader("获奖页正文文件", type=["txt", "html", "htm", "pdf"], key="award_file")
        award_url = st.text_input("获奖正文的真实来源 URL", key="award_file_url")
        metadata_file = st.file_uploader("论文正文或 PDF（可选）", type=["txt", "html", "htm", "pdf"], key="metadata_file")
        metadata_url = st.text_input("论文正文的来源 URL（上传论文时必填）", key="metadata_file_url")
        submit = form_submit(st, "提取并保存", "extract_submit", type="primary")
    if submit:
        try:
            if award_file is None:
                raise ValueError("请上传获奖正文。")
            url_syntax(award_url.strip())
            if bool(metadata_file) != bool(metadata_url.strip()):
                raise ValueError("论文文件和论文来源 URL 需要同时提供。")
            started = time.perf_counter()
            with tempfile.TemporaryDirectory() as temp:
                sources = []
                for file, url, role, sid in [(award_file, award_url, "award", "s1"), (metadata_file, metadata_url, "metadata", "s2")]:
                    if file is None:
                        continue
                    content = file.getvalue()
                    if len(content) > 8 * 1024 * 1024:
                        raise ValueError("单个文件不能超过 8 MiB。")
                    path = Path(temp) / (sid + Path(file.name).suffix.lower())
                    path.write_bytes(content)
                    sources.append(read_local_source(path, url.strip(), role, sid))
                with st.status("正在读取文件并提取…", expanded=True):
                    result = collect_one(db, conf, year, [], local_sources=sources, llm=make_llm(), notify=st.write)
            result["elapsed_seconds"] = time.perf_counter() - started
            st.session_state["last_import"] = result
            flash("文件提取已结束。")
            st.rerun()
        except Exception as exc:
            safe_error(exc)

def review_page(db):
    st.header("记录核验")
    st.caption("核对来源中的奖项、作者与单位对应关系后，更新记录状态。")
    verified_count = len(db.search(status="verified"))
    repository = os.getenv("GITHUB_REPOSITORY", "peekabooXT/CCF-Awards-Agent")
    branch = os.getenv("GITHUB_BRANCH", "main")
    with st.expander("发布已核验记录到 GitHub", expanded=True):
        st.write(f"当前已核验 **{verified_count}** 条；目标仓库 **{repository}**，分支 **{branch}**。")
        st.caption("发布会重新生成四个 Markdown 索引和已核验 JSON 快照；待核验、已排除记录不会上传。内容无变化时不会创建空提交。")
        configured = bool(os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN"))
        if not configured:
            st.info("服务器尚未配置 GITHUB_TOKEN。为避免公网泄露令牌，本页面不提供 Token 输入框。")
        if st.button(
            "发布最新已核验记录到 GitHub", key="publish_verified", type="primary",
            disabled=not configured or verified_count == 0,
        ):
            try:
                with st.spinner("正在生成索引并提交到 GitHub…"):
                    result = publish_verified(db, GitHubPublisher(repository=repository, branch=branch))
                st.session_state["last_publish"] = result
            except Exception as exc:
                safe_error(exc)
        result = st.session_state.get("last_publish")
        if result:
            if result["changed"]:
                st.success(f"已发布 {result['verified_records']} 条已核验记录，更新 {len(result['files'])} 个文件。")
            else:
                st.info("GitHub 上的已核验数据已是最新版本，没有创建新提交。")
            st.link_button("查看 GitHub 提交", result["commit_url"])
    state = st.selectbox("筛选核验状态", ["pending", "verified", "rejected", "all"], format_func=STATUSES.get, key="review_filter")
    records = db.search(status=state)
    if not records:
        st.info("当前状态下没有记录。可以先采集或导入样例。")
        return
    by_id = {r["id"]: r for r in records}
    selected = st.selectbox("选择要核验的论文", list(by_id), format_func=lambda x: f'{by_id[x]["acronym"]} {by_id[x]["year"]} · {by_id[x]["title"]}', key="review_record")
    record = by_id[selected]
    render_detail(record)
    with st.form(f"review_form_{selected}"):
        a, b = st.columns(2)
        states = ["pending", "verified", "rejected"]
        target = a.selectbox("核验结论", states, index=states.index(record["status"]), format_func=STATUSES.get, key=f"review_target_{selected}")
        reviewer = b.text_input("核验人", key=f"reviewer_{selected}")
        note = st.text_area("核验备注", placeholder="记录依据、缺失信息或需要更正的内容", key=f"review_note_{selected}")
        submit = form_submit(st, "保存核验结论", "review_submit", type="primary")
    if submit:
        try:
            db.review(selected, target, require_text(reviewer, "核验人"), require_text(note, "核验备注"))
            flash("核验结论已保存，旧版本已保留。")
            st.rerun()
        except Exception as exc:
            safe_error(exc)


def coverage_page(db, conferences):
    st.header("采集覆盖")
    st.caption("按会议、年份和奖项分别检查。没有找到记录，不等于该年度没有设奖。")
    with st.form("coverage_filter"):
        a, b, c = st.columns([3, 1, 1])
        cid = a.selectbox("会议范围", [None, *conferences], format_func=lambda x: conference_label(x, conferences), key="coverage_conference")
        start = b.number_input("起始年份", min_value=1900, max_value=2200, value=2024, key="coverage_from")
        end = c.number_input("结束年份", min_value=1900, max_value=2200, value=dt.date.today().year, key="coverage_to")
        submit = form_submit(st, "查看覆盖情况", "coverage_submit", type="primary")
    if submit:
        if start > end:
            st.error("起始年份不能晚于结束年份。")
            return
        st.session_state["coverage_query"] = (start, end, cid)
    query = st.session_state.get("coverage_query", (2024, dt.date.today().year, None))
    records = db.coverage(*query)
    st.dataframe([{"会议": r["acronym"], "会议编号": r["conference_id"], "CCF": r["rank"], "年份": r["year"],
                   "奖项": AWARDS[r["award_type"]], "覆盖状态": COVERAGE[r["state"]],
                   "待核验": r["counts"].get("pending", 0), "已核验": r["counts"].get("verified", 0),
                   "备注": r["note"] or ""} for r in records], hide_index=True, width="stretch")
    with st.expander("记录人工检查结论"):
        with st.form("coverage_mark"):
            a, b = st.columns([3, 1])
            selected = a.selectbox("已检查的会议", list(conferences), format_func=lambda x: conference_label(x, conferences), key="mark_conference")
            year = b.number_input("检查年份", min_value=1900, max_value=2200, value=2024, key="mark_year")
            a, b = st.columns(2)
            award = a.selectbox("检查奖项", list(AWARDS), format_func=AWARDS.get, key="mark_award")
            state = b.selectbox("覆盖结论", ["partial", "checked", "not_found", "not_offered"], format_func=COVERAGE.get, key="mark_state")
            url = st.text_input("结论来源网址", key="mark_url")
            note = st.text_area("检查备注", key="mark_note")
            mark = form_submit(st, "保存覆盖结论", "mark_submit")
        if mark:
            try:
                db.mark_coverage(selected, year, award, state, url.strip(), require_text(note, "检查备注"))
                flash("覆盖结论已保存。")
                st.rerun()
            except Exception as exc:
                safe_error(exc)


def main():
    db_path = database_path()
    db = Database(db_path)
    try:
        if not db.conferences():
            db.init()
        default_db = (Path(__file__).resolve().parent / "data" / "awards.sqlite3").resolve()
        if db_path.resolve() == default_db and not db.conn.execute("SELECT 1 FROM records LIMIT 1").fetchone():
            workbooks = sorted((default_db.parent / "exports").glob("CCF190_*_论文奖核验整理版.xlsx"))
            if workbooks:
                import_excel(db, workbooks[-1])
        conferences = {r["id"]: r for r in db.conferences()}
        section = render_sidebar(db)
        if "notice" in st.session_state:
            kind, message = st.session_state.pop("notice")
            getattr(st, kind)(message)
        st.title(APP_NAME)
        st.caption(APP_SUBTITLE)
        st.caption(APP_NAME_ZH)
        all_records = db.search()
        a, b, c = st.columns(3)
        a.metric("会议范围", len(conferences), help="用户提供名单中的 A 类 58 个、B 类 132 个")
        b.metric("已记录奖项", len(all_records), help="包含待核验和已核验；同一论文可获得不同奖项")
        c.metric("待核验", sum(r["status"] == "pending" for r in all_records))
        st.divider()
        if section == "论文检索":
            search_page(db, conferences)
        elif section == "采集与导入":
            collect_page(db, conferences)
        elif section == "记录核验":
            review_page(db)
        else:
            coverage_page(db, conferences)
    finally:
        # No global/cached SQLite connection: each Streamlit rerun owns its connection.
        db.close()


main()
