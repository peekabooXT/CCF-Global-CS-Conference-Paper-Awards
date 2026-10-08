# Global CS Paper Awards Agent

> **Best Paper and Best Student Paper Awards in Top Computer Science Venues**
>
> 全球计算机顶级论文奖数据库——收录顶级会议与期刊的最佳论文奖和最佳学生论文奖

## 已收录论文

**[全部记录：会议/期刊名称 A–Z](AWARDS.md)** · **[按会议/期刊类别](docs/awards/BY_CATEGORY.md)** · **[按年份](docs/awards/BY_YEAR.md)** · **[按奖项类型](docs/awards/BY_AWARD.md)**

以上页面由数据库自动生成，包含 Best Paper、Best Student Paper、论文名、作者及单位、会议、获奖年份、发表时间、核验状态和官方来源链接。

**v1.0：本地管理 / 服务器公开分离。** 服务器仅部署论文检索、获奖论文展示（获奖事件）和来源收录。本地保留采集与导入、记录核验、采集覆盖、LLM 连接与日志。右上角“审核与发布到服务器 / GitHub”可在人工确认后统一发布已核验数据、四个 Markdown 索引与更新时间。详见 [本地审核与公开发布说明](docs/LOCAL-PUBLIC-PUBLISH.md)。

网页的“采集与导入”支持 **会议多选 × 多个年份/年份区间** 的批量任务，选择数量不受单批上限限制。页面会把计划拆成每批最多 100 个会议年度任务、最多 20 个年份；每批须由用户单独确认，完成后不会自动启动下一批。当前标签页会保存计划进度，切换页面后可继续；连接中断时须先核对日志，重试可能重复调用并产生费用。每批结束后会在同一页面显示任务统计、论文明细、CSV 下载、逐任务状态、耗时和 API token 日志；搜索与结构化提取分别记录输入、输出和总 tokens，最近 50 次底层采集运行也会持久化展示。仅当服务商在响应中返回 `usage` 时才能记录，旧日志无法事后准确补算。

这个项目实现一个获奖论文采集与检索系统：可一次选择多个会议和多个年份或年份区间，自动发现官网与获奖页，读取正文，由 LLM 提取获奖记录，经过字段与证据校验后保存到 SQLite，再按会议、年份、作者、单位等条件组合查询。支持网页界面、命令行和 GitHub Actions。

**当前数据库已接入核验整理版 Excel：包含 2023–2025 完整年度及截至 2026-09-15 已公布的记录，共 327 条目标奖项。会议名单共 190 个：A 类 58 个、B 类 132 个。**

采用 Python 标准库和 SQLite，无需搭建服务器、向量数据库或 Agent 框架。只有读取 PDF 时才需要安装 `pypdf`。LLM 使用可配置的 Chat Completions 兼容接口；无需把 API 密钥交给别人。

## 致谢

