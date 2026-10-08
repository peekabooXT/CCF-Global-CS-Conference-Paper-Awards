# Global CS Paper Awards Agent

**计算机领域获奖论文数据库**

Global CS Paper Awards Agent 整理计算机领域会议的获奖论文，提供按会议、研究领域、年份和奖项类型浏览与检索的入口。我们希望帮助研究者发现值得阅读的论文，也让每条收录记录的来源便于查证。

## 浏览论文

**[访问在线数据库](http://47.107.172.42/)**

也可以直接在 GitHub 浏览：

| 索引 | 内容 |
| --- | --- |
| [全部论文](AWARDS.md) | 按会议名称 A–Z 排序 |
| [研究领域](docs/awards/BY_CATEGORY.md) | 按会议所属领域浏览 |
| [获奖年份](docs/awards/BY_YEAR.md) | 按年度浏览 |
| [奖项类型](docs/awards/BY_AWARD.md) | 最佳论文、最佳学生论文及其他奖项 |

各索引标注数据更新时间和收录数量。网站支持组合筛选、论文详情与 CSV 导出；“会议年度颁奖”页面按会议和年份展示奖项与论文。

## 收录范围

会议目录以 **CCF 2026 年 A/B 类会议名单**为基础，共 190 个会议，其中 A 类 58 个、B 类 132 个。目录范围与已收录数据的覆盖范围不同，各会议的实际收录年份以网站和索引为准。

记录保留来源中的奖项原名，包含 Best Paper、Best Student Paper、Outstanding Paper、Distinguished Paper 等名称。同一篇论文获得不同奖项时，分别保留获奖关联。

论文信息包括题名、作者、作者单位、会议、获奖年份、奖项原名、发表时间和来源链接。字段以来源实际提供的信息为准；未公开或尚未补齐的信息标注为未知。

## 数据来源与整理

数据来自会议和主办方的获奖公告、论文出版页面、人工整理资料，以及 [Jeff Huang 的 Best Paper Awards](https://jeffhuang.com/best_paper_awards/) 等聚合来源。

我们在整理时核对来源、处理会议别名与重复条目，并保留原始来源信息。论文详情区分官方获奖证据和聚合收录线索；聚合来源没有给出奖项原名时，记录注明“来源未提供奖项原名”。

网站展示已核验的数据。“已核验”表示经过来源核对，不代表该会议历年的获奖论文已经全部收录。会议年份、论文发表时间和 CCF 分类年份也可能不同。

更多说明见 [使用指南](docs/USER-GUIDE.md)和[数据说明](docs/DATA.md)。

## 反馈与补充

欢迎通过 [Issues](https://github.com/peekabooXT/Global-CS-Paper-Awards-Agent/issues) 提交缺失论文、信息更正和使用建议。补充数据时，请附上会议名称、获奖年份、论文题名及官方来源链接，便于核对。

## 关于项目

项目采用 Python、SQLite 和 Vue 构建，结合自动采集与人工核验持续整理获奖资料。本仓库提供项目源码、数据快照和论文索引。

## 致谢

感谢[湖南科技大学](https://www.hnust.edu.cn/)、[湖南科技大学计算机科学与工程学院](https://computer.hnust.edu.cn/)以及服务计算与软件服务新技术湖南省重点实验室提供的学习与科研环境。

特别感谢[刘建勋](https://faculty.hnust.edu.cn/pubtphp/jsjkxygcxy/1050037/chinese/index.html)教授、[王焕宇](https://faculty.hnust.edu.cn/pubtphp/jsjkxygcxy/1050148/chinese/index.html)教授、[黄晶](https://faculty.hnust.edu.cn/pubtphp/jsjkxygcxy/1050135/chinese/index.html)教授在本项目建设过程中的帮助、指导与把关。谨向三位老师致以诚挚的谢意。
