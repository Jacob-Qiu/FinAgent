# FinAgent 本地知识库目录说明

`kb/` 是 FinAgent 扩展层的数据工程根目录，用来存放本地知识库原始语料、股票池配置，以及 Qdrant/SQLite 检索索引的默认输出位置。

这个目录现在看起来比较空，是因为研报、财报、百科、术语等真实语料还没有全部放进来。它不是废弃目录，后续 RAG 入库、检索和历史行情股票池都会依赖这里的路径约定。

## 目录结构

| 路径 | 用途 | 当前状态 |
|---|---|---|
| `stock_universe.yaml` | 历史行情数据工程使用的股票池配置 | 已使用，不能随意删除 |
| `raw_reports/` | 放研报、券商报告原文 | 等待真实研报样本 |
| `raw_filings/` | 放财报、公告、SEC filing、年报/季报原文 | 等待真实财报样本 |
| `raw_encyclopedia/` | 放百科、背景知识、行业/概念说明 | 等待真实百科语料 |
| `raw_glossary/` | 放金融术语库 | 目前有术语 CSV 模板 |
| `qdrant/` | Qdrant 本地向量库和 SQLite 关键词索引默认输出目录 | build 后生成真实索引文件 |

## 原始语料目录

### `raw_reports/`

用于存放研报和券商报告原文，供新 KB 管线切片、向量化并写入 Qdrant。

推荐格式：

- `.pdf`
- `.md`
- `.markdown`
- `.txt`

推荐文件名：

```text
ticker_publishdate_broker_subject.pdf
```

示例：

```text
0700_20240115_中金公司_腾讯控股深度报告.pdf
NVDA_20240220_MorganStanley_AI_supply_chain.md
```

入库后主要供 `retrieve_reports` 工具检索。

### `raw_filings/`

用于存放财报、公告、SEC filings、港股年报、A 股定期报告等财务披露文件。

支持格式：

- `.pdf`
- `.md`
- `.markdown`
- `.txt`
- `.html`
- `.htm`
- `.xhtml`
- `.xml`
- `.csv`
- `.json`

推荐文件名：

```text
ticker_periodend_reporttype_issuer_or_title.ext
```

示例：

```text
000001_20231231_annual_report_平安银行2023年年度报告.pdf
000001_20240630_semiannual_report_平安银行2024年半年度报告.pdf
000001_20240930_q3_report_平安银行2024年三季报.pdf
AAPL_20230930_10-K_Apple_FY2023.html
0700_20231231_annual_report_腾讯控股2023年年报.xhtml
```

入库时会尽量解析并保存：

- `ticker`
- `issuer`
- `period_end`
- `report_type`
- `statement_type`

入库后主要供 `retrieve_filings` 工具检索。

### `raw_encyclopedia/`

用于存放百科、背景资料、概念说明、行业知识、政策背景等通用知识材料。

推荐格式：

- 带 `# / ## / ###` heading 的 Markdown
- 分段清晰的 `.txt`
- 只有 PDF 版本时可放 `.pdf`

切片逻辑：

- heading 会作为章节边界
- 长章节会按 token window 切片
- 每个 chunk 会保留章节路径，方便后续检索时知道上下文位置

### `raw_glossary/`

用于存放金融术语库。适合放概念定义、别名、相关术语、示例和备注。

推荐格式：

- CSV
- Markdown
- YAML
- JSON

CSV 推荐字段：

```csv
term,definition,aliases,category,related_terms,example,notes
```

当前目录里的 `glossary_template.csv` 是模板文件，可以按这个格式继续补充真实术语。

切片逻辑：

- 通常一个术语生成一个结构化 chunk
- 很长的术语解释会退回 token window 切片
- payload 会保留 aliases、category、related_terms 等元数据

## 索引与构建目录

### `qdrant/`

这是本地 Qdrant collection 的默认持久化目录，也是 SQLite 关键词索引的默认位置。

构建 KB 后可能生成：

```text
kb/qdrant/
kb/qdrant/kb_lexical_index.sqlite
```

注意：

- 这个目录由 KB pipeline 管理
- 没有 build 前只有 README 是正常的
- 一旦 build 出真实索引文件，不建议手动删除，除非你明确要重建 KB

## 常用命令

构建全部 KB：

```bash
python scripts/build_knowledge_base_qdrant.py build
```

只构建研报：

```bash
python scripts/build_knowledge_base_qdrant.py build --doc-types report
```

只构建财报：

```bash
python scripts/build_knowledge_base_qdrant.py build --doc-types filing
```

构建百科和术语：

```bash
python scripts/build_knowledge_base_qdrant.py build --doc-types encyclopedia,glossary
```

重建整个 Qdrant collection：

```bash
python scripts/build_knowledge_base_qdrant.py build --rebuild
```

检索 KB：

```bash
python scripts/build_knowledge_base_qdrant.py search --query "腾讯 2023 年报 毛利率变化"
```

通过扩展入口构建：

```bash
python agent_ext.py build-kb
```

通过扩展入口检索：

```bash
python agent_ext.py search-kb --query "英伟达 AI 服务器需求"
```

## 与 Agent 工具的关系

当前已接入 agent 的 KB/数据工具包括：

- `retrieve_reports`：检索 `raw_reports/` 入库后的研报证据块
- `retrieve_filings`：检索 `raw_filings/` 入库后的财报/公告证据块
- `market_data_snapshot`：读取本地历史行情 Parquet，不直接读取 `kb/raw_*`
- `realtime_quote`：通过 AkShare 查实时行情，并结合本地历史行情做成交量异动解释

`raw_encyclopedia/` 和 `raw_glossary/` 已经能走统一 KB build/search 管线，但暂时还没有独立的 agent 专用工具入口。后续可以根据需要新增 `retrieve_knowledge`、`retrieve_glossary` 或统一 `retrieve_kb` 工具。

## 不建议删除的内容

不建议删除：

- `kb/` 整个目录
- `kb/stock_universe.yaml`
- `kb/raw_reports/`
- `kb/raw_filings/`
- `kb/qdrant/`

可以暂时不用，但建议保留：

- `kb/raw_encyclopedia/`
- `kb/raw_glossary/`

可以按需清理：

- 各子目录里的 README，占位说明文件本身不参与运行
- `glossary_template.csv`，如果你已经建立了真实术语库，可以替换或删除模板

一句话：`kb/` 是本地知识底座的入口和索引输出根目录。现在空目录多，是因为真实语料尚未放入；后续研报、财报、百科、术语库完善后，这里会成为 RAG 数据工程的核心工作区。