感谢[湖南科技大学](https://www.hnust.edu.cn/)、[湖南科技大学计算机科学与工程学院](https://computer.hnust.edu.cn/)以及[服务计算与软件服务新技术湖南省重点实验室](https://computer.hnust.edu.cn/xyxw/4403db98401440288088d39953e56d4d.htm)提供的学习与科研环境。实验室链接指向学院官网介绍。

特别感谢刘建勋（副校长、二级教授）、黄晶副教授、王焕宇教授在本项目建设过程中的帮助、指导与把关。谨向三位老师致以诚挚的谢意。

公开展示版与本地管理版页脚均设有上述单位的索引链接；获奖论文 Markdown 索引在重新生成时也会保留致谢内容。

## 自主搜索并记录

自主流程分成五层，搜索结果本身不会直接变成获奖事实：

1. `web_search` 查找会议官网、主办方或官方出版平台的候选页面；
2. 安全抓取器实际读取候选页面正文或 PDF，不使用搜索结果摘要充当证据；
3. LLM 将论文、奖项、作者、单位和日期提取为结构化 JSON；
4. 本地规则检查奖项名称、原文引文、来源对应和重复记录，新记录默认仍为“待核验”；
5. SQLite 保存可搜索数据，`data/records/*.json` 保存可在 GitHub 复现的证据包，Markdown 索引从数据库重新生成。

设置搜索与提取所需的环境变量：

```powershell
# 结构化提取：默认 DeepSeek，地址和模型已有默认值
$env:DEEPSEEK_API_KEY = "你的 DeepSeek API key"

# 若同一端点同时支持 Chat Completions 和 Responses web_search，可直接复用
$env:SEARCH_REUSE_LLM = "1"

# 端点不支持 web_search 时，改用独立搜索连接
$env:SEARCH_API_KEY = "支持 Responses web_search 的 API key"
$env:SEARCH_MODEL = "支持 web_search 的模型名"
```

然后可以分步或一键运行：

```bash
# 只发现候选官方页面，不入库
python -m global_cs_paper_awards_agent discover --conference ACL --year 2026

# 自动搜索、抓取、提取、校验并保存 evidence JSON
python -m global_cs_paper_awards_agent autocollect --conference ACL --year 2026

# 无人值守处理最多 3 个尚无记录的会议
python -m global_cs_paper_awards_agent agent-run --year 2026 --limit 3

# 从当前数据库重新生成四个 GitHub Markdown 视图
python -m global_cs_paper_awards_agent render-markdown --root .
```

仓库的 [GitHub Actions 工作流](.github/workflows/award-agent.yml) 现在仅验证公开快照和索引时间一致性；不再自动采集、导入或推送数据。所有采集与人工审核均在本机进行。

### 从本地“审核与发布”同步两端

本地填写审核人并确认已核对来源后，可一键将有效待审核数据标为已核验，然后更新服务器公开数据和 GitHub 的 `AWARDS.md` 等索引。被排除的数据不发布；空数据发布需另行确认。发布时间使用同一个 Asia/Shanghai 时间，页面保留两端成功、失败或部分成功的记录。

发布使用本机 Git 登录和受限 SSH 发布密钥，不使用服务器 GitHub Token 或浏览器 API Key。服务器没有审核、采集或发布 HTTP 接口。配置、备份与重试规则详见 [v1.0 发布说明](docs/LOCAL-PUBLIC-PUBLISH.md)。

## 1 先在本机运行离线样例

安装 Python 3.10 或以上版本，在 `Global-CS-Paper-Awards-Agent` 项目文件夹中打开终端。基础功能无需安装第三方依赖。

```bash
python -m global_cs_paper_awards_agent demo
python -m global_cs_paper_awards_agent search
```

有些系统需要把 `python` 改为 `python3`，Windows 也可以使用 `py`。`demo` 会创建数据库并导入会议名单及两条样例，不需要 API、不访问网络，可以重复运行。

运行后可看到论文标题、全部已录入的作者及各自单位、发表日期及日期精度、奖项、会议、年份、CCF 等级、核验状态和来源。样例从以下原始来源人工整理，默认状态仍为待核验：

| 样例 | 奖项 | 发表日期 |
| --- | --- | --- |
| Mission: Impossible Language Models | ACL 2024 Best Paper Award | 2024-08，精确到月 |
| Dataset Regeneration for Sequential Recommendation | KDD 2024 Best Student Paper Award | 未补齐，保留未知 |

ACL 的奖项见[会议获奖页](https://2024.aclweb.org/program/best_papers/)，作者与发表年月见[ACL Anthology](https://aclanthology.org/2024.acl-long.787/)，单位对应关系见[论文首页](https://aclanthology.org/2024.acl-long.787.pdf)。KDD 的奖项见[会议获奖页](https://kdd.org/kdd2024/awards/)，作者及单位见[官方日程](https://kdd.org/kdd2024/research-track-papers/)。样例中的来源文本是少量人工短摘录，并非程序实时抓取的完整快照。

如果不需要样例，只创建空论文数据库：

```bash
python -m global_cs_paper_awards_agent init
```

默认数据库在 `data/awards.sqlite3`。切换数据库时，将 `--db` 放在子命令前，例如 `python -m global_cs_paper_awards_agent --db data/my-papers.sqlite3 init`。备份时复制整个 `data` 目录即可。

仓库中的核验版 Excel 位于 `data/exports/`。网页使用默认数据库且记录表为空时，会自动导入最新的 `CCF190_*_论文奖核验整理版.xlsx`。也可以手动、重复安全地执行：

```bash
python -m global_cs_paper_awards_agent import-excel data/exports/CCF190_2023-2026截至2026-09-15_论文奖核验整理版.xlsx
```

重复导入不会生成重复记录；人工核验后的状态和备注会优先保留。

## 2 使用组合搜索

**不同筛选项之间是 AND 关系，年份和日期端点均包含在范围内。** 标题、作者、单位支持大小写不敏感的包含匹配。作者姓名和机构名称按来源原文保存，中文别名、姓名缩写及机构别名不会自动互相转换。

```bash
# ACL，2020—2025 年，作者姓名包含 Julie
python -m global_cs_paper_awards_agent search --conference ACL --year-from 2020 --year-to 2025 --author Julie

# 同一位作者的人名与单位必须同时匹配
python -m global_cs_paper_awards_agent search --author Julie --affiliation Stanford

# 查学生最佳论文奖；KDD 和 SIGKDD 都能解析到同一会议
python -m global_cs_paper_awards_agent search --conference KDD --award best_student_paper

# 按论文发表日期，而非会议年份筛选
python -m global_cs_paper_awards_agent search --published-from 2024-08-01 --published-to 2024-08-31

# B 类会议，2021—2025 年，只查人工已核验记录并导出
python -m global_cs_paper_awards_agent search --rank B --year-from 2021 --year-to 2025 --status verified --csv results/papers.csv

# 返回完整 JSON，便于以后接网页前端
python -m global_cs_paper_awards_agent search --conference ACL --format json
```

`--status` 默认是 `active`，包含待核验与已核验记录；已排除记录不会默认显示。只看可靠结果时使用 `--status verified`；核查历史时可用 `--status all` 或 `rejected`。

发表日期只知道月份时，内部按整月区间匹配。例如 `2024-08` 会命中 `2024-08-15` 所在的查询区间，但显示仍为 `2024-08`，不会伪造具体日期。发表日期未知的记录不会命中发表日期筛选，但能通过会议年份筛选找到。

## 3 配置多提供商 LLM API

结构化提取默认使用 DeepSeek：`LLM_PROVIDER=deepseek`、基础地址 `https://api.deepseek.com`、模型 `deepseek-flash`。通常只需配置密钥：

```powershell
$env:DEEPSEEK_API_KEY = "你的 DeepSeek API key"
```

目前内置以下配置档；网页端可直接选择，模型也可以从预设或当前账户列表选择，仍可手动填写模型 ID 和 API 地址：

| `LLM_PROVIDER` | 默认地址 | 默认模型 | 默认密钥变量 |
| --- | --- | --- | --- |
| `deepseek`（默认） | `https://api.deepseek.com` | `deepseek-flash` | `DEEPSEEK_API_KEY` |
| `openai` | `https://api.openai.com/v1` | `gpt-5-mini` | `OPENAI_API_KEY` |
| `bailian` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen3.8-max` | `DASHSCOPE_API_KEY` |
| `qwen`（千问，同百炼 API） | 同上 | `qwen3.8-max` | `DASHSCOPE_API_KEY` |
| `zhipu`（智谱） | `https://open.bigmodel.cn/api/paas/v4` | `glm-4.6` | `ZHIPUAI_API_KEY` |
| `custom` | 需要自行填写 | 需要自行填写 | `LLM_API_KEY` |

所有档位都可用 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL` 覆盖，因此其他兼容 Chat Completions 的服务也能接入。例如切换 OpenAI：

```powershell
$env:LLM_PROVIDER = "openai"
$env:OPENAI_API_KEY = "你的 API key"
$env:LLM_MODEL = "你的账户可调用模型"
```

网页界面的单次与批量采集默认使用自动网页搜索；搜索与结构化提取复用“LLM 连接”中当前的提供商、模型和 Key。网页采集必须显式填写 Key，切换提供商时清空旧 Key，不会暗中使用服务器环境变量。DeepSeek 官方连接的搜索使用同一 Key 的 Anthropic 兼容 `/anthropic/v1/messages`；OpenAI、百炼及千问连接使用 Responses `web_search`；智谱连接使用当前模型的 Chat Completions `web_search` 工具。各模型的搜索支持范围不同，若未真正执行搜索或未返回结构化来源会报错，不把模型回答当成来源。网页端在自动采集前提示所用账户及额外 Token 费用，日志及 CSV 记录搜索提供商、模型与 Token 用量。中转站请选择“中转站／自定义 OpenAI 兼容接口”，填写公共 HTTPS 基础地址、该站 Key 和模型 ID；提取要求 `/chat/completions`，自动搜索还要求同一地址的 `/responses` 真正执行 `web_search` 并返回来源，不支持搜索时可用已保存网址。模型列表读取使用该地址的 `/models`；不提供列表的中转站仍可手填模型。

命令行和 GitHub Actions 的搜索配置仍独立：设置 **SEARCH_REUSE_LLM=1** 后复用 LLM 凭据，但命令行搜索器目前仍要求该端点支持 Responses `web_search`，不使用网页端新增的 DeepSeek Anthropic 适配。若不复用，须显式配置独立搜索账户；该账户产生的费用不属于提取账户：

```powershell
$env:SEARCH_API_KEY = "搜索 API key"
$env:SEARCH_MODEL = "支持 Responses web_search 的模型"
# 默认 SEARCH_BASE_URL=https://api.openai.com/v1
```

使用 OpenAI 搜索时也兼容旧变量 `OPENAI_API_KEY`、`OPENAI_SEARCH_MODEL`。其他提供商只有在实际兼容 Responses API 且实现 `web_search` 时才可填入 `SEARCH_BASE_URL`；仅仅声称“OpenAI 兼容”并不代表支持网页搜索。

程序默认请求 JSON mode：`response_format={"type":"json_object"}`。如果某个兼容接口不支持，可设置 `LLM_JSON_MODE=0`；返回内容仍须为合法 JSON，并通过本地证据校验。API 地址必须使用 HTTPS，程序不会跟随携带密钥的重定向，也不会把密钥写入数据库。

参考：[DeepSeek Anthropic API](https://api-docs.deepseek.com/guides/anthropic_api/)、[DeepSeek 网页搜索及费用说明](https://api-docs.deepseek.com/quick_start/agent_integrations/claude_code/)、[DeepSeek Responses API 支持范围](https://api-docs.deepseek.com/guides/responses_api/)、[阿里云百炼网页搜索](https://help.aliyun.com/en/model-studio/web-search)、[百炼模型列表](https://help.aliyun.com/en/model-studio/list-models)、[OpenAI Responses API](https://developers.openai.com/api/reference/cli/resources/responses/methods/create)。

每次采集通常进行一次网页发现调用和一次结构化提取调用；网络返回 429 或 5xx 时最多尝试三次。来源正文和元数据会发送给你配置的提取服务商，新数据仍默认进入“待核验”。

## 4 指定网站并采集

先列出会议，找到名称与编号：

```bash
python -m global_cs_paper_awards_agent conferences --query ACL
python -m global_cs_paper_awards_agent conferences --rank B
python -m global_cs_paper_awards_agent conferences --query FSE
```

文档中 `FSE` 有两个含义：安全领域 Fast Software Encryption（B 类），以及软件工程领域 Foundations of Software Engineering（A 类）。输入 `FSE` 时程序会提示歧义，必须选择 `fse-95a390` 或 `fse-149830`；不会自动合并。

可选地让 LLM 提供网址候选：

```bash
python -m global_cs_paper_awards_agent suggest --conference ACL --year 2024
```

**`suggest` 没有搜索引擎工具，只根据模型返回候选 URL 和搜索词，候选可能过时或错误。** 先打开网址核实，再登记或传入 `collect`。也可以像你设想的那样，在其他 LLM 工具中手动找到官网后直接使用 URL。

登记和采集：

```bash
python -m global_cs_paper_awards_agent source-add --conference ACL --year 2024 --url https://2024.aclweb.org/program/best_papers/
python -m global_cs_paper_awards_agent collect --conference ACL --year 2024
```

也可以不登记，直接采集一个入口：

```bash
python -m global_cs_paper_awards_agent collect --conference KDD --year 2024 --url https://kdd.org/kdd2024/awards/
```

采集器读取入口以及同域中带 award、best-paper 等词的链接，默认最多尝试 4 个页面。网站正文清洗后进入 LLM；被拒绝的记录会在输出 `rejected` 中显示原因，原始提取保存在 `data/runs/`。所有新记录默认待核验。`no_results` 仅表示这次没有提取到符合条件的数据。

### 补充作者单位及发表时间

获奖页经常不提供单位或发表日期。用可重复的 `--extra-url` 指定论文详情页或 PDF，LLM 会结合这些来源提取同一论文的元数据。此版需要你提供这些补充网址，暂未自动逐篇查找 DOI 或论文 PDF。

读取 PDF 时先安装可选依赖：

```bash
python -m pip install -r requirements-pdf.txt
```

例如补充 ACL 样例的发表信息和单位：

```bash
python -m global_cs_paper_awards_agent collect --conference ACL --year 2024 --url https://2024.aclweb.org/program/best_papers/ --extra-url https://aclanthology.org/2024.acl-long.787/ --extra-url https://aclanthology.org/2024.acl-long.787.pdf --max-pages 4
```

作为元数据来源的 PDF 默认读取前 3 页，并在来源中记录读取范围。它适合提取论文首页的作者单位；如果单位在后文，请将相关页导出为文本，使用下一节的文件模式。获奖 PDF 来源本身没有这个 3 页截取规则。

### 页面不能直接读取时

动态网页、扫描 PDF、登录页面或无法读取 robots.txt 的站点，需要手动取得允许使用的正文。把获奖正文保存为 UTF-8 文本，保留真实来源 URL。然后运行：

```bash
python -m global_cs_paper_awards_agent extract-file --conference ACL --year 2024 --file award-page.txt --source-url https://2024.aclweb.org/program/best_papers/
```

可以再附加 `--metadata-file paper.pdf --metadata-url 论文PDF的真实URL`。HTML 文件和可提取文本的 PDF 也能作为文件输入；扫描 PDF 不支持 OCR。

如果不用 LLM，可仿照 `examples/sample-acl-2024.json` 人工填写来源短摘录与记录，再运行：

```bash
python -m global_cs_paper_awards_agent import-json my-extraction.json
```

该方式不访问网络；来源由导入者提供，所以本地证据校验不能证明来源网页真实，记录同样是待核验。

## 5 核验、修改和检查覆盖

搜索结果中有记录编号。打开原始来源确认奖项与论文、作者顺序、单位标号、发表日期，再标记：

```bash
python -m global_cs_paper_awards_agent show 记录编号
python -m global_cs_paper_awards_agent review 记录编号 --status verified --reviewer "你的名字" --note "已核对官方获奖段落、作者及论文首页单位"
```

发现错误时使用 `--status rejected`；需重新检查时使用 `pending`。要更正字段，编辑对应的采集 JSON 或人工 JSON，再用 `import-json` 导入。相同身份的内容变化会归档旧版并回到待核验；完全重复导入不会清除核验状态。标题或奖项身份变化会产生新记录，旧错误记录需人工排除。

去重身份为“会议编号 + 会议年份 + 奖项类型 + track + 规范化标题”。保留标题标点，不会把 C++ 和 C# 合并；明显改写的标题和 track 差异需要人工核查，不进行有风险的模糊合并。作者按每篇论文分别保存，不把同名作者自动合并成一个人。

查询所有会议在一个时间范围的覆盖情况：

```bash
python -m global_cs_paper_awards_agent coverage --year-from 2020 --year-to 2025
python -m global_cs_paper_awards_agent coverage --conference ACL --year-from 2024 --year-to 2024
```

| 状态 | 含义 |
| --- | --- |
| not_started | 尚无记录，也没有人工覆盖结论 |
| partial | 已有部分记录，或已修改数据，需要继续检查完整性 |
| checked | 人工确认已检查该会议年度的该种奖项名单 |
| not_found | 已人工查找，但尚未找到可靠信息 |
| not_offered | 有依据确认该年度没有设置该奖项 |

`coverage` 针对每个会议、每年、每种奖项分别记录。记录数不等于完整性。程序绝不会因返回空数组而自动标记未设奖。人工结论示例：

```bash
python -m global_cs_paper_awards_agent coverage-mark --conference ACL --year 2024 --award best_paper --state partial --url https://2024.aclweb.org/program/best_papers/ --note "当前仅导入一条样例，完整名单尚待采集"
```

登记更多会议年度入口后，可按范围批量采集：

```bash
python -m global_cs_paper_awards_agent batch --from-year 2020 --to-year 2025
python -m global_cs_paper_awards_agent runs
```

没有登记入口的会议年度会明确计入跳过数；某个任务失败后继续其他任务。再次采集会去重，可用于重试。此版未内置定时调度，也不会自动为 190 个会议生成并信任历年 URL。

## 6 数据设计与可扩展位置

| 模块 / 表 | 作用 |
| --- | --- |
| `catalog.py` / `conferences` | 从上传文档生成会议编号、简称、别名、等级和领域 |
| `network.py` / `seeds` | 年度入口管理、受限 HTML/PDF 读取 |
| `llm.py` | 提取提示词、可替换的 LLM API 适配器、网址候选 |
| `model.py` | 奖项精确白名单、字段与引文校验、日期精度、身份计算 |
| `db.py` / `records` | SQLite 持久化和检索；保留各作者的单位与证据 |
| `revisions` | 保存变更前版本及核验历史 |
| `runs` | 成功、失败、无结果、部分成功的任务日志 |
| `coverage` | 每个会议年度奖项的人工覆盖结论 |
| `__main__.py` | 命令行入口与采集编排；未来前端可复用 `Database.search` |

模型只负责从给定来源提取 JSON，不生成 SQL，也不能调用 shell 或执行网页中的指令。来源正文按不可信数据处理。字段校验可以检查引文是否存在、奖项段落是否包含标题、年份是否在来源中出现、日期格式和 URL 等；它不能独立证明网页真实性、作者与单位语义对应，或所有论文已被完整识别。最终核验仍由人完成。

核心记录字段包括 `title`、`conference_id`、`year`、`award_type`、原始 `award_name`、`track`、`authors[].name`、`authors[].affiliations[]`、`publication_date`、`date_precision`、各字段证据及 `sources`。CCF 分类采用用户提供的 2026 名单筛选历史论文，不代表这些会议在历史年份的等级。

## 7 验证与当前边界

执行本地验证：

```bash
python -m unittest discover -s tests -v
```

当前 49 项回归测试和独立进程离线演示均已通过，验证了会议名单、两类奖项、复合过滤、作者单位关联、日期精度、去重、修订、异常证据、任务失败、PDF 元数据读取范围以及 CLI/CSV。采集编排与 API 请求结构使用模拟响应测试；**没有使用你的真实 API 密钥进行付费推理调用，也未批量抓取历年获奖数据。**

现阶段还有这些边界：

- 只接受 `model.py` 中明确列出的 Best Paper / Best Student Paper 英文名称及少量 Research / Applied 变体。其他名称会列出拒绝原因。Outstanding、Distinguished、提名、runner-up、资源奖等不会自动归入最佳论文奖。日后可为有充分官方依据的同义奖项新增映射。
- 最多尝试 20 个页面，默认 4 个；单来源最大 8 MiB。正文总长度超过 100000 字符时，会先按独立的四位数年度标题截取目标年度区间（适用于 AAAI 这类历年汇总页），并在来源中记录截取范围和原始长度；无法可靠定位年度区间或截取后仍超限时明确报错，不静默截断。
- 基础抓取不执行 JavaScript，不绕过登录或网站访问限制，不处理图片文字；PDF 元数据仅默认读取前 3 页。
- 人名与机构使用字符串搜索，没有 ORCID 消歧、跨语言别名、机构更名知识库。
- 运行中强制关闭进程可能留下 `running` 日志；可重跑同一任务，已完成数据不会丢失。并发多人部署不在本版范围内。
- 官方网站推荐列表未重新审定；190 个会议的等级、领域和名称忠实来自用户上传文档。

## 8 建议的下一步

先选 3—5 个常用会议及明确年份范围，用真实 DeepSeek 提取 API 和搜索 API 联调并核对提取质量。当前已具备网页界面、自动网页发现、定时 GitHub Actions 和覆盖检查；下一步可继续提升论文详情页/PDF 自动发现率，并增加失败任务重试与人工复核队列。

这份基础版把“所有 A/B 会议”作为可逐步覆盖的会议范围，把采集完整性单独记录，方便在增加自动化之后继续追踪缺口。
