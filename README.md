# CCF A/B 会议获奖论文 Agent 基础版

这个项目实现一个本地、单用户的采集与检索工具：指定会议某一年的官网或获奖页，读取正文，由 LLM 提取获奖记录，经过字段与证据校验后保存到 SQLite，再按会议、年份、作者、单位等条件组合查询。当前交付为命令行程序，没有网页界面。

**版本 0.1 已实现采集、保存、人工核验、组合检索和 CSV 导出。会议名单来自你上传的文档，共 190 个会议：A 类 58 个、B 类 132 个。名单已全部导入种子文件；历年获奖数据尚未全量采集。项目提供两条真实获奖样例用于试跑。**

采用 Python 标准库和 SQLite，无需搭建服务器、向量数据库或 Agent 框架。只有读取 PDF 时才需要安装 `pypdf`。LLM 使用可配置的 Chat Completions 兼容接口；无需把 API 密钥交给别人。

## 1 先在本机运行离线样例

安装 Python 3.10 或以上版本，把压缩包解压，在 `ccf-awards-agent` 文件夹中打开终端。基础功能无需安装第三方依赖。

```bash
python -m ccf_awards demo
python -m ccf_awards search
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
python -m ccf_awards init
```

默认数据库在 `data/awards.sqlite3`。切换数据库时，将 `--db` 放在子命令前，例如 `python -m ccf_awards --db data/my-papers.sqlite3 init`。备份时复制整个 `data` 目录即可。

## 2 使用组合搜索

**不同筛选项之间是 AND 关系，年份和日期端点均包含在范围内。** 标题、作者、单位支持大小写不敏感的包含匹配。作者姓名和机构名称按来源原文保存，中文别名、姓名缩写及机构别名不会自动互相转换。

```bash
# ACL，2020—2025 年，作者姓名包含 Julie
python -m ccf_awards search --conference ACL --year-from 2020 --year-to 2025 --author Julie

# 同一位作者的人名与单位必须同时匹配
python -m ccf_awards search --author Julie --affiliation Stanford

# 查学生最佳论文奖；KDD 和 SIGKDD 都能解析到同一会议
python -m ccf_awards search --conference KDD --award best_student_paper

# 按论文发表日期，而非会议年份筛选
python -m ccf_awards search --published-from 2024-08-01 --published-to 2024-08-31

# B 类会议，2021—2025 年，只查人工已核验记录并导出
python -m ccf_awards search --rank B --year-from 2021 --year-to 2025 --status verified --csv results/papers.csv

# 返回完整 JSON，便于以后接网页前端
python -m ccf_awards search --conference ACL --format json
```

`--status` 默认是 `active`，包含待核验与已核验记录；已排除记录不会默认显示。只看可靠结果时使用 `--status verified`；核查历史时可用 `--status all` 或 `rejected`。

发表日期只知道月份时，内部按整月区间匹配。例如 `2024-08` 会命中 `2024-08-15` 所在的查询区间，但显示仍为 `2024-08`，不会伪造具体日期。发表日期未知的记录不会命中发表日期筛选，但能通过会议年份筛选找到。

## 3 配置 LLM API

程序直接请求 `LLM_BASE_URL/chat/completions`。提供商需要支持 `model`、`messages` 以及 `choices[0].message.content` 响应。模型名称必须由你填写为账户实际可调用的模型。

Linux / macOS，在当前终端设置：

```bash
export LLM_BASE_URL="https://api.openai.com/v1"
export LLM_MODEL="填写你可调用的模型名"
read -s -p "API key: " LLM_API_KEY
export LLM_API_KEY
```

Windows PowerShell：

```powershell
$env:LLM_BASE_URL = "https://api.openai.com/v1"
$env:LLM_MODEL = "填写你可调用的模型名"
$secret = Read-Host "API key" -AsSecureString
$env:LLM_API_KEY = [System.Net.NetworkCredential]::new("", $secret).Password
```

使用其他提供商时，替换 `LLM_BASE_URL` 和 `LLM_MODEL`。API 地址要求 HTTPS，程序不会跟随带密钥请求的重定向。默认请求 JSON mode：`response_format={"type":"json_object"}`。如果提供商不支持此参数，可设置 `LLM_JSON_MODE=0`；返回内容仍必须是合法 JSON，并通过本地校验。程序不会自动读取 `.env`。

