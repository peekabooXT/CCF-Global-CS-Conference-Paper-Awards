# 把 CCF 获奖论文 Agent 改成网页版本

这一版使用 **Streamlit 网页界面 + 原有 Python 采集逻辑 + 原有 SQLite 数据库**。程序在你的电脑上运行，通过浏览器操作。你无需先学习前后端分离，就能完成论文检索、采集、核验和覆盖检查。

代码已接好。可以先按下面的步骤启动，再对照最后一节理解每个按钮如何调用原来的程序。

## 第一步 准备项目

解压 `ccf-awards-agent-web-v0.2.zip`，进入里面的 `ccf-awards-agent` 文件夹。这个文件夹中应该能直接看到 `streamlit_app.py`、`requirements-web.txt` 和 `ccf_awards` 文件夹。

**如果旧版已经有自己的论文数据：**先关闭旧程序并备份旧版 `data` 文件夹，再将原来的 `data/awards.sqlite3` 和 `data/runs` 复制到新版对应位置。新版使用同一数据库结构，无需重新采集。若原来通过 `CCF_AWARDS_DB` 指定其他数据库，仍可使用那个设置；相对路径现在以项目文件夹为基准。

只想试跑时，不需要复制旧数据。网页首次运行会导入 190 个会议的名单，但不会自动导入论文或发起 API 调用。

## 第二步 确认 Python

在项目文件夹里打开终端，运行：

```bash
python --version
```

