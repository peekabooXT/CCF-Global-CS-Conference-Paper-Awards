# Global CS Paper Awards

**计算机领域获奖论文数据库**

Global CS Paper Awards 整理计算机领域会议的获奖论文，提供按会议、研究领域、年份和奖项类型浏览与检索的入口。我们希望帮助研究者发现值得阅读的论文，也让每条收录记录的来源便于查证。

## 浏览论文

**[访问在线数据库](http://47.107.172.42/)**

也可以直接在 GitHub 浏览：

| 索引 | 内容 |
| --- | --- |
| [全部论文](AWARDS.md) | 按会议名称 A–Z 排序 |
| [研究领域](docs/awards/BY_CATEGORY.md) | 按会议所属领域浏览 |
| [获奖年份](docs/awards/BY_YEAR.md) | 按年度浏览 |
| [奖项类型](docs/awards/BY_AWARD.md) | 最佳论文、最佳学生论文及其他奖项 |

各索引标注数据更新时间和收录数量。网站提供“论文检索”“论文总览”“会议年度颁奖”三个入口：卡片检索适合逐篇阅读，论文总览用紧凑表格批量筛查，年度颁奖按会议和年份展示奖项与论文。论文总览支持会议多选、年份范围、关键词即时筛选和排序，可导出全部筛选结果 CSV，而不只是当前页。

## 收录范围

会议目录以 **CCF 2026 年 A/B 类会议名单**为基础，共 190 个会议，其中 A 类 58 个、B 类 132 个。目录范围与已收录数据的覆盖范围不同，各会议的实际收录年份以网站和索引为准。

记录保留来源中的奖项原名，包含 Best Paper、Best Student Paper、Outstanding Paper、Distinguished Paper 等名称。同一篇论文获得不同奖项时，分别保留获奖关联。

论文信息包括题名、作者、作者单位、会议、获奖年份、奖项原名、发表时间和来源链接。字段以来源实际提供的信息为准；未公开或尚未补齐的信息标注为未知。

## 数据来源与整理

数据来自会议和主办方的获奖公告、论文出版页面、人工整理资料，以及 [Jeff Huang 的 Best Paper Awards](https://jeffhuang.com/best_paper_awards/) 等聚合来源。

我们在整理时核对来源、处理会议别名与重复条目，并保留原始来源信息。论文详情区分官方获奖证据和聚合收录线索；聚合来源没有给出奖项原名时，记录注明“来源未提供奖项原名”。

网站展示已核验的数据。“已核验”表示经过来源核对，不代表该会议历年的获奖论文已经全部收录。会议年份、论文发表时间和 CCF 分类年份也可能不同。

本站不托管、镜像或提供论文附件下载。论文总览的题名跳转 Google Scholar，公开的外部论文 / 出版页面与官方获奖来源分别列出；本地采集上传的文件不进入公开发布包。CSV 导出仅包含书目信息与链接。

更多说明见 [使用指南](docs/USER-GUIDE.md)和[数据说明](docs/DATA.md)。

## 反馈与补充

如果发现数据错误、遗漏或其他问题，请联系作者邮箱：[peekaboocatx@gmail.com](mailto:peekaboocatx@gmail.com)。如能附上相关论文、会议、年份及来源链接，将有助于核对和修正。


欢迎通过 [Issues](https://github.com/peekabooXT/Global-CS-Paper-Awards/issues) 提交缺失论文、信息更正和使用建议。补充数据时，请附上会议名称、获奖年份、论文题名及官方来源链接，便于核对。

## 关于项目

本仓库只提供已核验论文的数据快照、Markdown 索引和只读展示网站。网站采用 Python、SQLite 和 Vue 构建，不包含数据采集、模型调用、审核管理或研究实验代码。

独立运行与校验方法见[运行说明](docs/RUNNING.md)。

## 致谢

感谢[湖南科技大学](https://www.hnust.edu.cn/)、[湖南科技大学计算机科学与工程学院](https://computer.hnust.edu.cn/)以及服务计算与软件服务新技术湖南省重点实验室提供的学习与科研环境。

特别感谢[刘建勋](https://faculty.hnust.edu.cn/pubtphp/jsjkxygcxy/1050037/chinese/index.html)教授、[王焕宇](https://faculty.hnust.edu.cn/pubtphp/jsjkxygcxy/1050148/chinese/index.html)教授、[黄晶](https://faculty.hnust.edu.cn/pubtphp/jsjkxygcxy/1050135/chinese/index.html)教授在本项目建设过程中的帮助、指导与把关。谨向三位老师致以诚挚的谢意。