JSON mode 只约束 JSON 格式，不能保证事实正确，因此新数据不会自动成为已核验记录。协议依据：[Chat Completions 官方接口](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)及[Structured Outputs 文档](https://developers.openai.com/api/docs/guides/structured-outputs)。

每次采集通常调用一次 LLM；网络返回 429 或 5xx 时最多尝试三次。`batch` 的调用量随已登记会议年度入口数量增长。来源正文和元数据会发送到你配置的 API 提供商，本地不会保存 API 密钥。

## 4 指定网站并采集

先列出会议，找到名称与编号：

```bash
python -m ccf_awards conferences --query ACL
python -m ccf_awards conferences --rank B
python -m ccf_awards conferences --query FSE
```

文档中 `FSE` 有两个含义：安全领域 Fast Software Encryption（B 类），以及软件工程领域 Foundations of Software Engineering（A 类）。输入 `FSE` 时程序会提示歧义，必须选择 `fse-95a390` 或 `fse-149830`；不会自动合并。

可选地让 LLM 提供网址候选：

```bash
python -m ccf_awards suggest --conference ACL --year 2024
```

**`suggest` 没有搜索引擎工具，只根据模型返回候选 URL 和搜索词，候选可能过时或错误。** 先打开网址核实，再登记或传入 `collect`。也可以像你设想的那样，在其他 LLM 工具中手动找到官网后直接使用 URL。

登记和采集：

```bash
python -m ccf_awards source-add --conference ACL --year 2024 --url https://2024.aclweb.org/program/best_papers/
python -m ccf_awards collect --conference ACL --year 2024
```

也可以不登记，直接采集一个入口：

```bash
python -m ccf_awards collect --conference KDD --year 2024 --url https://kdd.org/kdd2024/awards/
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
python -m ccf_awards collect --conference ACL --year 2024 --url https://2024.aclweb.org/program/best_papers/ --extra-url https://aclanthology.org/2024.acl-long.787/ --extra-url https://aclanthology.org/2024.acl-long.787.pdf --max-pages 4
```

作为元数据来源的 PDF 默认读取前 3 页，并在来源中记录读取范围。它适合提取论文首页的作者单位；如果单位在后文，请将相关页导出为文本，使用下一节的文件模式。获奖 PDF 来源本身没有这个 3 页截取规则。

### 页面不能直接读取时

动态网页、扫描 PDF、登录页面或无法读取 robots.txt 的站点，需要手动取得允许使用的正文。把获奖正文保存为 UTF-8 文本，保留真实来源 URL。然后运行：

```bash
python -m ccf_awards extract-file --conference ACL --year 2024 --file award-page.txt --source-url https://2024.aclweb.org/program/best_papers/
```

可以再附加 `--metadata-file paper.pdf --metadata-url 论文PDF的真实URL`。HTML 文件和可提取文本的 PDF 也能作为文件输入；扫描 PDF 不支持 OCR。

如果不用 LLM，可仿照 `examples/sample-acl-2024.json` 人工填写来源短摘录与记录，再运行：

```bash
python -m ccf_awards import-json my-extraction.json
```

该方式不访问网络；来源由导入者提供，所以本地证据校验不能证明来源网页真实，记录同样是待核验。

## 5 核验、修改和检查覆盖

搜索结果中有记录编号。打开原始来源确认奖项与论文、作者顺序、单位标号、发表日期，再标记：

```bash
python -m ccf_awards show 记录编号
python -m ccf_awards review 记录编号 --status verified --reviewer "你的名字" --note "已核对官方获奖段落、作者及论文首页单位"
```

发现错误时使用 `--status rejected`；需重新检查时使用 `pending`。要更正字段，编辑对应的采集 JSON 或人工 JSON，再用 `import-json` 导入。相同身份的内容变化会归档旧版并回到待核验；完全重复导入不会清除核验状态。标题或奖项身份变化会产生新记录，旧错误记录需人工排除。

去重身份为“会议编号 + 会议年份 + 奖项类型 + track + 规范化标题”。保留标题标点，不会把 C++ 和 C# 合并；明显改写的标题和 track 差异需要人工核查，不进行有风险的模糊合并。作者按每篇论文分别保存，不把同名作者自动合并成一个人。

查询所有会议在一个时间范围的覆盖情况：

```bash
python -m ccf_awards coverage --year-from 2020 --year-to 2025
python -m ccf_awards coverage --conference ACL --year-from 2024 --year-to 2024
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
python -m ccf_awards coverage-mark --conference ACL --year 2024 --award best_paper --state partial --url https://2024.aclweb.org/program/best_papers/ --note "当前仅导入一条样例，完整名单尚待采集"
```

登记更多会议年度入口后，可按范围批量采集：

```bash
python -m ccf_awards batch --from-year 2020 --to-year 2025
python -m ccf_awards runs
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

交付前已通过 22 项回归测试和独立进程离线演示，验证了会议名单、两类奖项、复合过滤、作者单位关联、日期精度、去重、修订、异常证据、任务失败、PDF 元数据读取范围以及 CLI/CSV。采集编排与 API 请求结构使用模拟响应测试；**没有使用你的真实 API 密钥进行付费推理调用，也未批量抓取历年获奖数据。**

现阶段还有这些边界：

- 只接受 `model.py` 中明确列出的 Best Paper / Best Student Paper 英文名称及少量 Research / Applied 变体。其他名称会列出拒绝原因。Outstanding、Distinguished、提名、runner-up、资源奖等不会自动归入最佳论文奖。日后可为有充分官方依据的同义奖项新增映射。
- 最多尝试 20 个页面，默认 4 个；单来源最大 8 MiB，正文总长度上限 100000 字符，超过时明确报错，不静默截断。长获奖列表可按页面或片段分批采集。
- 基础抓取不执行 JavaScript，不绕过登录或网站访问限制，不处理图片文字；PDF 元数据仅默认读取前 3 页。
- 人名与机构使用字符串搜索，没有 ORCID 消歧、跨语言别名、机构更名知识库。
- 运行中强制关闭进程可能留下 `running` 日志；可重跑同一任务，已完成数据不会丢失。并发多人部署不在本版范围内。
- 官方网站推荐列表未重新审定；190 个会议的等级、领域和名称忠实来自用户上传文档。

## 8 建议的下一步

先选 3—5 个常用会议及明确年份范围，用真实 API 调通并核对提取质量。随后增加网页查询界面；再加入论文详情页与 PDF 的自动发现；最后扩展搜索引擎 API、定时更新和覆盖率面板。每一步都可以复用现有数据库和检索逻辑。

这份基础版把“所有 A/B 会议”作为可逐步覆盖的会议范围，把采集完整性单独记录，方便在增加自动化之后继续追踪缺口。
