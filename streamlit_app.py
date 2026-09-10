"""Run from this folder: python -m streamlit run streamlit_app.py

This file only builds the UI. Database.search, collect_one, and Database.review
continue to own the underlying behavior used by both the web app and the CLI.
"""
import datetime as dt
import inspect
import json
import os
import tempfile
from pathlib import Path

import streamlit as st

from ccf_awards.__main__ import collect_one
from ccf_awards.db import Database
from ccf_awards.llm import LLM
from ccf_awards.model import require_text, url_syntax
from ccf_awards.network import read_local_source
from ccf_awards.web_helpers import (
    AWARDS, COVERAGE, STATUSES, csv_bytes, database_path, export_rows,
    import_demo, urls_from_text, validate_filters,
)

st.set_page_config(page_title="CCF 获奖论文库", page_icon="📑", layout="wide")


def conference_label(cid, conferences):
    if cid is None:
        return "全部会议"
    c = conferences[cid]
    return f'{c["acronym"]} · {c["rank"]} 类 · {c["area"]}'


def make_llm():
    return LLM(api_key=st.session_state.get("api_key") or None,
               base_url=st.session_state.get("base_url") or None,
               model=st.session_state.get("model_name") or None,
               json_mode=st.session_state.get("json_mode", True))


def flash(message, kind="success"):
    st.session_state["notice"] = (kind, message)


def safe_error(exc):
    message = str(exc)
    # Defensive redaction in UI; backend already omits provider response bodies.
    for secret in (st.session_state.get("api_key"), os.getenv("LLM_API_KEY")):
        if secret:
            message = message.replace(secret, "[已隐藏]")
    st.error(message)


def form_submit(container, label, key, **kwargs):
    """Keep form buttons working on both older and current Streamlit releases."""
    button = container.form_submit_button
    if "key" in inspect.signature(button).parameters:
        kwargs["key"] = key
    return button(label, **kwargs)


def render_sidebar(db):
    with st.sidebar:
        st.title("CCF 获奖论文库")
        st.caption("A / B 类会议 · 本地工作台")
        section = st.radio("工作区", ["论文检索", "采集与导入", "记录核验", "采集覆盖"], key="section")
        st.divider()
        with st.expander("LLM 连接设置"):
            st.caption("检索和样例导入不需要 API。设置只在当前网页会话中使用。")
            st.text_input("API 地址", value=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"), key="base_url")
            st.text_input("模型名称", value=os.getenv("LLM_MODEL", ""), key="model_name", placeholder="填写账户可调用的模型")
            st.text_input("API Key", type="password", key="api_key", help="留空时读取本机 LLM_API_KEY 环境变量；不会写入数据库。")
            st.checkbox("请求 JSON 模式", value=os.getenv("LLM_JSON_MODE", "1") == "1", key="json_mode")
            if st.session_state.get("model_name") and (st.session_state.get("api_key") or os.getenv("LLM_API_KEY")):
                st.caption("连接参数已填写；尚不代表连接测试成功。")
        if st.button("导入两条样例", key="demo", use_container_width=True):
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
        st.dataframe(author_rows, hide_index=True, use_container_width=True)
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
    st.dataframe([{k: row[k] for k in keys} for row in rows], hide_index=True, use_container_width=True)
    by_id = {r["id"]: r for r in results}
    selected = st.selectbox("选择论文查看作者、单位和来源", list(by_id), format_func=lambda x: f'{by_id[x]["acronym"]} {by_id[x]["year"]} · {by_id[x]["title"]}', key="detail_record")
    st.markdown("#### 论文详情")
    render_detail(by_id[selected])


def show_import_result(result):
    st.write(f'新增 {result["inserted"]} 条 · 更新 {result["updated"]} 条 · 重复 {result["unchanged"]} 条')
    if result.get("status") == "no_results":
        st.info("本次未提取到符合条件的记录，不代表该年度未设奖。")
    if result["rejected"]:
        st.warning(f'{len(result["rejected"])} 条记录未通过校验，请查看具体原因。')
        st.json(result["rejected"])
    if result.get("warnings"):
        st.warning("部分相关页面未能读取，本次采集可能不完整。")
        st.json(result["warnings"])


def collect_page(db, conferences):
    st.header("采集与导入")
    st.caption("从会议获奖页提取记录，或导入已整理的文件。新增记录默认待核验。")
    if st.session_state.get("last_import"):
        with st.expander("最近一次操作结果", expanded=True):
            show_import_result(st.session_state["last_import"])
    method = st.radio("数据来源", ["读取网页", "上传正文 / PDF", "导入 JSON"], horizontal=True, key="import_method")
    if method == "导入 JSON":
        with st.form("json_import"):
            upload = st.file_uploader("选择符合样例结构的提取 JSON", type=["json"], key="json_upload")
            submitted = form_submit(st, "导入记录", "json_submit", type="primary")
        if submitted:
            try:
                if upload is None:
                    raise ValueError("请先选择 JSON 文件。")
                result = db.ingest(json.loads(upload.getvalue().decode("utf-8-sig")))
                st.session_state["last_import"] = result
                flash("文件已处理，可到论文检索页查看有效记录。", "warning" if result["rejected"] else "success")
                st.rerun()
            except Exception as exc:
                safe_error(exc)
        st.caption("不调用 API。文件结构可参考 examples 中的 JSON。")
        return
    a, b = st.columns([3, 1])
    cid = a.selectbox("采集会议", list(conferences), format_func=lambda x: conference_label(x, conferences), key="collect_conference")
    year = b.number_input("会议年份", min_value=1900, max_value=2200, value=dt.date.today().year, step=1, key="collect_year")
    conf = conferences[cid]
    if method == "读取网页":
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
                llm = make_llm()
                with st.status("正在读取和提取，请等待本次操作结束。", expanded=True):
                    result = collect_one(db, conf, year, urls, extra_urls, int(maximum), llm=llm, notify=st.write)
                st.session_state["last_import"] = result
                flash("采集已结束，请核对本次结果。")
                st.rerun()
            except Exception as exc:
                safe_error(exc)
        with st.expander("还没有找到官网？"):
            st.caption("可让 LLM 建议候选网址；此功能没有接搜索引擎，候选需要你打开核实。")
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
    else:
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
                llm = make_llm()
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
                        result = collect_one(db, conf, year, [], local_sources=sources, llm=llm, notify=st.write)
                st.session_state["last_import"] = result
                flash("文件提取已结束。")
                st.rerun()
            except Exception as exc:
                safe_error(exc)


def review_page(db):
    st.header("记录核验")
    st.caption("核对来源中的奖项、作者与单位对应关系后，更新记录状态。")
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
                   "备注": r["note"] or ""} for r in records], hide_index=True, use_container_width=True)
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
    db = Database(database_path())
    try:
        if not db.conferences():
            db.init()
        conferences = {r["id"]: r for r in db.conferences()}
        section = render_sidebar(db)
        if "notice" in st.session_state:
            kind, message = st.session_state.pop("notice")
            getattr(st, kind)(message)
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
