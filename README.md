# CCF Global CS Conference Paper Awards

**English** | [简体中文](README.zh-CN.md)

An index of award-winning papers from **China Computer Federation (CCF) A/B conferences**, with original award names and verifiable sources.

**[Browse the website](http://47.107.172.42/?lang=en)** · [中文网站](http://47.107.172.42/?lang=zh)

The website opens in Chinese for new visitors. Use **中文 | English** in the upper-right corner to switch languages. Your choice is remembered by the browser. The interface language does not change paper titles, author names, original award names, evidence or the underlying records.

## Explore the collection

The default page is **Paper overview**, followed by **Annual conference awards** and **Paper search**.

- **Paper overview:** compact tables, multiple conference selection, instant keyword filtering and sorting. The default page size is 10.
- **Annual conference awards:** awards and indexed winning papers grouped by conference and year.
- **Paper search:** combine conference, CCF tier, award category, year, title, author, affiliation and publication-date filters. The default page size is 5.

Both paper views support page sizes of 5, 10, 15, 20, 30 and 50. CSV exports include all filtered results, not just the current page; interface headers follow the selected language.

You can also browse the versioned Markdown indices. These retain original-language bibliographic metadata and source links:

| Index | Contents |
| --- | --- |
| [All papers](AWARDS.md) | Conferences in A–Z order |
| [Research areas](docs/awards/BY_CATEGORY.md) | Conference research areas |
| [Award years](docs/awards/BY_YEAR.md) | Year-by-year listings |
| [Award categories](docs/awards/BY_AWARD.md) | Paper, student-paper and other awards |

## Scope and provenance

The catalogue follows the supplied **CCF 2026 A/B conference list**: 190 conferences, including 58 in tier A and 132 in tier B. Catalogue membership does not imply complete historical coverage, or the same CCF tier in every historical year. Actual coverage is shown by the records.

Original names such as Best Paper, Best Student Paper, Outstanding Paper and Distinguished Paper are retained. Multiple awards and sources for one paper are combined in search results while preserving their associations. Unknown fields are marked as unknown rather than inferred.

Sources include conference and organizer announcements, publisher pages, manually reviewed material and aggregators such as [Jeff Huang's Best Paper Awards](https://jeffhuang.com/best_paper_awards/). Official award evidence is distinguished from aggregator provenance. Verification applies to indexed records; it is not a completeness guarantee for a conference or year.

This site does not host, mirror or distribute paper attachments. Titles link to Google Scholar; known publication pages and award sources are listed separately. Locally uploaded attachments are not included in public releases.

## Documentation and data

- [User guide](docs/USER-GUIDE.md) · [中文使用指南](docs/USER-GUIDE.zh-CN.md)
- [Data notes](docs/DATA.md) · [中文数据说明](docs/DATA.zh-CN.md)
- [Run the viewer locally](docs/RUNNING.md) · [中文运行说明](docs/RUNNING.zh-CN.md)
- [Reviewed data snapshot](data/exports/public-data.json) · [Publication manifest](data/exports/publication.json)

This repository contains reviewed data, Markdown indices and a read-only viewer built with Python, SQLite and Vue. Collection, model calls, review administration and research experiments belong to the private maintainer repository.

## Corrections and contributions

If you find errors, omissions or other problems, please contact the author at **[peekaboocatx@gmail.com](mailto:peekaboocatx@gmail.com)** or open an [issue](https://github.com/peekabooXT/Global-CS-Paper-Awards/issues). Please include the conference, year, paper title and an official source when available.

## Acknowledgements

We thank [Hunan University of Science and Technology](https://www.hnust.edu.cn/), its [School of Computer Science and Engineering](https://computer.hnust.edu.cn/), and the Hunan Provincial Key Laboratory of Service Computing and Novel Software Service Technologies for the learning and research environment.

Special thanks to Professors [Jianxun Liu](https://faculty.hnust.edu.cn/pubtphp/jsjkxygcxy/1050037/chinese/index.html), [Huanyu Wang](https://faculty.hnust.edu.cn/pubtphp/jsjkxygcxy/1050148/chinese/index.html) and [Jing Huang](https://faculty.hnust.edu.cn/pubtphp/jsjkxygcxy/1050135/chinese/index.html) for their help, guidance and review throughout the project.