需要 Python 3.10 或以上。没有安装时，从 [Python 官方下载页](https://www.python.org/downloads/)安装；Windows 安装时勾选将 Python 加入 PATH。macOS 上若没有 `python` 命令，使用 `python3`。

## 第三步 安装网页依赖

推荐建立项目专用虚拟环境。以下命令无需激活环境，避免 PowerShell 执行策略造成干扰。

Windows：

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-web.txt
```

macOS / Linux：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-web.txt
```

网页依赖固定使用已测试的 Streamlit 1.63.0，并包含提取 PDF 所需的 pypdf。安装时需要访问 Python 包源。

如果你已经在自己的 Python 虚拟环境中，可以直接运行：

```bash
python -m pip install -r requirements-web.txt
```

## 第四步 启动网页

Windows：

```powershell
.venv\Scripts\python.exe -m streamlit run streamlit_app.py
```

macOS / Linux：

```bash
.venv/bin/python -m streamlit run streamlit_app.py
```

在已有虚拟环境中可使用通用命令：

```bash
python -m streamlit run streamlit_app.py
```

然后打开 [http://127.0.0.1:8501](http://127.0.0.1:8501)。终端需要保持运行；关闭终端或按 `Ctrl+C` 会停止网页服务，已经保存的论文仍在数据库中。

本地网页通过 `.streamlit/config.toml` 绑定 `127.0.0.1`，不会默认对局域网或公网开放。

## 第五步 先测试检索

1. 点击左侧 **导入两条样例**。此操作不需要 API，重复点击不会重复插入记录。
2. 在 **论文检索** 中选择 ACL，起始年份填写 2020，结束年份填写 2025。
3. 作者填写 `Julie`，单位填写 `Stanford`。
4. 点击 **搜索论文**，应该看到一条 ACL 2024 的样例。
5. 展开论文详情，检查作者及对应单位、发表日期和来源。
6. 点击 **下载 CSV**，导出当前筛选结果。

如果把单位改为 `Irvine` 再搜索，结果应为零：论文里虽然有该单位的另一名作者，Julie 与这个单位不对应。这正是复合筛选中需要避免的误匹配。

样例仍是上一版的两条真实记录，不是完整获奖库。未知发表日期保持未知；只知道月份的记录显示月份，不会编造具体日期。

## 第六步 配置 API 并采集一届会议

在左侧展开 **LLM 连接设置**，填写：

| 网页输入项 | 填写内容 |
| --- | --- |
| API 地址 | 提供商的 Chat Completions 基础地址，例如 `https://api.openai.com/v1` |
| 模型名称 | 你账户实际可调用的模型名 |
| API Key | 对应提供商的密钥 |
| 请求 JSON 模式 | 默认勾选；提供商不支持该参数时取消勾选 |

输入的参数只用于当前网页会话，不写入数据库、不修改其他会话的环境变量。API Key 留空时使用你本机已有的 `LLM_API_KEY` 环境变量。重启或重新建立网页会话后，可能需要重新填写。

接着：

1. 切换到 **采集与导入 → 读取网页**。
2. 选择 ACL，年份填写 2024。
3. 在入口栏填入 `https://2024.aclweb.org/program/best_papers/`。
4. 要补齐样例论文信息，可在“论文详情页或 PDF”中每行填一个网址：

```text
https://aclanthology.org/2024.acl-long.787/
https://aclanthology.org/2024.acl-long.787.pdf
```

5. 保持页面上限为 4，点击 **开始采集**。
6. 等待结束，查看新增、更新、重复和未通过校验的数量，再到论文检索查看记录。

这一步会将网页正文发送到你配置的 LLM API，并产生相应调用费用。填写参数并不等于连接已经测试成功；首次真实采集也是第一次连接联调。

**仅保存入口**不会调用 LLM。保存后，下次选择相同会议和年份，入口会自动填入。**开始采集**使用当前填写的网址，但不会自动登记为长期入口，需要保存时点击“仅保存入口”。

不知道网址时，可以使用页面下方的 **生成网址候选**。此功能仍只让 LLM 建议 URL，并没有接入搜索引擎；核实后再使用。

## 第七步 使用文件和人工核验

**网页不能直接读取时：**选择“上传正文 / PDF”，上传允许使用的获奖正文，并填写其真实来源 URL。可以另上传论文正文或 PDF，补充作者与单位。单文件上限 8 MiB；作为论文元数据的 PDF 默认读取前 3 页，不支持扫描件 OCR。

**已经整理好 JSON 时：**选择“导入 JSON”。文件结构沿用上一版 `examples` 中的样例；这个入口不调用 API，也会执行原来的字段与证据校验。

**核验记录时：**切换到“记录核验”，选择论文，打开原始来源，核对奖项、作者顺序、单位标号和发表日期，再填写核验人、备注及结论并保存。论文详情保留字段证据，已有核验记录也可以重新查看。

**检查完整性时：**切换到“采集覆盖”，按会议和年份查看。需要记录人工结论时，展开“记录人工检查结论”。“没有查到”与“确认未设奖”是不同状态。已有未排除的获奖记录时，程序会阻止相矛盾的“未设奖”结论。

## 这次具体改了哪些地方

网页的操作仍调用原来的核心方法：

| 网页操作 | 复用的核心方法 |
| --- | --- |
| 下拉框选择会议 | `Database.conferences()` |
| 点击搜索论文 | `Database.search(...)` |
| 保存入口 | `Database.add_seed(...)` |
| 开始网页或文件采集 | `collect_one(...)` |
| 导入 JSON | `Database.ingest(...)` |
| 保存核验结论 | `Database.review(...)` |
| 查看和更新覆盖结论 | `Database.coverage(...)`、`Database.mark_coverage(...)` |

新增文件：

- `streamlit_app.py`：网页入口，分别用函数组织四个工作区。
- `ccf_awards/web_helpers.py`：网页显示文字、CSV 下载等适配功能。
- `requirements-web.txt`：网页依赖。
- `.streamlit/config.toml`：本机监听地址、主题、上传限制及请求保护。
- `tests/test_web.py`：网页交互和会话配置测试。

两个核心改动：

- `LLM.__init__` 增加可选的 `api_key`、`base_url`、`model`、`json_mode` 参数，网页可以传入当前会话的设置。省略参数时，命令行仍按原方式读取环境变量。
- `collect_one` 增加可选的 `llm` 和 `notify` 参数，用网页选定的客户端采集，并将进度显示在页面上。

没有更换数据库，也没有重写检索与证据校验规则。命令行入口继续可用。

要理解最核心的网页连接方式，可以看这个对应关系：

```python
# 实际页面同时收集会议、年份、作者、单位等输入。
with st.form("search_form"):
    author = st.text_input("作者姓名")
    affiliation = st.text_input("作者单位")
    submitted = st.form_submit_button("搜索论文")

if submitted:
    records = db.search(author=author, affiliation=affiliation)
    st.dataframe(export_rows(records), hide_index=True)
```

表单把多个输入集中提交。采集、导入和核验只放在对应按钮的分支里，因此正常页面重跑不会自行再执行一次采集。SQLite 连接也按每次页面执行创建并关闭，没有把连接跨线程缓存。

## 常见问题

| 现象 | 处理方法 |
| --- | --- |
| `No module named streamlit` | 用启动网页的同一个 Python 执行 `-m pip install -r requirements-web.txt` |
| 找不到 `streamlit_app.py` | 先进入能看到该文件的项目文件夹，再运行启动命令 |
| 8501 端口被占用 | 启动时追加 `--server.port 8502`，浏览器打开 `http://127.0.0.1:8502` |
| 网页没有论文 | 点击导入样例，或复制旧数据库，或执行一次真实采集；会议名单不等于论文记录 |
| 数据库不是之前那份 | 检查 `CCF_AWARDS_DB`；默认固定为本项目下的 `data/awards.sqlite3` |
| API 401 / 403 | 检查提供商地址、Key 和该账户的模型调用权限 |
| API 不接受 JSON 参数 | 在连接设置中取消“请求 JSON 模式”后重试 |
| 显示连接参数已填写，但采集失败 | 这条提示只检查是否填写，不会提前调用 API；按实际错误检查配置 |
| 表格中的日期或单位是未知 | 补充论文元数据来源，再采集或人工整理后导入；不会根据模型记忆填补 |

## 验证与后续扩展

交付前 32 项测试全部通过，其中包含通过 Streamlit AppTest 模拟网页操作的测试，没有打开真实浏览器或使用付费 API。测试覆盖样例导入、复合筛选、年份校验、核验持久化、入口保存、缺失 API 配置、模拟采集、页面重跑不重复操作和覆盖状态。旧版的核心回归测试也一并保留。

```bash
python -m unittest discover -s tests -v
```

这是本机、单用户版本，尚未部署公网，也没有账户和多人权限。采集仍按前台一次任务执行；公网部署时再增加登录、任务队列、密钥管理与数据备份。真实 LLM 和网站采集仍需要你配置 API 后联调，程序测试没有代替这一步。

相关官方文档：[安装 Streamlit](https://docs.streamlit.io/get-started/installation/command-line)、[运行应用](https://docs.streamlit.io/develop/api-reference/cli/run)、[表单与执行流程](https://docs.streamlit.io/develop/api-reference/execution-flow)、[AppTest](https://docs.streamlit.io/develop/api-reference/app-testing)。
