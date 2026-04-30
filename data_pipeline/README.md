# data_pipeline 目录说明

`data_pipeline/` 是 FinAgent 的数据工程核心模块目录。这里放的是“真正处理数据的代码”，包括历史行情管线、新 KB/RAG 管线、配置加载、股票池读取和通用存储工具。

`scripts/` 里的脚本可以理解为命令行入口：它们负责解析终端参数，然后调用 `data_pipeline/` 里的类和函数。实际的数据拉取、清洗、特征工程、切片、向量化、索引和检索逻辑，主要都在 `data_pipeline/` 里面完成。

## 当前文件

| 文件 | 作用 | 定位 |
|---|---|---|
| `__init__.py` | 包入口，统一导出 `HistoricalMarketDataPipeline`、配置加载、股票池加载等对象；同时通过懒加载暴露 `KnowledgeBasePipeline` | 支撑文件 |
| `settings.py` | 加载扩展层配置，读取 `config_ext.local.yml` / `config_ext.example.yml`，并解析历史行情目录、KB 目录、Qdrant、embedding、chunk 参数等 | 核心基础配置 |
| `storage.py` | 通用存储 helper，负责创建目录、读写 Parquet | 基础工具 |
| `universe.py` | 读取 `kb/stock_universe.yaml` 股票池，并按市场/股票代码筛选 | 历史行情核心依赖 |
| `market_data.py` | 历史行情数据管线。批量拉取 A 股、港股、美股日线和周线，标准化字段，增量刷新，写 Parquet，并计算 MA、RSI、MACD、布林带等技术指标 | 历史行情核心 |
| `knowledge_base.py` | 新 KB/RAG 核心管线。处理研报、财报、百科、术语库，做文件哈希去重、切片、向量化入 Qdrant、SQLite 关键词索引、混合检索、rerank、邻近 chunk 展开 | KB/RAG 核心 |

## 和 scripts 的关系

`scripts/` 里的两个脚本只是命令行入口，不是主要处理逻辑本身。

| scripts 入口 | 实际调用的 data_pipeline 模块 | 说明 |
|---|---|---|
| `scripts/build_historical_market_data.py` | `data_pipeline/market_data.py`、`data_pipeline/universe.py` | 手动触发历史日线/周线数据构建 |
| `scripts/build_knowledge_base_qdrant.py` | `data_pipeline/knowledge_base.py` | 手动触发新 KB 构建或命令行检索测试 |

举个例子：

```bash
python scripts/build_historical_market_data.py --market us --symbols NVDA
```

这个命令本身只负责接收 `--market`、`--symbols` 等参数，然后调用 `HistoricalMarketDataPipeline`。真正拉取行情、标准化字段、计算技术指标和写 Parquet 的逻辑在 `market_data.py`。

再比如：

```bash
python scripts/build_knowledge_base_qdrant.py build --doc-types report
```

这个命令本身只负责接收 `build` 和 `--doc-types` 参数，然后调用 `KnowledgeBasePipeline`。真正读取研报、切片、embedding、写 Qdrant、建 SQLite 关键词索引的逻辑在 `knowledge_base.py`。

## 当前数据流

历史行情数据流：

```text
kb/stock_universe.yaml
-> data_pipeline/universe.py
-> data_pipeline/market_data.py
-> data/market_data/{market}/{interval}/{symbol}.parquet
-> tools/market_data_snapshot.py / tools/realtime_quote.py
```

新 KB/RAG 数据流：

```text
kb/raw_reports/
kb/raw_filings/
kb/raw_encyclopedia/
kb/raw_glossary/
-> data_pipeline/knowledge_base.py
-> kb/qdrant/
-> tools/report_retriever.py / tools/filing_retriever.py
```

