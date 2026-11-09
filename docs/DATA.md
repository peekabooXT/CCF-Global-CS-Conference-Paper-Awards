# Data notes

**English** | [简体中文](DATA.zh-CN.md)

## Catalogue and coverage

The conference catalogue uses the supplied CCF 2026 A/B classification and contains 190 conferences. This classification supports current browsing and filtering; it does not imply the same tier in every historical year.

Not every conference has complete data for every year. Actual coverage is defined by the records in the indices and search results. Missing years and sources remain subject to future collection and review.

## Records and awards

An award record associates a paper with an award at a conference in a given year. Conference aliases, typographical title variants and confirmed duplicates are reconciled while distinct award associations are retained.

Original award names are preserved. Generic browsing categories distinguish paper awards, student-paper awards and other awards; relevant Outstanding and Distinguished paper awards are included in the corresponding categories. Categories facilitate retrieval and do not replace original names.

Some aggregator listings do not supply an official award name. They are marked accordingly, and their collection provenance is kept separate from official award evidence.

## Fields

| Field | Meaning |
| --- | --- |
| Award year | Conference or award year recorded by the source |
| Publication date | Date in the publication metadata; it may differ from the award year |
| Authors and affiliations | Sourced names and institutions; unmatched associations retain the original text |
| Review status | Current source-verification status |
| Source | Official announcement, publication page or aggregator listing |

Month-level dates remain month-level; no day is invented. Missing information is not inferred from an author name, a conference year or another record.

## Verification and languages

Collection combines automated discovery with manual source checks. The website and reader indices expose reviewed data and traceable source links. Verification is a statement about indexed records, not a completeness guarantee for a conference or year.

Chinese and English interfaces use the same snapshot and database. Language switching translates interface text, generic category labels and CSV headers. It does not modify or translate paper titles, original award names, authors, affiliations or quoted evidence.

## Versioned data

[publication.json](../data/exports/publication.json) records the release, timestamp and counts. [public-data.json](../data/exports/public-data.json) holds the corresponding snapshot. Presentation-only updates may change the deployed website commit without changing the data-publication timestamp.

External aggregators include [Jeff Huang's Best Paper Awards](https://jeffhuang.com/best_paper_awards/). Consult each record's source links for its specific provenance. Send corrections with evidence through [Issues](https://github.com/peekabooXT/CCF-Global-CS-Conference-Paper-Awards/issues) or [email](mailto:peekaboocatx@gmail.com).
